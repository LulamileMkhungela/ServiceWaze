"""Generate PWA icons with Pillow (no external assets)."""
import os
from PIL import Image, ImageDraw

def make(size, maskable=False):
    pad = int(size * 0.12) if maskable else 0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # rounded-square background with vertical gradient
    d = ImageDraw.Draw(img)
    w, h = size, size
    top, bot = (13, 23, 30, 255), (9, 13, 18, 255)
    for y in range(h):
        t = y / h
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(4))
        d.line([(0, y), (w, y)], fill=c)
    # rounded mask
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(size * 0.22), fill=255)
    img.putalpha(mask)
    # border
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(size * 0.22), outline=(56, 189, 248, 120), width=max(2, int(size * 0.015)))
    # lightning bolt (accent)
    bolt = [(0.52, 0.16), (0.30, 0.54), (0.46, 0.54), (0.40, 0.86), (0.66, 0.44), (0.49, 0.44)]
    scaled = [(int(x * size), int(y * size)) for x, y in bolt]
    d.polygon(scaled, fill=(56, 189, 248, 255))
    # water drop (white)
    cx, cy = size * 0.74, size * 0.72
    r = size * 0.115
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(230, 237, 243, 235))
    d.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], fill=(56, 189, 248, 255))
    return img

os.makedirs("static/icons", exist_ok=True)
for s, name, mask in [(192, "icon-192.png", False), (512, "icon-512.png", False),
                      (512, "maskable-512.png", True), (180, "icon-180.png", False)]:
    make(s, mask).save(f"static/icons/{name}")
    print("wrote", name)
