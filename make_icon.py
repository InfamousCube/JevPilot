"""Draws JevPilot.ico: terracotta rounded square with a cream eight-point spark."""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), 112, fill=(217, 119, 87, 255))

cx = cy = S / 2
for i in range(8):
    a = math.pi / 4 * i
    tip = (cx + math.cos(a) * 170, cy + math.sin(a) * 170)
    side = 34
    left = (cx + math.cos(a + math.pi / 2) * side, cy + math.sin(a + math.pi / 2) * side)
    right = (cx + math.cos(a - math.pi / 2) * side, cy + math.sin(a - math.pi / 2) * side)
    d.polygon([left, tip, right], fill=(250, 249, 245, 255))
d.ellipse((cx - 46, cy - 46, cx + 46, cy + 46), fill=(250, 249, 245, 255))

img.save(os.path.join(HERE, "JevPilot.ico"),
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ok")
