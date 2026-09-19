"""Wide, thin game cards: cover image, darkening toward the right, name on top."""
import hashlib
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCALE = 2  # render at 2x so cards stay sharp on HiDPI screens
FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _font(size: int):
    for name in ("seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale and center-crop like CSS object-fit: cover."""
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))),
                     Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _fallback_art(name: str, w: int, h: int) -> Image.Image:
    """Warm abstract art derived from the name, used when a game has no image."""
    d = hashlib.md5(name.encode()).digest()
    palette = [(217, 119, 87), (196, 142, 92), (120, 90, 160), (70, 120, 110),
               (180, 80, 90), (90, 110, 170)]
    c1, c2 = palette[d[0] % len(palette)], palette[d[1] % len(palette)]
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        t = x / max(1, w - 1)
        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        for y in range(h):
            px[x, y] = col
    draw = ImageDraw.Draw(img)
    for i in range(6):
        r = h * (0.4 + (d[2 + i] % 60) / 60)
        cx, cy = (d[8 + i] / 255) * w, (d[14 - i] / 255) * h
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=tuple(min(255, v + 30) for v in (c2 if i % 2 else c1)))
    return img.filter(ImageFilter.GaussianBlur(h / 5))


def find_image(games_dir: str, stem: str, explicit: str | None) -> str | None:
    candidates = [explicit] if explicit else []
    candidates += [f"{stem}.{ext}" for ext in ("png", "jpg", "jpeg", "webp")]
    for c in candidates:
        p = c if os.path.isabs(c) else os.path.join(games_dir, c)
        if os.path.isfile(p):
            return p
    return None


def render_card(name: str, image_path: str | None, w: int, h: int, bg: tuple,
                state: str = "idle", accent: tuple = (217, 119, 87)) -> Image.Image:
    """state: idle | hover | selected."""
    W, H, R = w * SCALE, h * SCALE, 9 * SCALE
    try:
        art = _cover(Image.open(image_path), W, H) if image_path else None
    except OSError:
        art = None
    art = art or _fallback_art(name, W, H)

    # Darken toward the right so the name stays readable on any image.
    shade = Image.new("L", (W, 1))
    lift = {"idle": 0, "hover": -25, "selected": -15}[state]
    for x in range(W):
        t = x / (W - 1)
        shade.putpixel((x, 0), max(0, min(255, int(40 + 190 * t ** 1.3) + lift)))
    black = Image.new("RGB", (W, H), (12, 11, 10))
    art = Image.composite(black, art, shade.resize((W, H)))

    draw = ImageDraw.Draw(art)
    font = _font(15 * SCALE)
    text = name
    while draw.textlength(text, font=font) > W * 0.62 and len(text) > 3:
        text = text[:-2].rstrip() + "…"
    tw = draw.textlength(text, font=font)
    ty = (H - font.size) // 2 - 2 * SCALE
    draw.text((W - tw - 14 * SCALE, ty + SCALE), text, font=font, fill=(0, 0, 0))  # soft shadow
    draw.text((W - tw - 14 * SCALE, ty), text, font=font, fill=(250, 249, 245))

    if state == "selected":
        draw.rounded_rectangle((SCALE, SCALE, W - SCALE - 1, H - SCALE - 1), R,
                               outline=accent, width=2 * SCALE)
    elif state == "hover":
        draw.rounded_rectangle((SCALE, SCALE, W - SCALE - 1, H - SCALE - 1), R,
                               outline=(110, 108, 100), width=SCALE)

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), R, fill=255)
    out = Image.new("RGB", (W, H), bg)
    out.paste(art, (0, 0), mask)
    return out
