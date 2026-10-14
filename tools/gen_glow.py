"""Glow masks for the painted crystals in dark rooms.

    python tools/gen_glow.py              # all dark rooms
    python tools/gen_glow.py 09 2e        # only these
    python tools/gen_glow.py --preview OUT_DIR 09 2e

Crystals were invented by the image model, so the original has no tiles for them: they
are found in the HD background by colour (bright, saturated cyan / blue / violet), away
from water cells. The mask is saved as remaster/assets/glow/room_XX.png (grey, quarter
size); the renderer pulses it additively.
"""
import colorsys, os, sys
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]
import extract_gfx as gfx  # noqa: E402
sys.argv = _argv

ASSETS = os.path.join(ROOT, 'remaster', 'assets')
OUT = os.path.join(ASSETS, 'glow')
SCALE = 4                       # mask is 1/4 of 1920x960
WATER = {138, 31}

# Same set as the renderer's indoor_room(): caves (CGA palette 1), grotto and mines, temple.
def dark_rooms():
    return [r for r in range(gfx.NUM_ROOMS - 1)
            if gfx.room_palette(r) == 1 or 0x07 <= r <= 0x10 or 0x1c <= r <= 0x23]


def crystal(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return 0.45 <= h <= 0.85 and s >= 0.35 and v >= 0.55


def fire(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return 0.03 <= h <= 0.15 and s >= 0.45 and v >= 0.9


def core(r, g, b):  # white-hot centre of a flame
    return r >= 235 and g >= 215 and b >= 120


def fire_mask(room):
    """Painted flames (braziers, torches, fire pits): mask + a list of flame tops."""
    im = Image.open(os.path.join(ASSETS, 'rooms', f'room_{room:02x}.png')).convert('RGB')
    w, h = im.width // SCALE, im.height // SCALE
    p = im.resize((w, h), Image.BOX).load()
    hit = [[fire(*p[x, y]) for x in range(w)] for y in range(h)]
    # connected blobs; keep flame-sized ones (not the big orange temple patterns)
    seen, tops = set(), []
    out = Image.new('L', (w, h), 0)
    o = out.load()
    for y in range(h):
        for x in range(w):
            if not hit[y][x] or (x, y) in seen:
                continue
            stack, pts = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and hit[ny][nx] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            hot = sum(1 for qx, qy in pts if core(*p[qx, qy]))
            if not (6 <= len(pts) <= 300 and bw <= 30 and bh <= 30 and bh >= bw * 0.6 and hot >= 2):
                continue
            for qx, qy in pts:
                o[qx, qy] = 255
            tops.append(((min(xs) + max(xs)) / 2 * SCALE, min(ys) * SCALE, bw * SCALE))
    return out.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.5)), tops


def mask(room):
    im = Image.open(os.path.join(ASSETS, 'rooms', f'room_{room:02x}.png')).convert('RGB')
    w, h = im.width // SCALE, im.height // SCALE
    small = im.resize((w, h), Image.BOX)
    tiles, _ = gfx.room_map(room)
    cw, ch = w / gfx.MAP_W, h / gfx.MAP_H
    p = small.load()
    out = Image.new('L', (w, h), 0)
    o = out.load()
    for y in range(h):
        for x in range(w):
            c, row = int(x / cw), int(y / ch)
            near_water = any(tiles[rr * gfx.MAP_W + cc] in WATER
                             for rr in range(max(0, row - 1), min(gfx.MAP_H, row + 2))
                             for cc in range(max(0, c - 1), min(gfx.MAP_W, c + 2)))
            if not near_water and crystal(*p[x, y]):
                o[x, y] = 255
    out = out.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(2.5))
    return out


def main():
    args = sys.argv[1:]
    preview = args[args.index('--preview') + 1] if '--preview' in args else None
    rooms = [int(a, 16) for a in args if not a.startswith('--') and a != preview] or dark_rooms()
    os.makedirs(OUT, exist_ok=True)
    for r in rooms:
        m = mask(r)
        lit = sum(1 for v in m.get_flattened_data() if v > 40) / (m.width * m.height)
        m.save(os.path.join(OUT, f'room_{r:02x}.png'))
        fm, tops = fire_mask(r)
        fm.save(os.path.join(OUT, f'room_{r:02x}_fire.png'))
        with open(os.path.join(OUT, f'room_{r:02x}_fire.txt'), 'w') as f:  # x y width, canvas px
            for x, y, bw in tops:
                f.write(f'{x:.0f} {y:.0f} {bw:.0f}\n')
        print(f'room {r:02x}: {lit * 100:.1f}% crystals, {len(tops)} flames')
        if preview:
            os.makedirs(preview, exist_ok=True)
            bg = Image.open(os.path.join(ASSETS, 'rooms', f'room_{r:02x}.png')).convert('RGB').resize(m.size)
            hl = Image.new('RGB', m.size, (255, 0, 255))
            Image.composite(hl, bg, m).save(os.path.join(preview, f'glow_{r:02x}.png'))


if __name__ == '__main__':
    main()
