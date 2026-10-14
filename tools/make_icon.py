"""App icon from existing art: jungle square, the HD hero, a corner badge ("HD" or "$60").

    python tools/make_icon.py OUT.iconset [BADGE]     # BADGE: corner text, default "HD"

Writes the PNG sizes iconutil expects; make_app.sh turns the folder into an .icns.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'remaster', 'assets')
FONT = '/System/Library/Fonts/Supplemental/Impact.ttf'
S = 1024
BODY = 824  # macOS icon grid: rounded square inside the canvas, room for the shadow
RADIUS = 185


def master(badge_text):
    bg = Image.open(os.path.join(ASSETS, 'rooms', 'room_06.png')).convert('RGB')
    side = bg.height
    bg = bg.crop((560, 0, 560 + side, side)).resize((BODY, BODY), Image.LANCZOS)

    hero = Image.open(os.path.join(ASSETS, 'sprites', '8e69.png'))
    hero = hero.crop(hero.getbbox())
    k = BODY * 0.62 / hero.height
    hero = hero.resize((round(hero.width * k), round(hero.height * k)), Image.NEAREST)
    body = bg.convert('RGBA')
    body.alpha_composite(hero, ((BODY - hero.width) // 2 - 60, BODY - hero.height - 40))

    # corner badge, top right
    badge = Image.new('RGBA', (360, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.rounded_rectangle((0, 0, 359, 199), radius=40, fill=(90, 50, 10, 255))
    d.rounded_rectangle((10, 10, 349, 189), radius=34, fill=(255, 205, 60, 255))
    font = ImageFont.truetype(FONT, 150)
    l, t, r, b = d.textbbox((0, 0), badge_text, font=font)
    x, y = (360 - (r - l)) // 2 - l, (200 - (b - t)) // 2 - t
    d.text((x + 5, y + 5), badge_text, font=font, fill=(150, 90, 10, 255))
    d.text((x, y), badge_text, font=font, fill=(40, 120, 30, 255))
    badge = badge.rotate(-12, resample=Image.BICUBIC, expand=True)
    body.alpha_composite(badge, (BODY - badge.width + 10, 20))

    mask = Image.new('L', (BODY, BODY), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, BODY - 1, BODY - 1), radius=RADIUS, fill=255)
    icon = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    off = (S - BODY) // 2
    shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), (off, off + 12), mask)
    icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    icon.paste(body, (off, off), mask)
    return icon


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    m = master(sys.argv[2] if len(sys.argv) > 2 else 'HD')
    for size in (16, 32, 128, 256, 512):
        m.resize((size, size), Image.LANCZOS).save(os.path.join(out, f'icon_{size}x{size}.png'))
        m.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(out, f'icon_{size}x{size}@2x.png'))
    print('iconset:', out)


if __name__ == '__main__':
    main()
