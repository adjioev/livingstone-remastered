"""HD versions of the rest of the sprite bank, one Gemini sheet per family.

    python tools/gen_bank.py              # all sheets
    python tools/gen_bank.py A C          # only these sheets
    python tools/gen_bank.py --recut A    # re-cut saved raw sheets, no API call

Each sheet: originals laid out on magenta in a cols x rows grid -> Gemini redraws them
in the style reference -> rows found by empty gaps, columns split evenly -> each item
keyed and fitted into its original frame's box. Every bank sprite that is a mirror
image of a generated one gets the flipped HD frame.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_sprites as gs  # noqa: E402
import gen_weapons as gw  # noqa: E402  (item_image, fit_box, transform)

OUT = os.path.join(gs.ASSETS, 'sprites')

# name -> (cols, rows, aspect, [(sprite, description)])
SHEETS = {
    'A': (4, 4, '1:1', [
        (0x9cef, 'jungle bird flying right, wings up'), (0x9d51, 'same bird, wings spread'),
        (0x9db3, 'same bird, wings down'), (0x9e99, 'carnivorous plant, jaws open, leaning right'),
        (0x9f25, 'same carnivorous plant, jaws half open'), (0x9fb1, 'same carnivorous plant, facing the viewer'),
        (0xa131, 'red monkey sitting, facing right'), (0xa1ab, 'same red monkey, crouched'),
        (0xaa07, 'scorpion, tail raised'), (0xaa5d, 'same scorpion, walking'),
        (0xaab3, 'small green lizard running right'), (0xaadf, 'same lizard, other leg'),
        (0xad35, 'big yellow piranha fish, mouth open, facing right'), (0xad97, 'same piranha, mouth closed'),
        (0xadf9, 'flat yellow spiky crab / spider-like creature'), (0xae43, 'same creature, legs moved'),
    ]),
    'B': (4, 4, '1:1', [
        (0xa225, 'miner; redrawn in sheet N'), (0xa2ab, 'miner; redrawn in sheet N'),
        (0xa331, 'blowgun hunter; redrawn in sheet L'), (0xa3b1, 'blowgun hunter; redrawn in sheet L'),
        (0xa431, 'tribal warrior with a raised club'), (0xa4b7, 'same warrior, striking'),
        (0xa53d, 'archer; redrawn in sheet L'), (0xa5b7, 'archer; redrawn in sheet L'),
        (0xa631, 'witch doctor in a green mask, arms up'), (0xa6b1, 'same witch doctor, arms down'),
        (0xae8d, 'dancing native with a drum, arm raised'), (0xaf13, 'same dancing native, other arm raised'),
        (0xb14d, 'barbarian; redrawn in sheet O'), (0xb1d3, 'barbarian; redrawn in sheet O'),
        (0xb2d7, 'green crouching jungle creature with a red hat'), (0xb34b, 'same creature, other pose'),
    ]),
    'C': (4, 3, '4:3', [
        (0xb447, 'tribal chief with a feathered headdress and a staff'),
        (0xb617, 'big-nosed hunter in a green hat running right'), (0xb6a3, 'same hunter, other step'),
        (0xb72f, 'same hunter, throwing'), (0xb099, 'mermaid; redrawn in sheet M'),
        (0xb0f3, 'same spirit, other pose'), (0xaf99, 'small swirling whirlwind / tornado'),
        (0xb8df, 'belly dancer, arms out (big); redrawn in sheet J'),
        (0xb7bb, 'long crocodile swimming LEFT (head and jaws on the left, tail on the right), mouth closed'),
        (0xb841, 'same crocodile facing left, mouth open'),
    ]),
    'D': (4, 4, '1:1', [
        (0xa03d, 'hanging oil lamp'), (0xa0b1, 'pair of glowing eyes in the dark, half closed'),
        (0xa0d1, 'same glowing eyes, open'), (0xa0f1, 'same glowing eyes, wide open'),
        (0xa111, 'same glowing eyes, blinking'), (0xa731, 'red coconut'),
        (0xa741, 'thrown pickaxe; gen_props.py --pick'), (0xa753, 'thrown pickaxe; gen_props.py --pick'),
        (0xa765, 'thrown pickaxe; gen_props.py --pick'), (0xa777, 'thrown pickaxe; gen_props.py --pick'),
        (0xa7a9, 'archer arrow; drawn by gen_props.py --arrow'), (0xa7c3, 'yellow puff of dust, small'),
        (0xa7f5, 'yellow puff of dust, medium'), (0xa827, 'yellow puff of dust, fading'),
        (0xab0b, 'loaf of bread (food)'), (0xabbd, 'clay water jug (water)'),
    ]),
    'E': (4, 4, '1:1', [
        (0xa859, 'small wooden mine cart'), (0xa8af, 'same mine cart, wheels turned'),
        (0xa905, 'poison gas; drawn by gen_props.py --gas'), (0xa95b, 'poison gas, gen_props --gas'),
        (0xa9b1, 'poison gas, gen_props --gas'), (0xab45, 'round yellow fruit'),
        (0xab7b, 'red and yellow treasure pot'), (0xabf7, 'small yellow bundle of supplies'),
        (0xac15, 'same bundle, turned'), (0xac33, 'red bat flying, wings up'),
        (0xac89, 'same red bat, wings level'), (0xacdf, 'same red bat, wings down'),
        (0xb259, 'red heart (extra life)'), (0xb26d, 'small green arrow pointing right'),
        (0xb27f, 'small green arrow pointing down'), (0xb2b5, 'tall green arrow pointing up'),
    ]),
    # Title-screen drummers, redone on their own: the first pass drew realistic side-on men,
    # the originals are squat masked figures facing the viewer.
    'G': (2, 1, '16:9', [
        (0xae8d, 'cartoon tribal drummer FACING THE VIEWER, short and stocky, wearing a huge round yellow '
                 'ceremonial mask with big eyes, red-painted body, a large yellow drum with a green band '
                 'held in front of the belly, RIGHT hand raised and waving, cartoon proportions like the '
                 'explorer in image 2'),
        (0xaf13, 'the exact same drummer, identical mask, body and drum, but the LEFT hand raised and waving'),
    ]),
    'F': (4, 3, '4:3', [
        (0xb547, 'fireball; redrawn in sheet Q'), (0xb56d, 'fireball; redrawn in sheet Q'),
        (0xb593, 'big red spider hanging'), (0xb5d5, 'same big spider, legs moved'),
        (0xb3bf, 'red snake slithering right'), (0xb403, 'same snake, other pose'),
        (0x9e15, 'falling water drops'), (0x9e41, 'same drops, lower'),
        (0x9e6d, 'same drops, lowest'), (0xb8c7, 'tiny dust puff'),
        (0xb8cf, 'tiny dust puff, smaller'), (0xb8d7, 'tiny dust puff, fading'),
    ]),
    # Chief and the gold the hero collects. Runs after B and uses its natives as the style.
    'H': (3, 1, '16:9', [
        (0xb447, 'cartoon tribal chief with a tall feather headdress and a carved staff, in exactly the '
                 'same cartoon style and proportions as the natives in image 2'),
        (0xabf7, 'gold; redrawn in sheet P'),
        (0xac15, 'the same gold bar with a bright sparkle / glint on it'),
    ]),
    # Ceiling lever switch (a077 is the mirror = other position). D drew it as an oil lamp.
    'I': (1, 1, '1:1', [
        (0xa03d, 'cave LEVER SWITCH hanging from the ceiling: a riveted iron mounting plate at the top, '
                 'a metal lever hanging down and tilted to the lower left, a round knob at its end. Not a lamp.'),
    ]),
    # Bonus scene when gold is collected; C wrongly described her as Stanley. c54f is the
    # mirror, so alternating the two frames makes her dance.
    'J': (1, 1, '1:1', [
        (0xb8df, 'cheerful cartoon BELLY DANCER woman facing the viewer, dancing with both arms raised to '
                 'the sides: long dark hair, colourful traditional stage costume with a decorated top, a long '
                 'flowing skirt and a hip scarf with little gold coins, gold bracelets, big smile. Same '
                 'cartoon pixel-art style as the explorer in image 2. A woman, not an explorer.'),
    ]),
    # Room 18: blowgun hunter (B drew him facing the wrong way), the archer (B drew a
    # shield warrior) and the arrow (was a dart).
    'L': (3, 2, '16:9', [
        (0xa331, 'cartoon tribal hunter kneeling, facing LEFT, aiming a long BLOWGUN horizontally to the '
                 'left with both hands at his mouth; same cartoon style as the natives in image 2'),
        (0xa3b1, 'the same blowgun hunter facing LEFT, cheeks puffed, blowing a dart out of the blowgun'),
        (0xa53d, 'cartoon tribal ARCHER standing, facing LEFT, holding a big curved wooden BOW raised high, '
                 'the arrow nocked and pointing diagonally UP-LEFT at 45 degrees into the sky, string '
                 'drawn back; same cartoon style'),
        (0xa5b7, 'the same archer facing LEFT, bow still raised at 45 degrees up-left, arrow just released, '
                 'no arrow on the bow'),
        (0xa789, 'a single wooden ARROW flying horizontally to the RIGHT: stone arrowhead on the right, '
                 'feather fletching on the left, long thin shaft'),
    ]),
    # Water mermaid (rusalka) in the river rooms; C drew a cobra.
    'M': (2, 1, '16:9', [
        (0xb099, 'cute cartoon fairy-tale mermaid character for a kids game, facing the viewer: long red '
                 'hair, big friendly smile, a modest long-sleeved yellow tunic, a green fish tail curling to '
                 'the right with a fin at the tip; same cartoon pixel-art style as the explorer in image 2'),
        (0xb0f3, 'the same mermaid, her tail flicking: the tail fin lifted a little higher'),
    ]),
    # Mine rooms: angry miners with pickaxes (B drew natives with spears).
    'N': (2, 1, '16:9', [
        (0xa225, 'cartoon ANGRY MINER walking to the RIGHT: dented miner helmet with a small lamp, bushy '
                 'beard, furious face, dirty patched work clothes and boots, swinging a big PICKAXE raised '
                 'over his shoulder; same cartoon pixel-art style as the explorer in image 2'),
        (0xa2ab, 'the same angry miner walking RIGHT, other step, pickaxe raised high ready to throw'),
    ]),
    # River rooms: barbarian with a club (B drew a running native).
    'O': (2, 1, '16:9', [
        (0xb14d, 'cartoon BARBARIAN running to the RIGHT: wild shaggy blond hair and beard, muscular, fur '
                 'loincloth and fur boots, holding a big wooden CLUB raised high in his raised hand; same '
                 'cartoon pixel-art style as the explorer in image 2'),
        (0xb1d3, 'the same barbarian running RIGHT, other step, the club swung forward and down'),
    ]),
    # Gold the hero collects: a chunky glowing nugget (the renderer adds pulsing rays).
    'P': (2, 1, '16:9', [
        (0xabf7, 'a big shiny GOLD NUGGET treasure: chunky rounded lump of bright yellow gold with a thick dark '
                 'outline, warm highlights and a curved shine mark, wider than tall, lying flat; bold pixel art'),
        (0xac15, 'the same gold nugget with a bright white sparkle star on its top edge'),
    ]),
    # Room 23 (temple fire pit): bouncing fireballs, not spiders.
    'Q': (2, 1, '16:9', [
        (0xb547, 'a FIREBALL: round ball of bright yellow-orange fire with a white-hot core, short flickering '
                 'flame tongues licking up from it, a few sparks; bold pixel art with a dark red outline'),
        (0xb56d, 'the same fireball a moment later: the flame tongues flicker into a different shape'),
    ]),
}

# Part of the generated sheet to use, as fractions (x0, y0, x1, y1), when the model repeats
# the layout: H came back with every item drawn twice, one row under the other.
CROP = {'H': (0, 0, 1, 0.5)}

# Sheets where stray bits (a dart beside a frame) are dropped: keep each cell's main figure.
SINGLE_BLOB = {'L', 'P', 'Q'}

# Sprites the model drew facing the wrong way: mirrored after cutting.
FLIP = {0xa53d, 0xa5b7, 0xb14d, 0xb1d3, 0xa225, 0xa2ab}

# When the hero sheet is the style reference: copy its look exactly, not just "cartoon".
HERO_STYLE_RULE = """- Match the explorer in image 2 EXACTLY in rendering: the same big chunky pixels (the same pixel
  size relative to the body), flat colour areas with only one or two shades per colour, a limited
  palette, a bold dark outline around everything, simple readable shapes, little fine detail.
  No smooth gradients, no painterly shading, no tiny details."""

# Style image per sheet (default: the HD scene reference) and extra instructions.
RAW_DIR = os.path.join(gs.ASSETS, 'raw')
STYLE = {'B': os.path.join(RAW_DIR, 'hero_sheet.png'), 'N': os.path.join(RAW_DIR, 'hero_sheet.png'),
         'O': os.path.join(RAW_DIR, 'hero_sheet.png'), 'P': os.path.join(RAW_DIR, 'hero_sheet.png'), 'Q': os.path.join(RAW_DIR, 'hero_sheet.png'), 'H': os.path.join(RAW_DIR, 'bank_B.png'),
         'L': os.path.join(RAW_DIR, 'bank_B.png'),
         'J': os.path.join(RAW_DIR, 'hero_sheet.png'), 'M': os.path.join(RAW_DIR, 'hero_sheet.png')}
EXTRA = {
    'B': 'Make them CARTOON characters: big heads, chunky simple shapes, friendly exaggerated faces, short '
         'stocky bodies, the same cartoon style and proportions as the explorer in image 2. Not realistic, '
         'not muscular.',
}

PROMPT = """Redraw this sprite sheet of {n} characters and items from a 1986 jungle adventure game as
high-detail modern pixel art in the style of image 2 (its HD remake).

Image 1 is the LAYOUT: the original low-resolution sprites on magenta, {cols} columns x {rows} rows.
Keep every sprite in its own cell, in the same order, facing the same way, same pose and same
proportions. Consecutive frames of the same creature must look identical apart from the pose.
{items}

Rules:
- Flat pure magenta #FF00FF background everywhere, no shadows, no ground, no grid lines, no text.
- Each sprite fills most of its cell, with empty magenta space between sprites.
- Same lighting and outline style for all sprites.
{extra}
{style_rule}"""


def bank_key(addr):
    p, w, h = next(r for r in gs.gfx.sprites() if r[0] == addr)
    return tuple(tuple((gs.gfx.img[p + 2 + y * w + x // 4] >> (6 - 2 * (x % 4))) & 3 for x in range(w * 4))
                 for y in range(h))


def mirrors_of(addr):
    m = tuple(r[::-1] for r in bank_key(addr))
    return [p for p, _, _ in gs.gfx.sprites() if p != addr and bank_key(p) == m]


def guide(cols, rows, aspect, items):
    W = 1024
    H = {'1:1': 1024, '4:3': 768, '16:9': 576}[aspect]
    cw, ch = W // cols, H // rows
    sheet = Image.new('RGB', (W, H), gs.KEY)
    for i, (addr, _) in enumerate(items):
        im = gw.item_image(addr)
        z = max(1, min((cw - 30) // im.width, (ch - 30) // im.height))
        im = im.resize((im.width * z, im.height * z), Image.NEAREST)
        sheet.paste(im, ((i % cols) * cw + (cw - im.width) // 2, (i // cols) * ch + (ch - im.height) // 2))
    return sheet


def merged_runs(mask, min_gap, min_len):
    spans = []
    for a, b in gw.gw.runs(mask):
        if spans and a - spans[-1][1] < min_gap:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    return [s for s in spans if s[1] - s[0] >= min_len]


def figures(sheet, cols, rows, n):
    """Items in reading order. The model doesn't always keep the grid (wide items span
    two cells, a row may hold 5), so find items by gaps in each row band; if the count
    doesn't come out right, fall back to the even grid."""
    im = gs.key_out(sheet)
    w, h = im.size
    a = im.getchannel('A').load()
    bands = merged_runs([any(a[x, y] > 128 for x in range(0, w, 2)) for y in range(h)], h // 60, h // 20)
    figs = []
    for y0, y1 in bands:
        cols_x = merged_runs([any(a[x, y] > 128 for y in range(y0, y1, 2)) for x in range(w)], w // 60, w // 40)
        figs += [im.crop((x0, y0, x1, y1)) for x0, x1 in cols_x]
    if len(figs) == n:
        return [f.crop(f.getbbox()) for f in figs]
    print(f'  gap cut found {len(figs)} items, expected {n}: using the even grid')
    return gw.figures(sheet, cols, rows)


def largest_blob(fig):
    """Keep only the biggest connected figure (the model sometimes adds extras)."""
    k = 4
    small = fig.getchannel('A').resize((max(1, fig.width // k), max(1, fig.height // k)))
    w, h = small.size
    a = small.load()
    seen, best = set(), None
    for y in range(h):
        for x in range(w):
            if a[x, y] < 64 or (x, y) in seen:
                continue
            stack, pts = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and a[nx, ny] >= 64:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if best is None or len(pts) > len(best):
                best = pts
    if not best:
        return fig
    xs, ys = [p[0] for p in best], [p[1] for p in best]
    box = (min(xs) * k, min(ys) * k, (max(xs) + 1) * k, (max(ys) + 1) * k)
    blob = Image.new('L', small.size, 0)
    keep_pts = set(best)
    blob.putdata([255 if (i % w, i // w) in keep_pts else 0 for i in range(w * h)])
    keep = blob.resize(fig.size, Image.NEAREST).filter(ImageFilter.MaxFilter(5))
    out = Image.new('RGBA', fig.size, (0, 0, 0, 0))
    out.paste(fig, (0, 0), keep)
    return out.crop(box)


def cut(name, sheet):
    cols, rows, _, items = SHEETS[name]
    if name in CROP:
        x0, y0, x1, y1 = CROP[name]
        sheet = sheet.crop((int(x0 * sheet.width), int(y0 * sheet.height), int(x1 * sheet.width), int(y1 * sheet.height)))
    figs = figures(sheet, cols, rows, len(items))
    if len(items) == 1 or name in SINGLE_BLOB:
        figs = [largest_blob(f) for f in figs]
    later = list(SHEETS)[list(SHEETS).index(name) + 1:]
    redone = {a for other in later for a, _ in SHEETS[other][3]}
    n = 0
    for (addr, _), fig in zip(items, figs):
        if addr in redone:  # a later sheet redraws this sprite
            continue
        if fig.width < 4 or fig.height < 4:
            print(f'{name}: {addr:04x} empty cell, skipped')
            continue
        if addr in FLIP:
            fig = fig.transpose(Image.FLIP_LEFT_RIGHT)
        hd = gw.fit_box(fig, addr)
        hd.save(os.path.join(OUT, f'{addr:04x}.png'))
        for m in mirrors_of(addr):
            hd.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(OUT, f'{m:04x}.png'))
            n += 1
    print(f'{name}: {len(items)} sprites + {n} mirrored')


def generate(name):
    cols, rows, aspect, items = SHEETS[name]
    g = guide(cols, rows, aspect, items)
    g.save(os.path.join(gs.ASSETS, 'guides', f'bank_{name}.png'))
    desc = '\n'.join(f'{i + 1}. {d}' for i, (_, d) in enumerate(items))
    style = Image.open(STYLE.get(name, gs.STYLE_REF))
    style_rule = HERO_STYLE_RULE if STYLE.get(name) == STYLE.get('B') else ''
    prompt = PROMPT.format(n=len(items), cols=cols, rows=rows, items=desc, extra=EXTRA.get(name, ''),
                           style_rule=style_rule)
    sheet = gs.gemini.generate(prompt, [g, style], aspect=aspect, label=f'sheet {name}')
    sheet.save(os.path.join(gs.ASSETS, 'raw', f'bank_{name}.png'))
    cut(name, sheet)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = args or list(SHEETS)
    os.makedirs(OUT, exist_ok=True)
    if '--recut' in sys.argv:
        for n in names:
            cut(n, Image.open(os.path.join(gs.ASSETS, 'raw', f'bank_{n}.png')).convert('RGB'))
        return
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(generate, names))


if __name__ == '__main__':
    main()
