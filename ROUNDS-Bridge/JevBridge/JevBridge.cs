using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;
using BepInEx;
using BepInEx.Configuration;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace JevBridge
{
    /// <summary>
    /// Exposes ROUNDS game state over a local TCP socket and lets an external
    /// agent (JevPilot) drive one player. Only active in offline/local games:
    /// it never touches input while connected to an online room.
    /// </summary>
    [BepInPlugin("com.leo.jevbridge", "JevBridge", "1.0.0")]
    public class JevBridgePlugin : BaseUnityPlugin
    {
        internal static JevBridgePlugin Instance;
        private ConfigEntry<int> port;

        // Command state, written on the main thread only.
        internal static int ControlledId = -1;
        internal static float CmdMove;
        internal static bool CmdShoot;
        internal static int CmdTarget = -1;
        internal static float LastCmdTime = -99f;
        internal static float JumpUntil = -1f;
        internal static bool JumpEdge;
        internal static float BlockArmedUntil = -1f;
        internal static bool BlockNow;
        internal static float BulletSpeed = 60f, BulletGravity = 30f;
        internal static volatile bool ClientConnected;
        // AI scripts we switched off while Jev drives a vanilla bot; restored on release.
        private static readonly List<Behaviour> disabledAi = new List<Behaviour>();
        private static int takenOverId = -1;
        private static readonly HashSet<int> seenBullets = new HashSet<int>();

        private class Request
        {
            public string Line;
            public string Reply;
            public readonly ManualResetEventSlim Done = new ManualResetEventSlim(false);
        }

        private readonly Queue<Request> pending = new Queue<Request>();
        private TcpListener listener;

        private void Awake()
        {
            Instance = this;
            port = Config.Bind("General", "Port", 5577, "Local TCP port JevPilot connects to.");
            Application.runInBackground = true; // keep playing while JevPilot has focus
            new Harmony("com.leo.jevbridge").PatchAll();
            // BepInEx's manager object can be destroyed by the game; tick from our own.
            var ticker = new GameObject("JevBridgeTicker") { hideFlags = HideFlags.HideAndDontSave };
            DontDestroyOnLoad(ticker);
            ticker.AddComponent<Ticker>();
            var t = new Thread(ServeLoop) { IsBackground = true, Name = "JevBridge" };
            t.Start();
            Logger.LogInfo("JevBridge listening on 127.0.0.1:" + port.Value);
        }

        // ---------------------------------------------------------------- network
        private void ServeLoop()
        {
            listener = new TcpListener(IPAddress.Loopback, port.Value);
            listener.Start();
            while (true)
            {
                try
                {
                    using (TcpClient client = listener.AcceptTcpClient())
                    using (NetworkStream ns = client.GetStream())
                    using (var reader = new StreamReader(ns, new UTF8Encoding(false)))
                    using (var writer = new StreamWriter(ns, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" })
                    {
                        client.NoDelay = true;
                        ClientConnected = true;
                        string line;
                        while ((line = reader.ReadLine()) != null)
                        {
                            var req = new Request { Line = line.Trim() };
                            lock (pending) pending.Enqueue(req);
                            writer.WriteLine(req.Done.Wait(3000) ? req.Reply : "{\"error\":\"game did not answer\"}");
                        }
                    }
                }
                catch (Exception e)
                {
                    Logger.LogWarning("JevBridge client: " + e.Message);
                }
                ClientConnected = false;
                ControlledId = -1; // client gone -> hand control back (Tick restores the bot AI)
            }
        }

        internal void Tick()
        {
            SyncTakeover();
            TrackOwnBullets();
            while (true)
            {
                Request req;
                lock (pending)
                {
                    if (pending.Count == 0) break;
                    req = pending.Dequeue();
                }
                try { req.Reply = Handle(req.Line); }
                catch (Exception e) { req.Reply = "{\"error\":" + Json.Str(e.GetType().Name + ": " + e.Message) + "}"; }
                req.Done.Set();
            }
        }

        private string Handle(string line)
        {
            string[] a = line.Split(' ');
            switch (a[0].ToUpperInvariant())
            {
                case "STATE":
                    return StateJson();
                case "CONTROL":
                    ControlledId = int.Parse(a[1], CultureInfo.InvariantCulture);
                    return "{\"ok\":true}";
                case "ACT":
                    // ACT move shoot jump blockArm blockNow target
                    CmdMove = Mathf.Clamp(F(a[1]), -1f, 1f);
                    CmdShoot = a[2] == "1";
                    if (a[3] == "1" && Time.time > JumpUntil) { JumpEdge = true; JumpUntil = Time.time + 0.3f; }
                    if (a[4] == "1") BlockArmedUntil = Time.time + 0.7f;
                    if (a[5] == "1") BlockNow = true;
                    CmdTarget = int.Parse(a[6], CultureInfo.InvariantCulture);
                    LastCmdTime = Time.unscaledTime;
                    return "{\"ok\":true}";
                case "PICK":
                    return Pick(int.Parse(a[1], CultureInfo.InvariantCulture));
                case "RELEASE":
                    ControlledId = -1;
                    return "{\"ok\":true}";
                default:
                    return "{\"error\":\"unknown command\"}";
            }
        }

        /// When Jev controls a vanilla bot (lobby key B), switch its own AI off so
        /// both don't fight over the inputs; give it back as soon as Jev lets go.
        private static void SyncTakeover()
        {
            int want = ClientConnected ? ControlledId : -1;
            Player p = want >= 0 ? FindPlayer(want) : null;
            bool isBot = p != null && p.data != null && p.data.playerActions == null;
            if (isBot && takenOverId == want && disabledAi.Count > 0 && disabledAi[0] != null) return;
            if (!isBot && takenOverId < 0) return;

            foreach (Behaviour b in disabledAi) if (b != null) b.enabled = true;
            disabledAi.Clear();
            takenOverId = -1;
            if (!isBot) return;

            foreach (MonoBehaviour mb in p.GetComponentsInChildren<MonoBehaviour>(true))
            {
                string n = mb.GetType().Name;
                if (mb.enabled && (n.StartsWith("PlayerAI") || n == "PlayerAPI"))
                {
                    mb.enabled = false;
                    disabledAi.Add(mb);
                }
            }
            takenOverId = want;
        }

        internal static bool IsJevControlled(Player p) =>
            p != null && ClientConnected && p.PlayerID == ControlledId;

        private static float F(string s) => float.Parse(s, CultureInfo.InvariantCulture);

        internal static bool Allowed => PhotonNetwork.OfflineMode;

        internal static Player FindPlayer(int id)
        {
            if (PlayerManager.instance == null) return null;
            foreach (Player p in PlayerManager.instance.players)
                if (p != null && p.PlayerID == id) return p;
            return null;
        }

        // Learn the real bullet speed/gravity from our own shots, so aiming adapts to cards.
        private void TrackOwnBullets()
        {
            Player me = FindPlayer(ControlledId);
            if (me == null) return;
            foreach (ProjectileHit ph in FindObjectsOfType<ProjectileHit>())
            {
                if (ph.ownPlayer != me) continue;
                int id = ph.GetInstanceID();
                if (!seenBullets.Add(id)) continue;
                MoveTransform mt = ph.GetComponent<MoveTransform>();
                if (mt == null) continue;
                float sp = mt.velocity.magnitude;
                if (sp > 5f) BulletSpeed = Mathf.Lerp(BulletSpeed, sp, 0.5f);
                BulletGravity = mt.gravity;
            }
            if (seenBullets.Count > 5000) seenBullets.Clear();
        }

        // ---------------------------------------------------------------- aiming / danger
        internal static Vector3 AimAt(Player me, Player target)
        {
            Vector3 from = me.data.hand != null ? me.data.hand.position : me.transform.position;
            Vector3 tp = target.transform.position;
            Vector3 tv = target.data.playerVel != null ? (Vector3)VelocityOf(target) : Vector3.zero;
            float v = Mathf.Max(10f, BulletSpeed);
            Vector3 aimPoint = tp;
            for (int i = 0; i < 3; i++)
            {
                float t = Vector3.Distance(from, aimPoint) / v;
                aimPoint = tp + tv * t + Vector3.up * (0.5f * BulletGravity * t * t);
            }
            Vector3 d = aimPoint - from;
            d.z = 0f;
            return d.normalized;
        }

        private static readonly FieldInfo velField = AccessTools.Field(typeof(PlayerVelocity), "velocity");

        internal static Vector2 VelocityOf(Player p)
        {
            if (p.data.playerVel == null || velField == null) return Vector2.zero;
            object v = velField.GetValue(p.data.playerVel);
            return v is Vector2 v2 ? v2 : Vector2.zero;
        }

        internal static Player NearestEnemy(Player me)
        {
            Player best = null;
            float bd = float.MaxValue;
            foreach (Player p in PlayerManager.instance.players)
            {
                if (p == null || p == me || p.TeamID == me.TeamID || p.data.dead) continue;
                float d = Vector3.Distance(p.transform.position, me.transform.position);
                if (d < bd) { bd = d; best = p; }
            }
            return best;
        }

        /// Seconds until the most dangerous enemy bullet reaches us (or +inf).
        internal static float TimeToImpact(Player me, out int count)
        {
            count = 0;
            float best = float.PositiveInfinity;
            Vector3 pos = me.transform.position;
            foreach (ProjectileHit ph in FindObjectsOfType<ProjectileHit>())
            {
                if (ph.ownPlayer == me || (ph.ownPlayer != null && ph.ownPlayer.TeamID == me.TeamID)) continue;
                MoveTransform mt = ph.GetComponent<MoveTransform>();
                if (mt == null) continue;
                Vector3 rel = ph.transform.position - pos;
                Vector3 v = mt.velocity;
                if (rel.magnitude > 30f || v.sqrMagnitude < 1f) continue;
                count++;
                float t = -Vector3.Dot(rel, v) / v.sqrMagnitude;
                if (t < 0f) continue;
                float miss = (rel + v * t).magnitude;
                if (miss < 1.6f && t < best) best = t;
            }
            return best;
        }

        // ---------------------------------------------------------------- cards
        private static readonly FieldInfo spawnedField = AccessTools.Field(typeof(CardChoice), "spawnedCards");
        private static readonly FieldInfo pickerTypeField = AccessTools.Field(typeof(CardChoice), "pickerType");
        private static readonly FieldInfo dealingField = AccessTools.Field(typeof(CardChoice), "isPlaying");

        /// True once every offered card has been dealt (the deal animation is over).
        internal static bool CardsReady()
        {
            CardChoice cc = CardChoice.instance;
            return cc != null && cc.IsPicking && !(bool)dealingField.GetValue(cc) && Offered().Count > 0;
        }
        private static readonly FieldInfo nameField = AccessTools.Field(typeof(CardInfo), "cardName");
        private static readonly FieldInfo descField = AccessTools.Field(typeof(CardInfo), "cardDestription");

        internal static List<GameObject> Offered()
        {
            if (CardChoice.instance == null) return new List<GameObject>();
            return spawnedField.GetValue(CardChoice.instance) as List<GameObject> ?? new List<GameObject>();
        }

        private static bool MyPick(Player me)
        {
            CardChoice cc = CardChoice.instance;
            if (cc == null || !cc.IsPicking || cc.pickrID < 0 || me == null) return false;
            int pickerType = Convert.ToInt32(pickerTypeField.GetValue(cc));
            return pickerType == 0 ? cc.pickrID == me.TeamID : cc.pickrID == me.PlayerID;
        }

        private string Pick(int index)
        {
            Player me = FindPlayer(ControlledId);
            if (!Allowed) return "{\"error\":\"online game - JevBridge only works in local games\"}";
            if (!MyPick(me)) return "{\"error\":\"not our pick\"}";
            if (!CardsReady()) return "{\"error\":\"cards still being dealt\"}";
            List<GameObject> cards = Offered();
            if (index < 0 || index >= cards.Count || cards[index] == null) return "{\"error\":\"bad index\"}";
            CardChoice.instance.Pick(cards[index]);
            CardChoice.instance.pickrID = -1;
            return "{\"ok\":true}";
        }

        internal static string CardName(CardInfo c)
        {
            string n = nameField?.GetValue(c) as string;
            if (string.IsNullOrEmpty(n)) { try { n = c.CardName; } catch { n = c.name; } }
            return n;
        }

        private static void CardJson(Json j, CardInfo c)
        {
            j.Open();
            j.Key("name").Val(CardName(c));
            string d = descField?.GetValue(c) as string;
            if (string.IsNullOrEmpty(d)) { try { d = c.CardDescription; } catch { d = ""; } }
            j.Key("description").Val(d == c.name ? "" : d);
            j.Key("rarity").Val(c.rarity.ToString());
            j.Key("stats").OpenArr();
            if (c.cardStats != null)
                foreach (CardInfoStat s in c.cardStats)
                {
                    string stat = s.stat, amount = s.amount;
                    try { if (string.IsNullOrEmpty(stat) && !s.LocalizedStat.IsEmpty) stat = s.LocalizedStat.GetLocalizedString(); } catch { }
                    try { if (string.IsNullOrEmpty(amount)) amount = s.GetSimpleAmount(); } catch { }
                    j.Open().Key("stat").Val(stat).Key("amount").Val(amount).Key("positive").Val(s.positive).Close();
                }
            j.CloseArr();
            j.Close();
        }

        // ---------------------------------------------------------------- state
        private static readonly int groundMask = LayerMask.GetMask("Default");

        private string StateJson()
        {
            var j = new Json();
            j.Open();
            j.Key("offline").Val(Allowed);
            j.Key("controlled").Val(ControlledId);
            Player me = FindPlayer(ControlledId);
            bool picking = CardChoice.instance != null && CardChoice.instance.IsPicking;
            bool fighting = me != null && me.data.isPlaying && !picking;
            j.Key("phase").Val(picking ? "pick" : fighting ? "fight" : "other");
            j.Key("my_pick").Val(MyPick(me));
            j.Key("cards_ready").Val(CardsReady());
            j.Key("bullet_speed").Val(BulletSpeed);

            j.Key("players").OpenArr();
            if (PlayerManager.instance != null)
                foreach (Player p in PlayerManager.instance.players)
                {
                    if (p == null) continue;
                    CharacterData d = p.data;
                    Vector2 vel = VelocityOf(p);
                    j.Open();
                    j.Key("id").Val(p.PlayerID).Key("team").Val(p.TeamID);
                    j.Key("x").Val(p.transform.position.x).Key("y").Val(p.transform.position.y);
                    j.Key("vx").Val(vel.x).Key("vy").Val(vel.y);
                    j.Key("hp").Val(d.health).Key("max_hp").Val(d.MaxHealth);
                    j.Key("dead").Val(d.dead).Key("grounded").Val(d.isGrounded).Key("wall_grab").Val(d.isWallGrab);
                    j.Key("jumps_left").Val(d.currentJumps);
                    j.Key("bot").Val(d.playerActions == null);
                    Gun gun = d.weaponHandler != null ? d.weaponHandler.gun : null;
                    GunAmmo ammo = gun != null ? gun.GetComponentInChildren<GunAmmo>() : null;
                    if (ammo != null)
                    {
                        j.Key("ammo").Val(Convert.ToInt32(AccessTools.Field(typeof(GunAmmo), "currentAmmo").GetValue(ammo)));
                        j.Key("max_ammo").Val(ammo.maxAmmo);
                    }
                    if (d.block != null) j.Key("block_ready").Val(!d.block.IsOnCD());
                    j.Key("cards").OpenArr();
                    if (d.currentCards != null) foreach (CardInfo c in d.currentCards) j.Val(CardName(c));
                    j.CloseArr();
                    if (me != null && p != me)
                    {
                        Vector3 a = me.transform.position, b = p.transform.position;
                        RaycastHit2D hit = Physics2D.Linecast(a, b, groundMask);
                        j.Key("line_of_sight").Val(hit.collider == null || hit.collider.GetComponentInParent<Player>() != null);
                    }
                    j.Close();
                }
            j.CloseArr();

            if (me != null && fighting)
            {
                Vector3 pos = me.transform.position;
                j.Key("env").Open();
                j.Key("ground_left").Val(me.data.ThereIsGroundBelow(pos + Vector3.left * 3f, 10f));
                j.Key("ground_right").Val(me.data.ThereIsGroundBelow(pos + Vector3.right * 3f, 10f));
                j.Key("wall_left").Val(Physics2D.Raycast(pos, Vector2.left, 2.5f, groundMask).collider != null);
                j.Key("wall_right").Val(Physics2D.Raycast(pos, Vector2.right, 2.5f, groundMask).collider != null);
                j.Key("ceiling").Val(Physics2D.Raycast(pos, Vector2.up, 4f, groundMask).collider != null);
                int n;
                float tti = TimeToImpact(me, out n);
                j.Key("enemy_bullets").Val(n);
                j.Key("bullet_impact_in").Val(float.IsInfinity(tti) ? -1f : tti);
                j.Close();
            }

            if (picking)
            {
                j.Key("cards").OpenArr();
                foreach (GameObject go in Offered())
                {
                    CardInfo c = go != null ? go.GetComponent<CardInfo>() : null;
                    if (c != null) CardJson(j, c); else j.Val((string)null);
                }
                j.CloseArr();
            }
            j.Close();
            return j.ToString();
        }
    }

    /// Vanilla bots (lobby key B) have no PlayerActions, so their lobby slot throws
    /// every frame and can never ready up. Ready them automatically instead.
    [HarmonyPatch(typeof(CharacterSelectionInstance), "Update")]
    internal static class BotReadyPatch
    {
        private static bool Prefix(CharacterSelectionInstance __instance)
        {
            Player p = __instance.currentPlayer;
            if (p == null || p.data == null || p.data.playerActions != null) return true;
            if (!Traverse.Create(__instance).Field<bool>("isReady").Value) __instance.ReadyUp();
            return false;
        }
    }

    /// Vanilla bots also have no actions during the card pick, which stalls the game.
    /// Let them take a random card once the deal is finished.
    [HarmonyPatch(typeof(CardChoice), "DoPlayerSelect")]
    internal static class BotPickPatch
    {
        private static float readySince = -1f;

        private static bool Prefix(CardChoice __instance)
        {
            if (__instance.pickrID < 0 || !JevBridgePlugin.CardsReady()) { readySince = -1f; return true; }
            int pickerType = Convert.ToInt32(AccessTools.Field(typeof(CardChoice), "pickerType").GetValue(__instance));
            PlayerActions[] actions = pickerType == 0
                ? PlayerManager.instance.GetActionsFromTeam(__instance.pickrID)
                : PlayerManager.instance.GetActionsFromPlayer(__instance.pickrID);
            if (actions == null) return true; // the game already handles this case
            foreach (PlayerActions a in actions) if (a != null) return true; // a human picks
            Player jev = JevBridgePlugin.FindPlayer(JevBridgePlugin.ControlledId);
            if (jev != null && JevBridgePlugin.ClientConnected &&
                (pickerType == 0 ? jev.TeamID == __instance.pickrID : jev.PlayerID == __instance.pickrID))
                return false; // Jev picks this one over the bridge
            if (readySince < 0f) readySince = Time.unscaledTime;
            if (Time.unscaledTime - readySince < 1.0f) return false; // short "thinking" pause
            List<GameObject> cards = JevBridgePlugin.Offered();
            GameObject pick = cards[UnityEngine.Random.Range(0, cards.Count)];
            if (pick == null) return false;
            readySince = -1f;
            __instance.Pick(pick);
            __instance.pickrID = -1;
            return false;
        }
    }

    internal class Ticker : MonoBehaviour
    {
        private void Update() => JevBridgePlugin.Instance?.Tick();
    }

    [HarmonyPatch(typeof(GeneralInput), "Update")]
    internal static class InputPatch
    {
        private static bool lastShoot;
        private static float shootCycle;

        private static void Postfix(GeneralInput __instance)
        {
            int id = JevBridgePlugin.ControlledId;
            if (id < 0 || !JevBridgePlugin.Allowed) return;
            if (Time.unscaledTime - JevBridgePlugin.LastCmdTime > 1.5f) return; // stale -> hands off
            if (GameManager.lockInput || __instance.stunnedInput) return;
            CharacterData data = __instance.GetComponent<CharacterData>();
            if (data == null || data.player == null || data.player.PlayerID != id || !data.isPlaying || data.dead) return;
            Player me = data.player;

            __instance.direction = new Vector3(JevBridgePlugin.CmdMove, 0f, 0f);
            if (__instance.direction != Vector3.zero) __instance.latestPressedDirection = __instance.direction;

            Player target = JevBridgePlugin.FindPlayer(JevBridgePlugin.CmdTarget);
            if (target == null || target.data.dead || target.TeamID == me.TeamID) target = JevBridgePlugin.NearestEnemy(me);
            if (target != null)
            {
                __instance.aimDirection = JevBridgePlugin.AimAt(me, target);
                __instance.lastAimDirection = __instance.aimDirection;
            }

            bool jumpHeld = Time.time < JevBridgePlugin.JumpUntil;
            __instance.jumpIsPressed = jumpHeld;
            __instance.jumpWasPressed = JevBridgePlugin.JumpEdge;
            JevBridgePlugin.JumpEdge = false;

            // Hold fire, but re-press every 0.3 s so semi-auto and charge guns also fire.
            bool shoot = JevBridgePlugin.CmdShoot && !__instance.silencedInput;
            if (shoot)
            {
                shootCycle += Time.deltaTime;
                if (shootCycle > 0.3f) { shootCycle = 0f; shoot = false; }
            }
            __instance.shootIsPressed = shoot;
            __instance.shootWasPressed = shoot && !lastShoot;
            __instance.shootWasReleased = !shoot && lastShoot;
            lastShoot = shoot;

            bool block = JevBridgePlugin.BlockNow;
            JevBridgePlugin.BlockNow = false;
            if (!block && Time.time < JevBridgePlugin.BlockArmedUntil && data.block != null && !data.block.IsOnCD())
            {
                int n;
                float tti = JevBridgePlugin.TimeToImpact(me, out n);
                block = tti < 0.14f;
            }
            __instance.shieldWasPressed = block && !__instance.silencedInput;
        }
    }

    /// Minimal JSON writer (Unity's JsonUtility can't do dynamic objects).
    internal class Json
    {
        private readonly StringBuilder sb = new StringBuilder();
        private bool needComma;

        private void Comma() { if (needComma) sb.Append(','); needComma = false; }
        public Json Open() { Comma(); sb.Append('{'); return this; }
        public Json Close() { sb.Append('}'); needComma = true; return this; }
        public Json OpenArr() { sb.Append('['); needComma = false; return this; }
        public Json CloseArr() { sb.Append(']'); needComma = true; return this; }
        public Json Key(string k) { Comma(); sb.Append(Str(k)).Append(':'); return this; }
        public Json Val(string v) { Comma(); sb.Append(v == null ? "null" : Str(v)); needComma = true; return this; }
        public Json Val(bool v) { Comma(); sb.Append(v ? "true" : "false"); needComma = true; return this; }
        public Json Val(int v) { Comma(); sb.Append(v.ToString(CultureInfo.InvariantCulture)); needComma = true; return this; }
        public Json Val(float v)
        {
            Comma();
            sb.Append(float.IsNaN(v) || float.IsInfinity(v) ? "0" : Math.Round(v, 3).ToString(CultureInfo.InvariantCulture));
            needComma = true;
            return this;
        }

        public static string Str(string s)
        {
            var b = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') b.Append('\\').Append(c);
                else if (c < ' ') b.Append("\\u").Append(((int)c).ToString("x4"));
                else b.Append(c);
            }
            return b.Append('"').ToString();
        }

        public override string ToString() => sb.ToString();
    }
}
