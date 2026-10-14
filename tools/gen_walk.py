"""Generate an 8-frame HD walk cycle for the hero with Gemini.

    python tools/gen_walk.py            # generate + cut
    python tools/gen_walk.py --recut    # re-cut the last raw sheet

The original walk is only 3 frames (8ef5, 8e69, 8f81). The remaster plays this
cycle instead while the game shows those frames (see Renderer). Output:
remaster/assets/anim/walk_r_0..7.png, fitted to the original walk frame's box.
Needs the hero frames from gen_sprites.py as the identity reference.
"""
import os, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402  (sets up paths, gfx, gemini)

RAW = os.path.join(gs.ASSETS, 'raw', 'hero_walk.png')
OUT = os.path.join(gs.ASSETS, 'anim')
COLS, ROWS = 4, 2
FIT_TO = 0x8ef5                              # original walk frame: box for every cycle frame

POSES = [
    'contact: right leg stretched forward, heel touching the ground, left leg behind',
    'down: weight on the right leg, knee bent, body lowest',
    'passing: left leg swinging past the right leg',
    'up: pushing off the right foot, body highest, left leg forward in the air',
    'contact: left leg stretched forward, heel touching the ground, right leg behind',
    'down: weight on the left leg, knee bent, body lowest',
    'passing: right leg swinging past the left leg',
    'up: pushing off the left foot, body highest, right leg forward in the air',
]

PROMPT = """Draw an 8-frame walk cycle sprite sheet for this platform-game hero, walking to the RIGHT.

Image 1 shows the hero's existing animation frames: keep exactly the same character, art style,
pixel-art detail, outline, colours and proportions (safari hat, khaki shirt and shorts, brown boots,
green backpack).

Layout: a 4x2 grid of equal square cells on a flat pure magenta #FF00FF background, frames in this
order (left to right, top row then bottom row):
{poses}

Rules:
- Same character size in every cell: the hat top and the feet line at the same height in all frames.
- Side view facing right, smooth natural walk, arms swinging opposite to the legs.
- Flat pure magenta #FF00FF background everywhere, no ground, no shadow, no grid lines, no text."""


def runs(mask):
    """[start, end) spans where mask is true."""
    spans, start = [], None
    for i, v in enumerate(mask + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            spans.append((start, i))
            start = None
    return spans


def figures(sheet):
    """Find the 8 figures by empty gaps (the model doesn't keep cells exactly)."""
    im = gs.key_out(sheet)
    alpha = im.getchannel('A')
    w, h = im.size
    a = alpha.load()
    rows = [r for r in runs([any(a[x, y] > 128 for x in range(0, w, 2)) for y in range(h)]) if r[1] - r[0] > h // 10]
    figs = []
    for y0, y1 in rows:
        cols = [c for c in runs([any(a[x, y] > 128 for y in range(y0, y1, 2)) for x in range(w)]) if c[1] - c[0] > w // 40]
        figs += [im.crop((x0, y0, x1, y1)) for x0, x1 in cols]
    if len(figs) != COLS * ROWS:
        sys.exit(f'expected {COLS * ROWS} figures, found {len(figs)}; try --recut after fixing, or regenerate')
    return [f.crop(f.getbbox()) for f in figs]


def cut(sheet):
    figs = figures(sheet)
    # One scale for all frames (tallest figure = original walk frame height) so the
    # body bob of the cycle survives; feet on the original feet line.
    x0, y0, x1, y1 = (v * gs.ZOOM for v in gs.orig_bbox(FIT_TO))
    k = (y1 - y0) / max(f.height for f in figs)
    os.makedirs(OUT, exist_ok=True)
    for i, f in enumerate(figs):
        f = f.resize((round(f.width * k), round(f.height * k)), Image.LANCZOS)
        out = Image.new('RGBA', (gs.FW * gs.ZOOM, gs.FH * gs.ZOOM), (0, 0, 0, 0))
        cx = (x0 + x1) // 2
        out.alpha_composite(f, (max(0, min(out.width - f.width, cx - f.width // 2)), max(0, y1 - f.height)))
        out.save(os.path.join(OUT, f'walk_r_{i}.png'))
    print(f'saved {len(figs)} walk frames to {OUT}')


def main():
    if '--recut' in sys.argv:
        cut(Image.open(RAW).convert('RGB'))
        return
    hero = Image.open(os.path.join(gs.ASSETS, 'raw', 'hero_sheet.png'))
    poses = '\n'.join(f'{i + 1}. {p}' for i, p in enumerate(POSES))
    sheet = gs.gemini.generate(PROMPT.format(poses=poses), [hero], aspect='16:9', label='walk cycle')
    sheet.save(RAW)
    cut(sheet)


if __name__ == '__main__':
    main()
