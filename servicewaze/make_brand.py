"""Compose ServiceWaze brand assets:
  - final logo (1024 + wordmark variant)
  - PWA icon set (512/192/180/maskable) from the new logo
  - branded cover/banner with wordmark + status chips
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DARK = (13, 17, 23)
ACCENT = (56, 189, 248)
TEXT = (230, 237, 243)
MUTED = (154, 167, 184)
GREEN = (52, 211, 153)
AMBER = (251, 191, 36)
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
os.makedirs("assets", exist_ok=True)

# ---------------- 1) Final logo (square, 1024) ----------------
logo = Image.open("assets/logo_raw.png").convert("RGB")
side = min(logo.size)
logo = logo.crop(((logo.width - side) // 2, (logo.height - side) // 2,
                  (logo.width + side) // 2, (logo.height + side) // 2))
logo = logo.resize((1024, 1024), Image.LANCZOS)
logo.save("assets/servicewaze-logo.png")
print("logo 1024:", logo.size)

# ---------------- 2) PWA icon set ----------------
os.makedirs("static/icons", exist_ok=True)
for s, name in [(512, "icon-512.png"), (192, "icon-192.png"), (180, "icon-180.png")]:
    logo.resize((s, s), Image.LANCZOS).save(f"static/icons/{name}")
    print("icon:", name)
# maskable: logo at 66% inside brand-colored safe zone
mask = Image.new("RGB", (512, 512), DARK)
inner = logo.resize((338, 338), Image.LANCZOS)
mask.paste(inner, ((512 - 338) // 2, (512 - 338) // 2))
mask.save("static/icons/maskable-512.png")
print("icon: maskable-512.png")

# ---------------- 3) Wordmark logo variant ----------------
word = Image.new("RGB", (1400, 420), DARK)
icon_small = logo.resize((300, 300), Image.LANCZOS)
word.paste(icon_small, (40, 60))
d = ImageDraw.Draw(word)
f_big = ImageFont.truetype(FONT_B, 150)
f_sub = ImageFont.truetype(FONT_R, 54)
d.text((390, 105), "Service", font=f_big, fill=TEXT)
d.text((390 + d.textlength("Service", font=f_big) + 6, 105), "Waze", font=f_big, fill=ACCENT)
tag = "LIVE SERVICE STATUS FOR YOUR AREA"
d.text((390, 290), tag, font=f_sub, fill=MUTED)
word.save("assets/servicewaze-logo-wordmark.png")
print("wordmark:", word.size)

# ---------------- 4) Cover banner ----------------
cover = Image.open("assets/cover_raw.png").convert("RGB")
W, H = cover.size
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
# left-to-right fade (strong left for text)
fade_stop = int(W * 0.62)
for x in range(fade_stop):
    t = x / fade_stop
    alpha = int(200 * (1 - t) ** 1.4 + 40 * (1 - t))
    od.line([(x, 0), (x, H)], fill=(8, 10, 14, alpha))
# bottom fade for chips
for y in range(H - int(H * 0.35), H):
    t = (y - (H - int(H * 0.35))) / int(H * 0.35)
    od.line([(0, y), (W, y)], fill=(8, 10, 14, int(180 * t)))
cover = Image.alpha_composite(cover.convert("RGBA"), overlay)

d = ImageDraw.Draw(cover)
f_w = ImageFont.truetype(FONT_B, 108)
f_t = ImageFont.truetype(FONT_R, 40)
f_chip = ImageFont.truetype(FONT_B, 30)
f_foot = ImageFont.truetype(FONT_R, 26)

# wordmark
x0, y0 = int(W * 0.045), int(H * 0.16)
d.text((x0, y0), "Service", font=f_w, fill=TEXT)
wx = x0 + d.textlength("Service", font=f_w)
d.text((wx + 4, y0), "Waze", font=f_w, fill=ACCENT)
# tagline
d.text((x0, y0 + 130), "Live service status for your area", font=f_t, fill=(216, 224, 234))
d.text((x0, y0 + 185), "Electricity  ·  Water  ·  Weather  ·  Transport  ·  News", font=f_t, fill=MUTED)

# status chips
def chip(x, y, label, dot_color):
    tw = d.textlength(label, font=f_chip)
    pad_x, pad_y = 22, 12
    w = tw + pad_x * 2 + 26
    h = 62
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(28, 36, 49, 235),
                        outline=(42, 52, 68, 255), width=2)
    d.ellipse([x + pad_x, y + h // 2 - 8, x + pad_x + 16, y + h // 2 + 8], fill=dot_color)
    d.text((x + pad_x + 30, y + 14), label, font=f_chip, fill=TEXT)
    return w

cy = int(H * 0.72)
cx = x0
cx += chip(cx, cy, "No load-shedding", GREEN) + 14
cx += chip(cx, cy, "3 water reports", AMBER) + 14
cx += chip(cx, cy, "16°C · Clear sky", ACCENT)

# footer
d.text((x0, int(H * 0.90)), "FREE  ·  NO LOGIN  ·  WORKS OFFLINE  ·  MULTILINGUAL", font=f_foot, fill=MUTED)
cover.convert("RGB").save("assets/servicewaze-cover.png")
print("cover:", cover.size)
print("DONE")
