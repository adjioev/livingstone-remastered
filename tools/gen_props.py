"""HD props: things the game draws with room tiles but moves at run time.

    python tools/gen_props.py           # generate
    python tools/gen_props.py --recut   # re-cut the saved raw image

Floating log (tiles 222 / 217 x8 / 132, 10 cells): remaster/assets/props/log.png,
sized 10 x 1 tiles at 6x (480 x 48) so the renderer can drop it on the log's cells.

Stake gate (tiles 249 tip / 250 stake, rooms 37 and 3a): gate_tip.png and gate.png, one
48 x 48 cell each, drawn procedurally (no API call): python tools/gen_props.py --gate

Archer's arrow (sprites a7a9 flying up-left at 45 degrees, cfd9 its mirror at launch):
procedural, python tools/gen_props.py --arrow

Miner's thrown pickaxe, spinning (a741 head right, a753 down, a765 left, a777 up):
procedural, python tools/gen_props.py --pick

Poisonous gas in the mines (sprites a905 / a95b / a9b1, three frames of one cloud):
procedural pixel-art puffs, python tools/gen_props.py --gas
"""
import os, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402
import gen_bank as gb  # noqa: E402  (largest_blob)

OUT = os.path.join(gs.ASSETS, 'props')
RAW = os.path.join(gs.ASSETS, 'raw', 'prop_log.png')
LOG_CELLS = 10
W, H = LOG_CELLS * 48, 48

PROMPT = """Draw one game prop as high-detail modern pixel art in the style of image 2.

Image 1 is the original low-resolution prop on magenta: a long horizontal FLOATING LOG (a tree trunk
lying on its side, seen from the side, cut ends on the left and right, bark texture, a little moss).

Rules:
- One single log, horizontal, long and thin like image 1 (about 10 times longer than it is tall).
- Flat pure magenta #FF00FF background, no water, no shadow, no text."""


def guide():
    tiles = [gs.gfx.LOG_L] + [gs.gfx.LOG_MID] * (LOG_CELLS - 2) + [gs.gfx.LOG_R]
    im = Image.new('RGB', (LOG_CELLS * 8, 8))
    px = im.load()
    for i, t in enumerate(tiles):
        gs.gfx.draw_tile(px, gs.gfx.TILES_A, t, i * 8, 0, gs.gfx.PAL[0])
    p = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if p[x, y] == (0, 0, 0):
                p[x, y] = gs.KEY
    sheet = Image.new('RGB', (1024, 576), gs.KEY)
    big = im.resize((960, 96), Image.NEAREST)
    sheet.paste(big, (32, 240))
    return sheet


def cut(raw):
    fig = gb.largest_blob(gs.key_out(raw))
    fig = fig.crop(fig.getbbox())
    os.makedirs(OUT, exist_ok=True)
    fig.resize((W, H), Image.LANCZOS).save(os.path.join(OUT, 'log.png'))
    print('saved', os.path.join(OUT, 'log.png'))


def gate_tiles():
    """Sharpened wooden stake with an iron band, 16 x 16 art pixels -> 48 x 48."""
    dark, wood, light, iron, iron_hi = (52, 30, 14), (132, 84, 40), (184, 132, 74), (70, 72, 80), (150, 154, 164)
    def cell(tip):
        im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
        p = im.load()
        x0, x1 = 4, 11  # stake body columns
        for y in range(16):
            if tip and y < 7:  # point: narrows to the top
                half = max(0, (y * 4) // 7)
                a, b = 7 - half, 8 + half
            else:
                a, b = x0, x1
            for x in range(a, b + 1):
                edge = x in (a, b)
                col = dark if edge else (light if x == a + 1 else wood)
                p[x, y] = col + (255,)
        if not tip:
            for y in (5, 6):  # iron band
                for x in range(x0 - 1, x1 + 2):
                    p[x, y] = (iron_hi if y == 5 else iron) + (255,)
            for y in (11, 13):  # grain
                p[7, y] = dark + (255,)
        return im.resize((48, 48), Image.NEAREST)
    os.makedirs(OUT, exist_ok=True)
    cell(True).save(os.path.join(OUT, 'gate_tip.png'))
    cell(False).save(os.path.join(OUT, 'gate.png'))
    print('saved gate_tip.png, gate.png')


GAS_FRAMES = (0xa905, 0xa95b, 0xa9b1)


def gas_frames():
    """A sickly green cloud of overlapping puffs; each frame shifts and swells them."""
    import math, random
    dark, mid, light, glow = (110, 170, 30), (160, 220, 50), (210, 250, 110), (240, 255, 170)
    for f, addr in enumerate(GAS_FRAMES):
        _, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
        W, H = w * 4 * 10 // 4, h * 10 // 4  # 1 art pixel = 4 HD pixels
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rnd = random.Random(7)
        puffs = []
        for i in range(9):
            a = i / 9 * 2 * math.pi + f * 0.7
            r = (0.18 + 0.12 * rnd.random()) * min(W, H) * (1 + 0.12 * math.sin(f * 2.1 + i))
            cx = W / 2 + math.cos(a) * W * 0.22 + rnd.uniform(-2, 2)
            cy = H / 2 + math.sin(a) * H * 0.2 + rnd.uniform(-2, 2)
            puffs.append((cx, cy, r))
        puffs.append((W / 2, H / 2, min(W, H) * 0.3))
        # translucent layers, each on its own canvas so overlaps don't stack up
        for col, grow, dy, alpha in ((dark, 1.0, 1.0, 95), (mid, 0.78, 0.0, 120), (light, 0.45, -1.0, 140)):
            layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            for cx, cy, r in puffs:
                rr = r * grow
                ld.ellipse((cx - rr, cy - rr + dy, cx + rr, cy + rr + dy), fill=col + (alpha,))
            im.alpha_composite(layer)
        for i in range(5):  # wisps curling off the edge
            a = rnd.uniform(0, 2 * math.pi) + f * 0.9
            for k in range(6):
                t = k / 5
                x = W / 2 + math.cos(a + t * 1.4) * W * (0.3 + 0.18 * t)
                y = H / 2 + math.sin(a + t * 1.4) * H * (0.28 + 0.16 * t)
                rr = 2.2 * (1 - t) + 0.6
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=mid + (int(110 * (1 - t)) + 20,))
        im = im.resize((W * 4, H * 4), Image.NEAREST)
        im.save(os.path.join(gs.ASSETS, 'sprites', f'{addr:04x}.png'))
    print('saved gas frames', ' '.join(f'{a:04x}' for a in GAS_FRAMES))


ARROW_UP_LEFT, ARROW_UP_RIGHT = 0xa7a9, 0xcfd9


def arrow_frames():
    """Diagonal arrow, head at the top-left, in 1/4-scale art pixels."""
    _, w, h = next(r for r in gs.gfx.sprites() if r[0] == ARROW_UP_LEFT)
    W, H = w * 4 * 10 // 4, h * 10 // 4  # 30 x 20
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    shaft, shaft_dark = (150, 96, 46, 255), (82, 50, 22, 255)
    stone, stone_hi = (120, 124, 132, 255), (200, 204, 210, 255)
    feather, feather_dk = (232, 232, 220, 255), (190, 60, 50, 255)
    tip, tail = (4, 3), (W - 5, H - 3)
    d.line((tip[0] + 3, tip[1] + 2, tail[0], tail[1]), fill=shaft_dark, width=3)
    d.line((tip[0] + 3, tip[1] + 2, tail[0], tail[1]), fill=shaft, width=1)
    d.polygon([(tip[0], tip[1]), (tip[0] + 6, tip[1] + 1), (tip[0] + 2, tip[1] + 5)], fill=stone)
    d.line((tip[0], tip[1], tip[0] + 4, tip[1] + 1), fill=stone_hi)
    for k, col in ((0, feather), (2, feather_dk), (4, feather)):  # fletching
        x, y = tail[0] - 4 + k * 0.6, tail[1] - 3 + k * 0.4
        d.line((x, y, x - 1, y - 3), fill=col, width=1)
        d.line((x, y, x - 3, y - 1), fill=col, width=1)
    im = im.resize((W * 4, H * 4), Image.NEAREST)
    im.save(os.path.join(gs.ASSETS, 'sprites', f'{ARROW_UP_LEFT:04x}.png'))
    im.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(gs.ASSETS, 'sprites', f'{ARROW_UP_RIGHT:04x}.png'))
    print('saved arrow', f'{ARROW_UP_LEFT:04x}', f'{ARROW_UP_RIGHT:04x}')


PICK_FRAMES = ((0xa741, 0), (0xa753, 270), (0xa765, 180), (0xa777, 90))  # head direction, degrees


def pick_frames():
    """Pickaxe with the handle along x and the iron head across its right end; rotated per frame."""
    S = 20  # art pixels, square
    base = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    wood, wood_dk = (150, 96, 46, 255), (82, 50, 22, 255)
    iron, iron_hi, iron_dk = (130, 134, 142, 255), (205, 208, 214, 255), (60, 62, 70, 255)
    d.rectangle((2, 9, 15, 11), fill=wood_dk)  # handle
    d.line((3, 10, 14, 10), fill=wood)
    d.polygon([(13, 2), (17, 6), (17, 14), (13, 18), (15, 10)], fill=iron_dk)  # curved head
    d.polygon([(14, 3), (16, 6), (16, 14), (14, 17), (15, 10)], fill=iron)
    d.line((15, 5, 15, 9), fill=iron_hi)
    for addr, angle in PICK_FRAMES:
        _, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
        frame = base.rotate(angle, resample=Image.NEAREST)
        W, H = w * 4 * 10, h * 10
        frame.resize((W, H), Image.NEAREST).save(os.path.join(gs.ASSETS, 'sprites', f'{addr:04x}.png'))
    print('saved pick frames', ' '.join(f'{a:04x}' for a, _ in PICK_FRAMES))


def main():
    if '--pick' in sys.argv:
        pick_frames()
        return
    if '--arrow' in sys.argv:
        arrow_frames()
        return
    if '--gas' in sys.argv:
        gas_frames()
        return
    if '--gate' in sys.argv:
        gate_tiles()
        return
    if '--recut' in sys.argv:
        cut(Image.open(RAW).convert('RGB'))
        return
    raw = gs.gemini.generate(PROMPT, [guide(), Image.open(gs.STYLE_REF)], aspect='16:9', label='log')
    raw.save(RAW)
    cut(raw)


if __name__ == '__main__':
    main()
