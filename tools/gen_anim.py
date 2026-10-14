"""Generate HD animation cycles that replace a sprite's few original frames.

    python tools/gen_anim.py drum dance       # generate
    python tools/gen_anim.py --recut drum     # re-cut the saved raw sheet

Each cycle is one Gemini sheet (cols x rows of frames, reading order). Frames are cut
by empty gaps, scaled with ONE common scale (tallest frame = the original sprite's
height) and placed on a common feet line and centre, so the figure doesn't jump between
frames. Output: remaster/assets/anim/<name>_<i>.png; the renderer plays them for every
sprite listed in its anim table.
"""
import os, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402
import gen_bank as gb  # noqa: E402  (merged_runs)

OUT = os.path.join(gs.ASSETS, 'anim')
RAW = os.path.join(gs.ASSETS, 'raw')

# name -> (cols, rows, aspect, fit to sprite, identity reference, poses, extra)
ANIMS = {
    'drum': (3, 2, '16:9', 0xae8d, os.path.join(gs.ASSETS, 'sprites', 'ae8d.png'), [
        'both hands raised high above the drum, body up',
        'RIGHT hand strikes the drum, left hand up, body dips',
        'both hands at shoulder height, bouncing',
        'LEFT hand strikes the drum, right hand up, body dips',
        'both hands strike the drum together, knees bent, lowest',
        'both hands raised, body up again, happy shout',
    ], 'A cheerful tribal drummer in a big round yellow ceremonial mask, red body, a yellow drum with a '
       'green band held in front, FACING THE VIEWER, standing in the same spot in every frame.'),
    'dance': (4, 2, '16:9', 0xb8df, os.path.join(gs.ASSETS, 'sprites', 'b8df.png'), [
        'arms raised gracefully to both sides, hips swaying to the left',
        'arms curving above the head, hips centred',
        'arms raised, hips swaying to the right',
        'one arm up, one arm forward, turning slightly, skirt swirling',
        'arms out wide, hips swaying to the left, skirt flowing',
        'hands together above the head, hips centred',
        'arms out, hips swaying to the right, skirt flowing',
        'graceful spin, skirt fanning out',
    ], 'A cheerful belly dancer in a colourful stage costume (decorated top, hip scarf with little gold '
       'coins, long flowing skirt, gold bracelets), FACING THE VIEWER, dancing in the same spot.'),
}

PROMPT = """Draw a {n}-frame looping animation sprite sheet of this game character, in a {cols} x {rows} grid,
frames in reading order (left to right, top row first).

Image 1 is the character: keep exactly the same design, colours, proportions and pixel-art style.
{who}

Frames:
{poses}

Rules:
- Same character size in every frame: head and feet at the same height, centred in the cell.
- Smooth looping motion: frame {n} leads back into frame 1.
- Flat pure magenta #FF00FF background everywhere, no ground, no shadow, no grid lines, no text."""


def figures(sheet, cols, rows):
    """Row bands by empty gaps; within a band, frames by gaps, or an even split when
    neighbouring frames touch (outstretched arms)."""
    im = gs.key_out(sheet)
    w, h = im.size
    a = im.getchannel('A').load()
    bands = gb.merged_runs([any(a[x, y] > 128 for x in range(0, w, 2)) for y in range(h)], h // 60, h // 10)
    if len(bands) != rows:
        bands = [(h * i // rows, h * (i + 1) // rows) for i in range(rows)]
    figs = []
    for y0, y1 in bands:
        spans = gb.merged_runs([any(a[x, y] > 128 for y in range(y0, y1, 2)) for x in range(w)], w // 80, w // 40)
        if len(spans) != cols:
            spans = [(w * c // cols, w * (c + 1) // cols) for c in range(cols)]
        figs += [im.crop((x0, y0, x1, y1)) for x0, x1 in spans]
    return [gb.largest_blob(f) for f in figs]


def sprite_bbox(addr):
    """Opaque box of an original sprite, in HD pixels."""
    im = gs.gfx.render_sprite(*next(r for r in gs.gfx.sprites() if r[0] == addr), gs.gfx.PAL[0]).convert('RGB')
    px = im.load()
    pts = [(x, y) for y in range(im.height) for x in range(im.width) if px[x, y] != (40, 40, 60)]
    return (min(p[0] for p in pts) * gs.ZOOM, min(p[1] for p in pts) * gs.ZOOM,
            (max(p[0] for p in pts) + 1) * gs.ZOOM, (max(p[1] for p in pts) + 1) * gs.ZOOM)


def cut(name, sheet):
    cols, rows, _, fit_to, _, poses, _ = ANIMS[name]
    figs = figures(sheet, cols, rows)
    x0, y0, x1, y1 = sprite_bbox(fit_to)
    _, w, h = next(r for r in gs.gfx.sprites() if r[0] == fit_to)
    k = (y1 - y0) / max(f.height for f in figs)
    os.makedirs(OUT, exist_ok=True)
    for i, f in enumerate(figs):
        f = f.resize((max(1, round(f.width * k)), max(1, round(f.height * k))), Image.LANCZOS)
        out = Image.new('RGBA', (w * 4 * gs.ZOOM, h * gs.ZOOM), (0, 0, 0, 0))
        cx = (x0 + x1) // 2
        out.alpha_composite(f, (max(0, min(out.width - f.width, cx - f.width // 2)), max(0, y1 - f.height)))
        out.save(os.path.join(OUT, f'{name}_{i}.png'))
    print(f'{name}: {len(figs)} frames')


def generate(name):
    cols, rows, aspect, _, ref, poses, who = ANIMS[name]
    text = PROMPT.format(n=len(poses), cols=cols, rows=rows, who=who,
                         poses='\n'.join(f'{i + 1}. {p}' for i, p in enumerate(poses)))
    sheet = gs.gemini.generate(text, [Image.open(ref)], aspect=aspect, label=f'anim {name}')
    sheet.save(os.path.join(RAW, f'anim_{name}.png'))
    cut(name, sheet)


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or list(ANIMS)
    for n in names:
        if '--recut' in sys.argv:
            cut(n, Image.open(os.path.join(RAW, f'anim_{n}.png')).convert('RGB'))
        else:
            generate(n)


if __name__ == '__main__':
    main()
