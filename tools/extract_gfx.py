"""Extract tiles and render rooms from LSTONE.COM (Opera Soft).

Image address = address in the game segment (LSTONE.COM: file offset + 0x100).

  0x59ac  tileset A: 256 tiles x 16 bytes (8x8, CGA 2bpp, 2 bytes/row)
  0x69ac  tileset B: font / HUD tiles, same format
  0x7c89  room table: word offsets into ROOM_DATA, one per room
  0x3fc0  ROOM_DATA: [count] then count x {col, row, word block_off}
  0x702c  BLOCKS: at block_off: {w, h} then w*h tile indices (0 = transparent)
  0x8ddd  SPRITES: contiguous records {w_bytes, h_rows} + w*h bytes of linear
          CGA 2bpp pixels (4 px/byte, colour 0 = transparent); ends at 0xdd99.
          Object slots point at a record via field +0x26 (blitter 0x3ae6).
"""
import os, struct, sys
from PIL import Image, ImageDraw

COM = sys.argv[1] if len(sys.argv) > 1 else 'original/LSTONE.COM'
OUT = sys.argv[2] if len(sys.argv) > 2 else 're'
_data = open(COM, 'rb').read()
# Image address = offset in the game segment. LSTONE.COM is a plain COM (address = file
# offset + 0x100); the 1991 Kiev LIVINGST.COM had a 256-byte loader in front (offset - 0x100).
img = _data[0x100:] if _data[:3] == b'\xe9\xac\x00' else bytes(0x100) + _data

TILES_A, TILES_B = 0x59ac, 0x69ac
ROOM_TABLE, ROOM_DATA, BLOCKS = 0x7c89, 0x3fc0, 0x702c
SPRITES, SPRITES_END = 0x8ddd, 0xdd99
HUD_SCRIPT = 0x8d05   # 0x00 row col = locate, 0xff = end, else tileset-B index
NUM_ROOMS = (0x7d07 - ROOM_TABLE) // 2   # keyboard table follows the room table
MAP_W, MAP_H = 40, 20

# BIOS mode 4 leaves the colour-select register at 0x30 (intensity on, black bg);
# the game then picks palette 0 or 1 via INT 10h/0Bh.
PAL = {0: [(0, 0, 0), (85, 255, 85), (255, 85, 85), (255, 255, 85)],
       1: [(0, 0, 0), (85, 255, 255), (255, 85, 255), (255, 255, 255)]}


def room_palette(room):
    # mirrors 0x35ae: rooms 0x2c..0x37 and 0x3a use palette 1
    return 1 if room == 0x3a or 0x2c <= room < 0x38 else 0


def draw_tile(px, base, idx, x0, y0, pal):
    a = base + idx * 16
    for row in range(8):
        w = img[a + row * 2] << 8 | img[a + row * 2 + 1]
        for k in range(8):
            px[x0 + k, y0 + row] = pal[(w >> (14 - 2 * k)) & 3]


def tilesheet(base, count, pal, name):
    cols = 16
    im = Image.new('RGB', (cols * 9, ((count + cols - 1) // cols) * 9), (40, 40, 60))
    px = im.load()
    for i in range(count):
        draw_tile(px, base, i, (i % cols) * 9, (i // cols) * 9, pal)
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(f'{OUT}/gfx/{name}.png')


def room_map(room):
    """Return the 40x20 tile map the game builds at 0xe04c (routine 0x3505)."""
    m = [0] * (MAP_W * MAP_H)
    p = ROOM_DATA + struct.unpack_from('<H', img, ROOM_TABLE + room * 2)[0]
    n = img[p]; p += 1
    for _ in range(n):
        col, row, off = img[p], img[p + 1], struct.unpack_from('<H', img, p + 2)[0]
        p += 4
        b = BLOCKS + off
        w, h = img[b], img[b + 1]
        b += 2
        for y in range(h):
            for x in range(w):
                t = img[b]; b += 1
                pos = (row + y) * MAP_W + col + x
                if t and 0 <= pos < len(m):
                    m[pos] = t
    return m, n


# Floating log: tiles LOG_L, LOG_MID..., LOG_R in one row. The game moves it along the
# river by rewriting the tile map, so the remaster draws it as a separate HD prop.
LOG_L, LOG_MID, LOG_R = 222, 217, 132


def log_runs(m):
    """(row, first_col, last_col) of every log in a 40x20 map, including logs cut by
    the screen edge (a run of LOG_MID touching column 0 or 39 next to one end tile)."""
    out = []
    for row in range(MAP_H):
        line = m[row * MAP_W:(row + 1) * MAP_W]
        c = 0
        while c < MAP_W:
            if line[c] in (LOG_L, LOG_R, LOG_MID):
                start = c
                while c < MAP_W and line[c] in (LOG_L, LOG_MID, LOG_R):
                    c += 1
                run = line[start:c]
                if LOG_L in run or LOG_R in run:
                    out.append((row, start, c - 1))
            else:
                c += 1
    return out


def without_logs(m):
    m = list(m)
    for row, a, b in log_runs(m):
        for c in range(a, b + 1):
            m[row * MAP_W + c] = 0
    return m


# Stake gate: a column of GATE_TIP over GATE_STAKE tiles blocking a doorway; a lever
# removes it from the tile map. Only in these rooms is it a door (in 2d/2f the same
# tiles are a fixed row of spikes).
GATE_TIP, GATE_STAKE = 249, 250
GATE_ROOMS = (0x37, 0x3a)  # 2d and 2f keep their painted spikes (room_XX_open.png)


def without_gates(m):
    return [0 if t in (GATE_TIP, GATE_STAKE) else t for t in m]


GROUND_TOP, GROUND_FILL = 179, 170  # grassy ground row and the earth under it


def render_map(m, room):
    """Render a 40x20 tile map (logs and gates removed) with the room's palette."""
    m = without_logs(m)
    if room in GATE_ROOMS:
        m = without_gates(m)
    im = Image.new('RGB', (MAP_W * 8, MAP_H * 8))
    px = im.load()
    pal = PAL[room_palette(room)]
    for i, t in enumerate(m):
        draw_tile(px, TILES_A, t, (i % MAP_W) * 8, (i // MAP_W) * 8, pal)
    return im


def render_room(room, logs=True):
    m, nblocks = room_map(room)
    if not logs:
        m = without_logs(m)
        if room in GATE_ROOMS:
            m = without_gates(m)
    im = Image.new('RGB', (MAP_W * 8, MAP_H * 8))
    px = im.load()
    pal = PAL[room_palette(room)]
    for i, t in enumerate(m):
        draw_tile(px, TILES_A, t, (i % MAP_W) * 8, (i // MAP_W) * 8, pal)
    return im, nblocks


def render_hud():
    """Interpret the HUD layout script the way 0x0d2d does (tiles from set B)."""
    im = Image.new('RGB', (320, 200))
    px = im.load()
    p, col, row = HUD_SCRIPT, 0, 0
    while img[p] != 0xff:
        if img[p] == 0:
            row, col = img[p + 1], img[p + 2]
            p += 3
            continue
        draw_tile(px, TILES_B, img[p], col * 8, row * 8, PAL[0])
        p += 1
        col += 1
        if col > 0x27:
            col, row = 0, row + 1
    im.crop((0, 160, 320, 200)).resize((960, 120), Image.NEAREST).save(f'{OUT}/gfx/hud.png')


def sprites():
    out, p = [], SPRITES
    while p < SPRITES_END:
        w, h = img[p], img[p + 1]
        out.append((p, w, h))
        p += 2 + w * h
    assert p == SPRITES_END
    return out


def render_sprite(p, w, h, pal):
    im = Image.new('RGB', (w * 4, h), (40, 40, 60))
    px = im.load()
    for y in range(h):
        for xb in range(w):
            b = img[p + 2 + y * w + xb]
            for k in range(4):
                c = (b >> (6 - 2 * k)) & 3
                if c:
                    px[xb * 4 + k, y] = pal[c]
    return im


def sprite_sheet(pal, name):
    recs = sprites()
    ims = [render_sprite(p, w, h, pal) for p, w, h in recs]
    width, x, y, rowh, pos = 640, 0, 0, 0, []
    for im in ims:
        cw, ch = max(im.width, 40) + 4, im.height + 14
        if x + cw > width:
            x, y, rowh = 0, y + rowh, 0
        pos.append((x, y)); x += cw; rowh = max(rowh, ch)
    sheet = Image.new('RGB', (width, y + rowh), (20, 20, 30))
    d = ImageDraw.Draw(sheet)
    for (p, w, h), im, (x, y) in zip(recs, ims, pos):
        d.text((x, y), f'{p:04x}', fill=(200, 200, 200))
        sheet.paste(im, (x, y + 12))
        im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(f'{OUT}/sprites/{p:04x}_{w * 4}x{h}.png')
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(f'{OUT}/gfx/{name}.png')
    return len(recs)


def main():
    for d in ('sprites', 'gfx', 'rooms'):
        os.makedirs(f'{OUT}/{d}', exist_ok=True)
    print('sprites:', sprite_sheet(PAL[0], 'sprites_pal0'))
    sprite_sheet(PAL[1], 'sprites_pal1')
    render_hud()
    tilesheet(TILES_A, 256, PAL[0], 'tiles_a_pal0')
    tilesheet(TILES_A, 256, PAL[1], 'tiles_a_pal1')
    tilesheet(TILES_B, (BLOCKS - TILES_B) // 16, PAL[0], 'tiles_b_pal0')
    rooms = []
    for r in range(NUM_ROOMS):
        im, n = render_room(r)
        im.resize((640, 320), Image.NEAREST).save(f'{OUT}/rooms/room_{r:02x}.png')
        rooms.append(im)
        print(f'room {r:02x}: {n} blocks, palette {room_palette(r)}')
    cols = 8
    atlas = Image.new('RGB', (cols * 324, ((len(rooms) + cols - 1) // cols) * 164), (60, 60, 60))
    for i, im in enumerate(rooms):
        atlas.paste(im, ((i % cols) * 324 + 2, (i // cols) * 164 + 2))
    atlas.save(f'{OUT}/rooms/atlas.png')


if __name__ == '__main__':
    main()
