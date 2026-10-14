"""Find the volcano peak on each outdoor room background (for the live smoke plume).

    python tools/find_volcano.py [--preview OUT_DIR]

The volcanoes are grey-brown cones standing against the sky in the upper half. Per
column, the topmost "volcano-coloured" pixel that sits directly under sky is a candidate
ridge point; the highest point of a ridge that falls away on both sides is the peak.
Writes remaster/assets/glow/volcano.txt: "room x y" (canvas px), rooms without one omitted.
"""
import colorsys, os, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]
import extract_gfx as gfx  # noqa: E402
sys.argv = _argv

ASSETS = os.path.join(ROOT, 'remaster', 'assets')
K = 4  # work at quarter size


def sky(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return (0.5 <= h <= 0.66 and s >= 0.25 and v >= 0.6) or (s < 0.12 and v > 0.85)


def rock(r, g, b):  # grey / brown / mauve, not green, not sky
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    green = 0.2 <= h <= 0.45 and s > 0.25
    return not green and not sky(r, g, b) and 0.25 <= v <= 0.85 and s <= 0.45


def peak(room):
    im = Image.open(os.path.join(ASSETS, 'rooms', f'room_{room:02x}.png')).convert('RGB')
    w, h = im.width // K, im.height // K
    p = im.resize((w, h), Image.BOX).load()
    top = []
    for x in range(w):
        y_hit = None
        for y in range(int(h * 0.08), int(h * 0.6)):
            if rock(*p[x, y]) and all(sky(*p[x, yy]) for yy in range(max(0, y - 4), y)):
                y_hit = y
                break
        top.append(y_hit)
    best = None
    for x in range(8, w - 8):
        y = top[x]
        if y is None:
            continue
        left = [top[x - d] for d in range(3, 9) if top[x - d] is not None]
        right = [top[x + d] for d in range(3, 9) if top[x + d] is not None]
        if len(left) >= 4 and len(right) >= 4 and min(left) > y + 2 and min(right) > y + 2:
            if best is None or y < best[1]:
                best = (x, y)
    return None if best is None else (best[0] * K + K // 2, best[1] * K)


# Crater positions (canvas px) read off gridded review sheets; refine() snaps them to
# the topmost solid pixel nearby. Rerun after regenerating a room's background.
PEAKS = {0x00: (1500, 232), 0x01: (720, 390), 0x02: (820, 118), 0x03: (1060, 250), 0x06: (1190, 350),
         0x11: (740, 464), 0x13: (1120, 262), 0x15: (1256, 300), 0x16: (730, 310), 0x18: (1160, 300),
         0x19: (1280, 440), 0x1a: (1040, 270), 0x24: (720, 236), 0x25: (1030, 320), 0x26: (1043, 363),
         0x27: (864, 380), 0x28: (620, 190), 0x29: (840, 104), 0x38: (1240, 276), 0x39: (760, 430),
         0x3b: (480, 262), 0x3c: (1250, 412)}


def refine(room, gx, gy):
    """Crater: the highest solid (dark: not sky, not cloud or smoke) pixel near the guess,
    taken at the middle of that top run. Canvas px."""
    im = Image.open(os.path.join(ASSETS, 'rooms', f'room_{room:02x}.png')).convert('RGB')
    w, h = im.width // K, im.height // K
    p = im.resize((w, h), Image.BOX).load()
    cx, cy = gx // K, gy // K

    def solid(x, y):
        r, g, b = p[x, y]
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return vv < 0.62 and not (0.5 <= hh <= 0.66 and ss > 0.3)

    top = {}
    for x in range(max(0, cx - 8), min(w, cx + 9)):
        for y in range(max(0, cy - 10), min(h - 2, cy + 11)):
            if solid(x, y) and solid(x, y + 1) and solid(x, y + 2):
                top[x] = y
                break
    if not top:
        return gx, gy
    ymin = min(top.values())
    xs = [x for x, y in top.items() if y <= ymin + 1]
    return (sum(xs) // len(xs)) * K + K // 2, ymin * K


def outdoor_rooms():
    return [r for r in range(gfx.NUM_ROOMS - 1)
            if not (gfx.room_palette(r) == 1 or 0x07 <= r <= 0x10 or 0x1c <= r <= 0x23)]


def main():
    preview = sys.argv[sys.argv.index('--preview') + 1] if '--preview' in sys.argv else None
    found = {r: refine(r, *g) for r, g in PEAKS.items()}
    with open(os.path.join(ASSETS, 'glow', 'volcano.txt'), 'w') as f:
        for r, (x, y) in sorted(found.items()):
            f.write(f'{r} {x} {y}\n')
    print(f'{len(found)} peaks:', ' '.join(f'{r:02x}' for r in sorted(found)))
    if preview:
        os.makedirs(preview, exist_ok=True)
        rooms = outdoor_rooms()
        cols = 6
        sheet = Image.new('RGB', (cols * 320, ((len(rooms) + cols - 1) // cols) * 160))
        for i, r in enumerate(rooms):
            im = Image.open(os.path.join(ASSETS, 'rooms', f'room_{r:02x}.png')).convert('RGB').resize((320, 160))
            d = ImageDraw.Draw(im)
            d.text((4, 4), f'{r:02x}', fill=(255, 255, 0))
            if r in found:
                x, y = found[r][0] / 6, found[r][1] / 6
                d.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 0, 255), width=2)
            sheet.paste(im, ((i % cols) * 320, (i // cols) * 160))
        sheet.save(os.path.join(preview, 'volcano.png'))


if __name__ == '__main__':
    main()
