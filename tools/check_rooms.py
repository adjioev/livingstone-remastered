"""Review sheets for HD room backgrounds: the original solid shapes' outlines drawn over
the HD picture, so moved, missing or invented platforms are easy to spot by eye.

    python tools/check_rooms.py OUT_DIR            # all HD rooms
    python tools/check_rooms.py OUT_DIR 06 03      # only these

Writes OUT_DIR/review_N.png, 6 rooms per sheet (2 x 3), each labelled with its number.
(An automatic edge-alignment score was tried; painterly backgrounds have edges
everywhere and it could not tell good rooms from bad ones.)
"""
import os, sys
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]
import extract_gfx as gfx  # noqa: E402
sys.argv = _argv

ROOMS = os.path.join(ROOT, 'remaster', 'assets', 'rooms')
W, H = 640, 320
PER_SHEET, COLS = 6, 2


def overlay(room):
    hd = Image.open(os.path.join(ROOMS, f'room_{room:02x}.png')).convert('RGB').resize((W, H), Image.LANCZOS)
    # Tile-level mask: dithered tiles have holes, a pixel mask would outline every dot.
    tiles, _ = gfx.room_map(room)
    mask = Image.new('L', (gfx.MAP_W, gfx.MAP_H))
    mask.putdata([255 if t else 0 for t in tiles])
    mask = mask.resize((W, H), Image.NEAREST)
    edge = mask.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 0 else 0)
    hd.paste((255, 0, 255), (0, 0), edge)
    d = ImageDraw.Draw(hd)
    d.rectangle((0, 0, 44, 22), fill=(0, 0, 0))
    d.text((6, 5), f'{room:02x}', fill=(255, 255, 0))
    return hd


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    rooms = [int(a, 16) for a in sys.argv[2:]] or sorted(
        int(f[5:7], 16) for f in os.listdir(ROOMS) if f.startswith('room_'))
    for n in range(0, len(rooms), PER_SHEET):
        chunk = rooms[n:n + PER_SHEET]
        sheet = Image.new('RGB', (COLS * W, ((len(chunk) + COLS - 1) // COLS) * H))
        for i, r in enumerate(chunk):
            sheet.paste(overlay(r), ((i % COLS) * W, (i // COLS) * H))
        path = os.path.join(out, f'review_{n // PER_SHEET}.png')
        sheet.save(path)
        print(path, ' '.join(f'{r:02x}' for r in chunk))


if __name__ == '__main__':
    main()
