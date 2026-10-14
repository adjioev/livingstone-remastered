"""Generate HD frames for the hero (Livingstone) with Gemini.

    python tools/gen_sprites.py              # generate sheet, cut, save frames
    python tools/gen_sprites.py --recut      # re-cut the last raw sheet without calling the API

All 16 right-facing frames go into one 4x4 sheet so the style stays consistent. Each
cell is keyed (magenta background), fitted onto the original frame's bounding box
(same height, same feet line, same centre) and saved as
remaster/assets/sprites/XXXX.png. The 14 left-facing frames are exact mirrors in the
original, so they are produced by flipping.
"""
import os, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]  # extract_gfx reads argv at import
import extract_gfx as gfx  # noqa: E402
import gemini  # noqa: E402
sys.argv = _argv

ASSETS = os.path.join(ROOT, 'remaster', 'assets')
STYLE_REF = os.path.join(ASSETS, 'ref', 'style.png')
RAW = os.path.join(ASSETS, 'raw', 'hero_sheet.png')
GUIDE = os.path.join(ASSETS, 'guides', 'hero_sheet.png')

KEY = (255, 0, 255)
CELL, ZOOM = 256, 10           # guide: 4x4 cells of 256 px, frame drawn at 10x
FW, FH = 24, 23                # original frame size in pixels
OFF = ((CELL - FW * ZOOM) // 2, (CELL - FH * ZOOM) // 2)

# (right-facing frame, mirrored left-facing frame or None, pose for the prompt)
FRAMES = [
    (0x8e69, 0xc831, 'standing still, facing right'),
    (0x8ef5, 0xc8bd, 'walking right, legs apart'),
    (0x8f81, 0xc949, 'walking right, legs passing'),
    (0x900d, 0xc9d5, 'crouched low, crawling right'),
    (0x9099, 0xcaed, 'leaping right, long stride in the air'),
    (0x9125, 0xca61, 'jumping right, knees tucked'),
    (0x91b1, 0xcb79, 'throwing: arm raised back behind the head'),
    (0x923d, 0xcc05, 'throwing: arm thrust forward to the right'),
    (0x92c9, 0xcc91, 'kneeling and throwing forward'),
    (0x9355, 0xcd1d, 'knocked out, lying flat on the ground, hat fallen off'),
    (0x93e1, 0xcec1, 'crouching, dazed, little stars around the head'),
    (0x946d, 0xcf4d, 'standing dazed, little stars around the head'),
    (0x94f9, 0xcda9, 'diving / tumbling forward horizontally'),
    (0x9585, 0xce35, 'tumbling, body horizontal, legs back'),
    (0x9611, None, 'facing the viewer, both arms raised in triumph'),
    (0x969d, None, 'facing the viewer, both arms raised high, cheering'),
]

PROMPT = """Redraw this 4x4 sprite sheet of a retro platform-game hero as high-detail modern pixel art.

Image 1 is the LAYOUT: 16 animation frames of the same character on a magenta background.
Image 2 is the STYLE reference: the explorer on the right of that picture is this character
(safari hat, khaki shirt and shorts, brown boots, green backpack). Match its look, shading and palette.

Frames, left to right, top to bottom:
{poses}

Rules:
- Keep the 4x4 grid. Each frame stays in its own cell, same position, same pose, same size: the
  character's head, feet and outline must cover the same area as the original frame.
- The character always faces RIGHT (frames 15 and 16 face the viewer).
- Identical character design, proportions and colours in all 16 frames.
- Background must be flat pure magenta #FF00FF everywhere. No shadows, no ground, no scenery, no
  grid lines, no text, no numbers, no extra objects."""


def frame_image(addr):
    p = next(r for r in gfx.sprites() if r[0] == addr)
    return gfx.render_sprite(*p, gfx.PAL[0])


def build_guide():
    sheet = Image.new('RGB', (CELL * 4, CELL * 4), KEY)
    for i, (addr, _, _) in enumerate(FRAMES):
        im = frame_image(addr).convert('RGBA')
        # render_sprite paints transparent pixels dark; make them magenta
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                if px[x, y][:3] == (40, 40, 60):
                    px[x, y] = KEY + (255,)
        im = im.convert('RGB').resize((FW * ZOOM, FH * ZOOM), Image.NEAREST)
        sheet.paste(im, ((i % 4) * CELL + OFF[0], (i // 4) * CELL + OFF[1]))
    os.makedirs(os.path.dirname(GUIDE), exist_ok=True)
    sheet.save(GUIDE)
    return sheet


def key_out(im):
    """Magenta -> transparent, with a soft edge and de-spill."""
    im = im.convert('RGBA')
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, _ = px[x, y]
            d = ((r - 255) ** 2 + g ** 2 + (b - 255) ** 2) ** 0.5
            if d < 110:
                px[x, y] = (0, 0, 0, 0)
            elif d < 170 and r > g and b > g:
                a = int(255 * (d - 110) / 60)
                px[x, y] = (min(r, g + 40), g, min(b, g + 40), a)
    return im


def orig_bbox(addr):
    im = frame_image(addr).convert('RGB')
    px = im.load()
    pts = [(x, y) for y in range(FH) for x in range(FW) if px[x, y] != (40, 40, 60)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def fit(cell, addr, scale):
    """Place the generated figure onto the original frame's bounding box."""
    box = cell.getbbox()
    out = Image.new('RGBA', (FW * scale, FH * scale), (0, 0, 0, 0))
    if not box:
        return out
    fig = cell.crop(box)
    x0, y0, x1, y1 = (v * scale for v in orig_bbox(addr))
    k = (y1 - y0) / fig.height
    if fig.width * k > (x1 - x0) * 1.35:  # keep wide poses inside the frame
        k = (x1 - x0) * 1.35 / fig.width
    fig = fig.resize((max(1, round(fig.width * k)), max(1, round(fig.height * k))), Image.LANCZOS)
    cx = (x0 + x1) // 2
    out.alpha_composite(fig, (max(0, min(out.width - fig.width, cx - fig.width // 2)), max(0, y1 - fig.height)))
    return out


def cut(sheet):
    sheet = sheet.resize((CELL * 4, CELL * 4), Image.LANCZOS)
    os.makedirs(os.path.join(ASSETS, 'sprites'), exist_ok=True)
    for i, (addr, mirror, _) in enumerate(FRAMES):
        cx, cy = (i % 4) * CELL, (i // 4) * CELL
        cell = key_out(sheet.crop((cx, cy, cx + CELL, cy + CELL)))
        frame = fit(cell, addr, ZOOM)
        frame.save(os.path.join(ASSETS, 'sprites', f'{addr:04x}.png'))
        if mirror:
            frame.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(ASSETS, 'sprites', f'{mirror:04x}.png'))
    print(f'saved {len(FRAMES)} frames + {sum(1 for f in FRAMES if f[1])} mirrored')


def main():
    if '--recut' in sys.argv:
        cut(Image.open(RAW).convert('RGB'))
        return
    guide = build_guide()
    poses = '\n'.join(f'{i + 1}. {pose}' for i, (_, _, pose) in enumerate(FRAMES))
    sheet = gemini.generate(PROMPT.format(poses=poses), [guide, Image.open(STYLE_REF)],
                            aspect='1:1', label='hero sheet')
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    sheet.save(RAW)
    cut(sheet)


if __name__ == '__main__':
    main()
