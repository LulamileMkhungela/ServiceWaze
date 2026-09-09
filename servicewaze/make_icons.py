"""Build the PWA icon set from the source artwork.

    python make_icons.py

Takes assets/icon-1024.png, knocks out the flat background, drops it onto the
ServiceWaze navy→teal gradient tile and writes every size the manifest and
service worker need (including a maskable icon with a safe zone).

Deterministic: no external services, pure Pillow.
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "assets", "icon-1024.png")
OUT = os.path.join(BASE, "static", "icons")
SIZE = 1024


def knockout(src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    w, h = im.size
    bg = im.getpixel((3, 3))
    # flood fill from all four corners to remove the flat background
    for corner in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)):
        try:
            ImageDraw.floodfill(im, corner, (0, 0, 0, 0), thresh=48)
        except Exception:
            pass
    # soften any halo left on the edges
    alpha = im.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    im.putalpha(alpha)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def gradient_tile(size: int, c1=(13, 21, 36), c2=(12, 74, 110)) -> Image.Image:
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    for y in range(size):
        t = y / max(1, size - 1)
        d.line([(0, y), (size, y)],
               fill=(int(c1[0] + (c2[0] - c1[0]) * t),
                     int(c1[1] + (c2[1] - c1[1]) * t),
                     int(c1[2] + (c2[2] - c1[2]) * t), 255))
    return tile


def rounded_square(size: int, radius_ratio: float = 0.22):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * radius_ratio), fill=255)
    return mask


def compose(art: Image.Image, size: int, content: float, bg=(13, 21, 36), rounded=True) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), bg + (255,))
    if not rounded:
        canvas.paste(gradient_tile(size), (0, 0))
    target = int(size * content)
    art_sq = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    a = art.copy()
    a.thumbnail((target, target), Image.LANCZOS)
    art_sq.paste(a, ((target - a.width) // 2, (target - a.height) // 2), a)
    canvas.alpha_composite(art_sq, ((size - target) // 2, (size - target) // 2))
    if rounded:
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(canvas, (0, 0), rounded_square(size))
        return out
    return canvas


def main():
    os.makedirs(OUT, exist_ok=True)
    if not os.path.exists(SRC):
        print("missing", SRC)
        return
    art = knockout(Image.open(SRC))
    jobs = [
        ("icon-192.png", 192, 0.78, True),
        ("icon-512.png", 512, 0.78, True),
        ("icon-180.png", 180, 0.78, True),
        ("maskable-512.png", 512, 0.62, False),   # safe zone for Android masks
        ("icon-1024.png", 1024, 0.78, True),
    ]
    for name, size, content, rounded in jobs:
        img = compose(art, size, content, rounded=rounded)
        img.save(os.path.join(OUT, name))
        print("wrote", name, img.size)
    print("icons in", OUT)


if __name__ == "__main__":
    main()
