"""Text sprites drawn with a font (image models garble lettering).

    python tools/gen_text.py

Plaques are drawn at 1/PIXEL of the HD size without anti-aliasing and scaled up with
nearest neighbour, so they share the chunky pixel look of the generated art.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402

SCALE, PIXEL = 10, 4
OUT = os.path.join(gs.ASSETS, 'sprites')
FONT = '/System/Library/Fonts/Supplemental/Impact.ttf'

# sprite -> (text, board colour, text colour). bb15 was "ПО ЭЛЕКТРОНМАШ" and c003 "г.КИЕВ"
# (the Kiev port's publisher); the remaster credits the original authors instead.
# Both are hidden in the remaster: the credit is part of the title logo (gen_rooms.py).
PLAQUES = {}
HIDDEN = (0xbb15, 0xc003)


# Speech balloons (yellow, tail at the bottom) and floating score numbers.
BALLOONS = {
    0xbbef: ['CONTINUARA'], 0xbcd5: ['TO BE', 'CONTINUED'], 0xbdbb: ['NO'], 0xbdf9: ['OK.'],
    0xbe37: ['LIVINGSTONE', 'I PRESUME'], 0xbf1d: ['LIVINGSTONE', 'SUPONGO'],
}
SCORES = {0x9afd: ('100', (255, 230, 80)), 0x9b23: ('250', (110, 240, 110)), 0x9b49: ('500', (255, 96, 80))}
LABELS = {0xc0a5: ('I PRESUME', (255, 230, 80))}


def canvas(addr):
    _, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
    W, H = w * 4 * SCALE // PIXEL, h * SCALE // PIXEL
    return Image.new('RGBA', (W, H), (0, 0, 0, 0)), W, H


def fit_font(d, lines, max_w, max_h):
    size = max_h
    while size > 4:
        font = ImageFont.truetype(FONT, size)
        boxes = [d.textbbox((0, 0), t, font=font) for t in lines]
        lh = max(b[3] - b[1] for b in boxes)
        if max(b[2] - b[0] for b in boxes) <= max_w and lh * len(lines) + (len(lines) - 1) <= max_h:
            return font, boxes, lh
        size -= 1
    return font, boxes, lh


def draw_lines(d, lines, font, boxes, lh, cx, top, ink, shadow):
    for i, (t, b) in enumerate(zip(lines, boxes)):
        x, y = cx - (b[2] - b[0]) // 2 - b[0], top + i * (lh + 1) - b[1]
        d.text((x + 1, y + 1), t, font=font, fill=shadow)
        d.text((x, y), t, font=font, fill=ink)


def balloon(addr, lines):
    im, W, H = canvas(addr)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    tail = max(3, H // 5)
    body_h = H - tail
    edge, fill, ink = (60, 40, 10, 255), (255, 228, 92, 255), (60, 36, 8, 255)
    d.rounded_rectangle((0, 0, W - 1, body_h - 1), radius=4, fill=edge)
    d.rounded_rectangle((1, 1, W - 2, body_h - 2), radius=4, fill=fill)
    cx = W // 2
    d.polygon([(cx - 3, body_h - 2), (cx + 3, body_h - 2), (cx - 1, H - 1)], fill=edge)
    d.polygon([(cx - 2, body_h - 3), (cx + 2, body_h - 3), (cx - 1, H - 3)], fill=fill)
    font, boxes, lh = fit_font(d, lines, W - 8, body_h - 6)
    top = (body_h - (lh * len(lines) + len(lines) - 1)) // 2
    draw_lines(d, lines, font, boxes, lh, cx, top, ink, (200, 160, 40, 255))
    return im.resize((W * PIXEL, H * PIXEL), Image.NEAREST)


def label(addr, text, ink):
    im, W, H = canvas(addr)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    font, boxes, lh = fit_font(d, [text], W - 2, H - 2)
    shadow = (40, 20, 0, 255)
    # outline: draw the shadow around, then the text
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw_lines(d, [text], font, boxes, lh, W // 2 + dx, (H - lh) // 2 + dy, shadow, shadow)
    draw_lines(d, [text], font, boxes, lh, W // 2, (H - lh) // 2, ink, shadow)
    return im.resize((W * PIXEL, H * PIXEL), Image.NEAREST)


def plaque(addr, text, board, ink):
    _, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
    W, H = w * 4 * SCALE // PIXEL, h * SCALE // PIXEL
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.fontmode = '1'  # no anti-aliasing: clean pixels after upscaling
    dark = tuple(c // 2 for c in board)
    light = tuple(min(255, c + 60) for c in board)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=3, fill=dark)
    d.rounded_rectangle((1, 1, W - 2, H - 2), radius=3, fill=board)
    d.line((3, 2, W - 4, 2), fill=light)
    size = H
    while size > 4:
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = d.textbbox((0, 0), text, font=font)
        if r - l <= W - 8 and b - t <= H - 6:
            break
        size -= 1
    x, y = (W - (r - l)) // 2 - l, (H - (b - t)) // 2 - t
    d.text((x + 1, y + 1), text, font=font, fill=dark)
    d.text((x, y), text, font=font, fill=ink)
    return im.resize((W * PIXEL, H * PIXEL), Image.NEAREST)


def main():
    os.makedirs(OUT, exist_ok=True)
    for addr in HIDDEN:  # fully transparent override = not drawn
        _, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
        Image.new('RGBA', (w * 4 * SCALE, h * SCALE), (0, 0, 0, 0)).save(os.path.join(OUT, f'{addr:04x}.png'))
        print(f'{addr:04x}: hidden')
    for addr, (text, board, ink) in PLAQUES.items():
        plaque(addr, text, board, ink).save(os.path.join(OUT, f'{addr:04x}.png'))
        print(f'{addr:04x}: {text}')
    for addr, lines in BALLOONS.items():
        balloon(addr, lines).save(os.path.join(OUT, f'{addr:04x}.png'))
        print(f'{addr:04x}: balloon {" / ".join(lines)}')
    for addr, (text, ink) in {**SCORES, **LABELS}.items():
        label(addr, text, ink).save(os.path.join(OUT, f'{addr:04x}.png'))
        print(f'{addr:04x}: {text}')


if __name__ == '__main__':
    main()
