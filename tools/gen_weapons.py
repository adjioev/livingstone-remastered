"""HD weapons and projectiles.

    python tools/gen_weapons.py            # poles (procedural) + Gemini sheet
    python tools/gen_weapons.py --poles    # only the procedural poles (no API call)
    python tools/gen_weapons.py --recut    # re-cut the last raw Gemini sheet

Pole: the vaulting pole is drawn by the game as a 1-px bent line in 12 frames. We redraw
that exact line as a thick bamboo stroke, so the bend matches the game frame for frame.
Everything else (boomerang, knife, grenade, explosion, spear, dart) comes from one
Gemini sheet; mirrored/flipped variants are made the same way the original makes them.
"""
import os, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402  (paths, gfx, gemini, key_out)
import gen_walk as gw  # noqa: E402  (runs: gap finding)

SCALE = 10
OUT = os.path.join(gs.ASSETS, 'sprites')
RAW = os.path.join(gs.ASSETS, 'raw', 'weapons_sheet.png')

POLES = [0x9787, 0x9795, 0x97f7, 0x9899, 0x9963, 0x9a25, 0x9acb,
         0xd607, 0xd669, 0xd70b, 0xd7d5, 0xd897]

# (source frame, description, [(derived frame, transform)])
H, V, HV = 'h', 'v', 'hv'
SHEET = [
    (0x9729, 'wooden boomerang, a right-angle "L" shape with the corner at the top right',
     [(0x9759, H), (0x9739, V), (0x9749, HV)]),
    (0x9769, 'throwing knife flying right: dark handle on the left, steel blade pointing right', [(0xc281, H)]),
    (0x9777, 'round black iron grenade with a short lit fuse', []),
    (0x9b6f, 'explosion, first frame: small puff of fire and smoke', []),
    (0x9bef, 'explosion, middle frame: big ball of fire and smoke', []),
    (0x9c6f, 'explosion, last frame: fire burst with flying sparks and debris', []),
    (0xa795, 'native wooden spear flying horizontally, stone tip pointing left', [(0xcff3, H)]),
    (0xa789, 'wooden arrow flying right, arrowhead on the right, fletching on the left', [(0xc543, H)]),
]

PROMPT = """Draw a sprite sheet of {n} game items as high-detail modern pixel art, in the style of image 2
(an HD remake of a 1986 jungle adventure game).

Image 1 is the LAYOUT: the original low-resolution items on magenta, one per cell, 4 columns x 2 rows.
Keep each item in its cell, in the same order, same orientation and same proportions:
{items}

Rules:
- Flat pure magenta #FF00FF background everywhere, no shadows, no ground, no grid lines, no text.
- Each item fills most of its cell; clear empty magenta space between items.
- Same lighting and outline style for all items."""


# ---------------------------------------------------------------- poles

WOOD_DARK, WOOD, WOOD_LIGHT, NODE = (70, 42, 18, 255), (196, 150, 78, 255), (238, 210, 140, 255), (120, 82, 36, 255)


def chain(pts):
    """Order line pixels end to end (start at an end point, walk to nearest neighbour)."""
    left = set(pts)
    def nbrs(q):
        return [(q[0] + dx, q[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx or dy) and (q[0] + dx, q[1] + dy) in left]
    cur = min(pts, key=lambda q: len(nbrs(q)))
    out = []
    while left:
        out.append(cur)
        left.discard(cur)
        if not left:
            break
        near = nbrs(cur)
        cur = min(near or left, key=lambda q: (q[0] - cur[0]) ** 2 + (q[1] - cur[1]) ** 2)
    return out


def smooth(c, k=3):
    """Moving average so the 1-px staircase becomes a smooth bend; ends stay put."""
    out = []
    for i in range(len(c)):
        lo, hi = max(0, i - k), min(len(c), i + k + 1)
        out.append((sum(p[0] for p in c[lo:hi]) / (hi - lo), sum(p[1] for p in c[lo:hi]) / (hi - lo)))
    return out


def pole(addr):
    p, w, h = next(r for r in gfx_sprites() if r[0] == addr)
    pts = [(x, y) for y in range(h) for x in range(w * 4)
           if (gs.gfx.img[p + 2 + y * w + x // 4] >> (6 - 2 * (x % 4))) & 3]
    c = [((x + 0.5) * SCALE, (y + 0.5) * SCALE) for x, y in smooth(chain(pts))]
    if len(c) == 1:
        c = c * 2
    im = Image.new('RGBA', (w * 4 * SCALE, h * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line(c, fill=WOOD_DARK, width=13, joint='curve')
    d.line(c, fill=WOOD, width=8, joint='curve')
    d.line([(x - 1, y - 2) for x, y in c], fill=WOOD_LIGHT, width=2, joint='curve')
    for x, y in c[6::14]:  # bamboo nodes
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=NODE)
    return im


def gfx_sprites():
    return gs.gfx.sprites()


# ---------------------------------------------------------------- Gemini sheet

CELL = 256


def guide():
    sheet = Image.new('RGB', (CELL * 4, 576), gs.KEY)
    for i, (addr, _, _) in enumerate(SHEET):
        im = item_image(addr)
        z = max(1, min((CELL - 40) // im.width, (CELL - 40) // im.height))
        im = im.resize((im.width * z, im.height * z), Image.NEAREST)
        sheet.paste(im, ((i % 4) * CELL + (CELL - im.width) // 2, (i // 4) * CELL + (CELL - im.height) // 2))
    sheet.save(os.path.join(gs.ASSETS, 'guides', 'weapons_sheet.png'))
    return sheet


def item_image(addr):
    """Original frame with transparent pixels shown as magenta."""
    p, w, h = next(r for r in gfx_sprites() if r[0] == addr)
    im = gs.gfx.render_sprite(p, w, h, gs.gfx.PAL[0]).convert('RGB')
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if px[x, y] == (40, 40, 60):
                px[x, y] = gs.KEY
    return im


def fit_box(fig, addr):
    """Scale the figure into the original frame's opaque box (contain), centred."""
    im = item_image(addr)
    px = im.load()
    pts = [(x, y) for y in range(im.height) for x in range(im.width) if px[x, y] != gs.KEY]
    x0, y0 = min(p[0] for p in pts) * SCALE, min(p[1] for p in pts) * SCALE
    x1, y1 = (max(p[0] for p in pts) + 1) * SCALE, (max(p[1] for p in pts) + 1) * SCALE
    k = min((x1 - x0) / fig.width, (y1 - y0) / fig.height)
    fig = fig.resize((max(1, round(fig.width * k)), max(1, round(fig.height * k))), Image.LANCZOS)
    out = Image.new('RGBA', (im.width * SCALE, im.height * SCALE), (0, 0, 0, 0))
    out.alpha_composite(fig, ((x0 + x1 - fig.width) // 2, (y0 + y1 - fig.height) // 2))
    return out


def transform(im, how):
    if 'h' in how:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if 'v' in how:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    return im


def figures(sheet, cols=4, rows=2):
    """Row bands by empty gaps, then equal-width columns (explosion sparks are separate
    blobs, so gap-splitting columns would over-split)."""
    im = gs.key_out(sheet)
    w, h = im.size
    a = im.getchannel('A').load()
    bands = [r for r in gw.runs([any(a[x, y] > 128 for x in range(0, w, 2)) for y in range(h)]) if r[1] - r[0] > h // 20]
    if len(bands) != rows:
        bands = [(h * i // rows, h * (i + 1) // rows) for i in range(rows)]
    figs = []
    for y0, y1 in bands:
        for c in range(cols):
            cell = im.crop((w * c // cols, y0, w * (c + 1) // cols, y1))
            figs.append(cell.crop(cell.getbbox()))
    return figs


def cut(sheet):
    figs = figures(sheet)
    for (addr, _, derived), fig in zip(SHEET, figs):
        hd = fit_box(fig, addr)
        hd.save(os.path.join(OUT, f'{addr:04x}.png'))
        for other, how in derived:
            transform(hd, how).save(os.path.join(OUT, f'{other:04x}.png'))
    print(f'saved {len(SHEET)} items + {sum(len(d) for _, _, d in SHEET)} variants')


def main():
    os.makedirs(OUT, exist_ok=True)
    for a in POLES:
        pole(a).save(os.path.join(OUT, f'{a:04x}.png'))
    print(f'saved {len(POLES)} pole frames')
    if '--poles' in sys.argv:
        return
    if '--recut' in sys.argv:
        cut(Image.open(RAW).convert('RGB'))
        return
    items = '\n'.join(f'{i + 1}. {d}' for i, (_, d, _) in enumerate(SHEET))
    sheet = gs.gemini.generate(PROMPT.format(n=len(SHEET), items=items),
                               [guide(), Image.open(gs.STYLE_REF)], aspect='16:9', label='weapons')
    sheet.save(RAW)
    cut(sheet)


if __name__ == '__main__':
    main()
