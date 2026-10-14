"""Generate HD room backgrounds with Gemini from the original room layouts.

    python tools/gen_rooms.py 06 05 04 11 03      # room numbers in hex
    python tools/gen_rooms.py --guides-only 06    # just write layout guides
    python tools/gen_rooms.py --logo               # redraw the title logo, no API call
    python tools/gen_rooms.py --patch swamp|trap [rooms]  # local repaint on aligned backgrounds
    python tools/gen_rooms.py --finish [rooms]     # re-run pixelize + logo from raw/, no API call

For each room: render the original tiles (no sprites) at 6x -> 1920x960 guide, pad to
16:9 with empty sky on top, send guide + style reference to Gemini, crop the result
back to 1920x960 and save remaster/assets/rooms/room_XX.png (picked up by the game).
The key is read from remaster/.env (GOOGLE_GENERATIVE_AI_API_KEY) and never logged.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)
_argv, sys.argv = sys.argv, sys.argv[:1]  # extract_gfx reads argv at import
import extract_gfx as gfx  # noqa: E402
import gemini  # noqa: E402
sys.argv = _argv

ASSETS = os.path.join(ROOT, 'remaster', 'assets')
W, H, PAD = 1920, 960, 120  # 1920x(960+120) = 16:9
STYLE_REF = os.path.join(ASSETS, 'ref', 'style.png')

# Title screen: the big "ЛИВИНГСТОН" is made of room tiles in rows 0-3. Image models garble
# lettering, so that band is left as empty sky for Gemini and the logo is drawn on top.
TITLE_ROOM = 0x3d
LOGO_ROWS = 4
# Title screen text per edition: (title, subtitle, credit plaque). '' = none.
EDITIONS = {
    'release': ('LIVINGSTONE', 'REMASTERED', 'OPERA SOFT'),
    'alan': ('ALAN JONES', 'IN SEARCH OF 60 DOLLARS', "DAD'S HOME GAMING"),  # family edition
}
LOGO_TEXT, LOGO_SUBTITLE, LOGO_CREDIT = EDITIONS['release']
LOGO_HEIGHT_WITH_SUBTITLE = 236  # px
LOGO_FONT = '/System/Library/Fonts/Supplemental/Impact.ttf'
# Title room without the logo (tracked, unlike raw/): make_app.sh draws each edition's logo on it.
TITLE_BG = os.path.join(ASSETS, 'title', 'room_3d_bg.png')
LOGO_PIXEL = 4  # drawn at 1/4 size without anti-aliasing, then scaled up: pixel-art look
PARALLEL = 6  # rooms generated at once
# Gemini picks a different "pixel size" per picture (caves came out almost smooth), so every
# room is snapped to one pixel grid: same chunkiness everywhere. (A reduced palette was
# tried too; median-cut lost hues - red flowers went brown, crystals went yellow.)
PIXEL = 5          # screen px per art pixel at 1920 wide

CLOUD_TILES = set(range(21, 29))  # yellow clouds in the sky
SWAMP_TILES = {137}                # poisonous swamp strip in the ground
SWAMP_GUIDE = (170, 40, 200)
WATER_TILES = {138, 31}        # olive river fill, waterfall / channel fill
WATER_GUIDE = (30, 110, 230)

# Per-room facts the layout alone doesn't tell the model.
HINTS = {
    0x00: 'The flat olive band along the bottom is a RIVER: paint open water there, with nothing floating '
          'on it. The mound in the middle rises out of the river.',
}
HINTS[0x02] = ('The blue band across the top-left is a river flowing on top of the rock cliff; it '
               'pours down the vertical blue column as a WATERFALL into the river along the bottom. '
               'The red rock under the top band is a cliff.')
HINTS[0x3a] = ('The cave interior is empty dry air: NO water, no lake, no pool anywhere. The black gap '
               'that reaches the RIGHT EDGE of the picture (in the middle of the right side) is a tunnel '
               'exit: keep it open all the way to the edge, no rock and no door there. No other doors '
               'or arches.')
HINTS[0x37] = ('The opening in the left wall is a doorway (a gate is drawn there by the game).')
MINE = ('This is an underground MINE deep inside the mountain: dark and spooky, NO sky, no clouds, no '
        'mountains, no daylight anywhere. Rough rock walls and ceiling everywhere behind, old wooden '
        'mine timbers and beams, dim warm lantern glow, cobwebs, dust, deep shadows. Open areas are dark '
        'rock tunnel receding into gloom, never black space and never stars.')
MINE_ROOMS = (0x0c, 0x0d, 0x0e, 0x0f, 0x10)  # outdoor palette in the game, but underground
for _r in MINE_ROOMS:
    HINTS[_r] = MINE
HINTS[0x01] = ('On the left a river runs along the top of a cliff and pours down as a WATERFALL (the blue '
               'vertical column) into the river at the bottom. Left of the waterfall, between the top '
               'river and the small grassy ledge at the bottom-left, is a CAVE: the black area there is a '
               'dark cave opening going into the cliff, with the grassy ledge as its floor. Keep that '
               'area dark and open, not solid rock.')
HINTS[0x0a] = ('This is a CAVE (grotto) inside the jungle hill: rocky ceiling with hanging moss and '
               'stalactites at the top, dark rock walls behind, NO sky, NO water anywhere. The long thin red '
               'strip at the bottom is a dry red-earth path on the cave floor; the two red ledges are rock '
               'shelves. A small red mushroom and a skull sit on the floor path.')
GROTTO = ('This is a CAVE (grotto) inside the jungle hill: rocky ceiling with hanging moss and '
          'stalactites at the top, dark rock walls behind, NO sky, no clouds, no mountains, no daylight '
          'from outside. Red ledges are rock shelves; any blue area is an underground pool or stream.')
CAVE_ROOMS = (0x07, 0x08, 0x09, 0x0a, 0x0b)  # outdoor palette in the game, but underground
for _r in CAVE_ROOMS:
    HINTS.setdefault(_r, GROTTO)
TEMPLE = ('This is a hall INSIDE an ancient jungle temple: carved stone ceiling, stone block walls '
          'behind, NO sky, no clouds, no mountains, no daylight from outside. Dim and mysterious, lit by '
          'flaming braziers and torches, carved glyphs on the walls, moss and roots creeping in, dust in '
          'the air. Columns are carved stone pillars.')
TEMPLE_ROOMS = (0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23)
for _r in TEMPLE_ROOMS:
    HINTS[_r] = TEMPLE + (' ' + HINTS[_r] if _r in HINTS else '')
CAVE_ROOMS = CAVE_ROOMS + TEMPLE_ROOMS
HINTS[0x1c] = TEMPLE + (' This is the temple sanctuary: the stepped block in the middle is a carved stone '
                        'ALTAR / stage with patterned gold-and-red tiles, a dancer performs on it.')
HINTS[0x38] = ('Open jungle clearing: one flat ground strip along the bottom and a small rock block at the '
               'top-left corner. Nothing else is solid: no ledges, no platforms, no floating islands in the middle.')
for _r in (0x1f, 0x22):
    HINTS[_r] += (' This hall has NO water: empty black areas are dark open space or a deep dark pit '
                  'between the stone platforms.')
HINTS[0x08] = GROTTO + (' The cave floor along the bottom is SOLID dry rock and earth from the left edge to the '
                        'right edge. The only water is the narrow waterfall in the blue column and a SMALL pool '
                        'right under it (the blue area at the bottom middle); everywhere else the floor is dry.')
HINTS[0x07] = GROTTO + ' This screen has NO water at all: the floor is dry rock and earth.'
HINTS[0x2a] = ('The water is ONLY a shallow river in the bottom strip of the picture (the blue band at the very '
               'bottom): its surface is low, far below the two grassy ledges at the top-left and top-right. '
               'Between the ledges and the river there is a lot of open air with jungle and sky behind. On '
               'the left a red rock cliff goes from the top-left ledge all the way down to the river bed.')
HINTS[0x28] = ('In the middle a wooden BRIDGE with a wooden railing (balustrade) along its top stands on two '
               'tall wooden scaffold TOWERS (lattice frames with cross beams, like well frames) rising out of '
               'the water. On the right a red rock cliff with a sandy road along its top ledge; on the left a '
               'smaller red rock. Water fills the bottom. Only sky above (no floating islands).')
HINTS[0x2b] = ('The small structure on the ground in the bottom middle is an old stone WELL: a low round '
               'wall of mossy green stones with yellow capstones, a dark opening inside, sitting on the grass. '
               'On the right is a tall rock cliff with a red mushroom-shaped ledge sticking out. Everything '
               'else is open sky and distant jungle: NO floating islands, nothing in the air.')
_PIT = (' The open area in the middle of the bottom, between the two walls, is a dark empty pit with a '
        'stone floor: NO spikes, no stakes, nothing in it (the game draws the spikes there).')
# 2d and 2f: the painted spikes are kept; room_XX_open.png (made with _PIT) is drawn over
# the spike cells once a lever clears them (see OPEN_CELLS / the renderer).
HINTS[0x29] = ('On the left is a tall red rock HILL. The yellow band on its side is a dirt ROAD (a sandy path) '
               'that winds around the hill: paint it clearly as a narrow sandy road cut into the hillside, '
               'walkable, with a little edge. The hill goes down to the water on the left. On the right is a '
               'grassy cliff ledge. Water fills the bottom; nothing else floats on it.')
RIVER = ('The flat olive area is a RIVER: paint open water there, with nothing floating on it '
         '(no logs, no boats, no rafts).')
for _r in (0x25, 0x26, 0x2a):
    HINTS[_r] = RIVER

PROMPT_OUTDOOR = """You are repainting one screen of a 1986 jungle platform game as a modern HD 2D game background.

Image 1 is the LAYOUT: the original low-resolution screen. It is a collision map.
Image 2 is the STYLE reference: match its painterly pixel-art look, lighting and palette.

Rules:
- Keep every platform, ledge, floating island, ground strip, rock mound, wall, tree trunk, vine and pillar EXACTLY where it is in image 1, with the same outline and size. Walkable top edges must stay at the same height.
- Plain purple areas in image 1 mark a SWAMP: paint a murky dark-green bog there (green-brown water, duckweed, reeds at the edges, a few bubbles), sunk into the ground, exactly in that area. Do NOT paint it purple.
- Plain blue areas in image 1 are WATER (river or lake): paint water exactly there, filling the whole blue area down to its bottom edge.
- Black areas in image 1 are open air: paint bright tropical sky, soft clouds, distant jungle, hills and mountains there, staying behind (never covering) the solid shapes.
- The empty band at the very top is extra sky; continue the sky there.
- Small distinctive details are gameplay elements: keep them where they are and draw them clearly -
  rows of round yellow stones (trapdoors), spikes, skulls, water and lava, ladders, ropes, columns.
- Repaint everything in the new style: never copy the original low-resolution dithered pixels into the picture.
- Do not invent hazards (spikes, lava, pits) that are not in image 1; a mound stays a mound.
- Do NOT add characters, people, animals, creatures, text, numbers, UI or HUD.
- Same framing as image 1: no zoom, no crop, no camera shift. Wide landscape image."""

PROMPT_TITLE = PROMPT_OUTDOOR + """

This is the TITLE SCREEN, a jungle village: on the left a large thatched-roof shelter on wooden poles,
on the right a tall wooden lookout tower with a flat platform on top (two drummers will stand on it),
a leafy bush mound in front of the tower, small flowers in the grass. Keep the top quarter of the
picture as clear open sky with nothing in it: the game title goes there."""

PROMPT_CAVE = PROMPT_OUTDOOR.replace(
    "paint bright tropical sky, soft clouds, distant jungle, hills and mountains there",
    "paint deep dark cave space with subtle depth, faint mist and glowing crystals far behind").replace(
    "continue the sky there", "continue the dark cave ceiling there")


def guide(room):
    # Trapdoors become plain ground in the guide (the model drew them as coins on a sunken
    # block); the pit is painted afterwards with --patch trap.
    tiles, _ = gfx.room_map(room)
    if any(t in TRAP_TILES for t in tiles):
        fixed = [gfx.GROUND_TOP if t in TRAP_TILES else t for t in tiles]
        fixed = [gfx.GROUND_FILL if (t == 202 and i >= gfx.MAP_W and tiles[i - gfx.MAP_W] in TRAP_TILES) else t
                 for i, t in enumerate(fixed)]
        im = gfx.render_map(fixed, room)
    else:
        im, _ = gfx.render_room(room, logs=False)  # logs move: drawn by the game as a prop
    # River tiles are a dithered olive the model reads as ground: paint them plain blue.
    tiles, _ = gfx.room_map(room)
    for i, t in enumerate(tiles):
        if t in CLOUD_TILES:  # decoration the model reads as floating platforms: leave open sky
            im.paste((0, 0, 0), ((i % gfx.MAP_W) * 8, (i // gfx.MAP_W) * 8, (i % gfx.MAP_W) * 8 + 8, (i // gfx.MAP_W) * 8 + 8))
        if t in SWAMP_TILES:
            im.paste(SWAMP_GUIDE, ((i % gfx.MAP_W) * 8, (i // gfx.MAP_W) * 8, (i % gfx.MAP_W) * 8 + 8, (i // gfx.MAP_W) * 8 + 8))
        if t in WATER_TILES:
            im.paste(WATER_GUIDE, ((i % gfx.MAP_W) * 8, (i // gfx.MAP_W) * 8, (i % gfx.MAP_W) * 8 + 8, (i // gfx.MAP_W) * 8 + 8))
    im = im.resize((W, H), Image.NEAREST)
    if room == TITLE_ROOM:
        im.paste((0, 0, 0), (0, 0, W, LOGO_ROWS * 8 * (W // gfx.MAP_W // 8)))
    padded = Image.new('RGB', (W, H + PAD))
    padded.paste(im, (0, PAD))
    os.makedirs(os.path.join(ASSETS, 'guides'), exist_ok=True)
    path = os.path.join(ASSETS, 'guides', f'room_{room:02x}.png')
    padded.save(path)
    return padded


def styled_text(text, lw, lh, top_col, bottom_col):
    """Text filling an lw x lh box (logo pixels): vertical gradient, dark outline,
    drop shadow and a highlight on the upper part of the letters."""
    mask = Image.new('L', (lw, lh), 0)
    d = ImageDraw.Draw(mask)
    d.fontmode = '1'
    size = lh
    while size > 6:
        font = ImageFont.truetype(LOGO_FONT, size)
        l, t, r, b = d.textbbox((0, 0), text, font=font)
        if r - l <= lw - 24 and b - t <= lh - 8:
            break
        size -= 1
    d.text(((lw - (r - l)) // 2 - l, (lh - (b - t)) // 2 - t), text, font=font, fill=255)

    out = Image.new('RGBA', (lw, lh), (0, 0, 0, 0))
    shadow = Image.new('RGBA', (lw, lh), (30, 14, 4, 160))
    edge = Image.new('RGBA', (lw, lh), (60, 28, 8, 255))
    for dx, dy in ((3, 3), (2, 3), (3, 2)):
        out.paste(shadow, (dx, dy), mask)
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if abs(dx) + abs(dy) <= 3:
                out.paste(edge, (dx, dy), mask)
    grad = Image.new('RGBA', (lw, lh))
    gp = grad.load()
    for y in range(lh):
        k = y / max(1, lh - 1)
        col = tuple(int(a + (b - a) * k) for a, b in zip(top_col, bottom_col)) + (255,)
        for x in range(lw):
            gp[x, y] = col
    out.paste(grad, (0, 0), mask)
    top = mask.copy()
    top.paste(0, (0, (lh * 2) // 5, lw, lh))
    shifted = Image.new('L', (lw, lh), 0)
    shifted.paste(top, (0, 1))
    hl = Image.composite(top, Image.new('L', (lw, lh), 0), Image.eval(shifted, lambda v: 255 - v))
    out.paste(Image.new('RGBA', (lw, lh), (255, 252, 210, 255)), (0, 0), hl)
    return out


def logo(bg):
    """Title + subtitle over the top band of the title room."""
    band_h = LOGO_ROWS * 8 * (W // gfx.MAP_W // 8)
    if LOGO_SUBTITLE:
        band_h = LOGO_HEIGHT_WITH_SUBTITLE
    lw, lh = W // LOGO_PIXEL, band_h // LOGO_PIXEL
    title_h = lh * 72 // 100 if LOGO_SUBTITLE else lh
    out = Image.new('RGBA', (lw, lh), (0, 0, 0, 0))
    out.alpha_composite(styled_text(LOGO_TEXT, lw, title_h, (255, 236, 110), (255, 126, 30)), (0, 0))
    if LOGO_SUBTITLE:
        out.alpha_composite(styled_text(LOGO_SUBTITLE, lw, lh - title_h + 2, (255, 255, 240), (140, 230, 120)),
                            (0, title_h - 2))
    out = out.resize((W, band_h), Image.NEAREST)
    bg = bg.convert('RGBA')
    bg.alpha_composite(out, (0, 4))
    if LOGO_CREDIT:
        c = credit_plaque(LOGO_CREDIT)
        bg.alpha_composite(c, ((W - c.width) // 2, band_h + 8))
    return bg.convert('RGB')


def credit_plaque(text, board=(178, 40, 32), ink=(255, 214, 72)):
    """Small red sign in the same pixel scale as the logo."""
    px = 2  # finer pixel than the logo: small lettering stays readable
    font = ImageFont.truetype(LOGO_FONT, 26)
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    pw, ph = r - l + 24, b - t + 14
    im = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    dark, light = tuple(v // 2 for v in board), tuple(min(255, v + 60) for v in board)
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), radius=6, fill=dark)
    d.rounded_rectangle((2, 2, pw - 3, ph - 3), radius=5, fill=board)
    d.line((6, 4, pw - 7, 4), fill=light, width=2)
    d.text((12 - l + 2, 7 - t + 2), text, font=font, fill=dark)
    d.text((12 - l, 7 - t), text, font=font, fill=ink)
    return im.resize((pw * px, ph * px), Image.NEAREST)


def pixelize(im):
    small = im.resize((W // PIXEL, H // PIXEL), Image.BOX)
    return small.resize((W, H), Image.NEAREST)


# Rooms whose (well aligned) background has no swamp: the bog is painted onto the swamp
# cells after pixelizing, so the ground line can't drift.
SWAMP_PAINT = (0x04, 0x05, 0x16, 0x18)


def paint_swamp(im, room):
    """Murky bog over the swamp cells, in art pixels: ragged muddy bank, dark water with
    a sheen, duckweed patches, lily pads and reeds."""
    import math, random
    tiles, _ = gfx.room_map(room)
    cell = W // gfx.MAP_W
    sw, sh = W // PIXEL, H // PIXEL
    rnd = random.Random(room)
    cols = {}
    for i, t in enumerate(tiles):
        if t in SWAMP_TILES:
            cols.setdefault(i // gfx.MAP_W, []).append(i % gfx.MAP_W)
    over = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    px = over.load()
    mud, mud_dk = (78, 58, 34), (52, 38, 22)
    water = [(26, 44, 30), (32, 54, 34), (38, 62, 38)]
    sheen, scum, scum_lt = (70, 98, 64), (74, 104, 40), (110, 142, 52)
    pad, pad_dk, flower = (80, 140, 50), (50, 96, 34), (236, 200, 220)
    for row, cs in cols.items():
        x0, x1 = min(cs) * cell * sw // W, (max(cs) + 1) * cell * sw // W
        y0, y1 = row * cell * sh // H, (row + 1) * cell * sh // H
        span = x1 - x0
        for x in range(x0, x1):
            k = (x - x0) / max(1, span - 1)
            inset = int(2.5 * (1 - math.sin(k * math.pi)) + rnd.random())  # shallower at the ends
            top = y0 + inset
            for y in range(y0, y1):
                if y < top:
                    continue
                d = y - top
                if d == 0:
                    c = mud_dk
                elif x in (x0, x1 - 1) or y == y1 - 1:
                    c = mud
                else:
                    c = water[min(2, d // 3)]
                    if d == 1 and rnd.random() < 0.5:
                        c = sheen
                    elif rnd.random() < 0.22:
                        c = scum if rnd.random() < 0.7 else scum_lt
                px[x, y] = c + (255,)
        for _ in range(max(1, span // 14)):  # lily pads
            cx, cy = rnd.randint(x0 + 3, x1 - 4), rnd.randint(y0 + 3, y1 - 3)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (1, 1), (-1, 1)):
                px[cx + dx, cy + dy] = (pad if dy == 0 else pad_dk) + (255,)
            if rnd.random() < 0.5:
                px[cx, cy - 1] = flower + (255,)
        for _ in range(max(2, span // 8)):  # reeds on the banks and in the bog
            x = rnd.choice([rnd.randint(x0, x0 + 3), rnd.randint(x1 - 4, x1 - 1), rnd.randint(x0, x1 - 1)])
            h = rnd.randint(3, 7)
            for k in range(h):
                px[x, y0 + 1 - k] = ((70, 112, 40) if k < h - 2 else (128, 92, 48)) + (255,)
    over = over.resize((W, H), Image.NEAREST)
    out = im.convert('RGBA')
    out.alpha_composite(over)
    return out.convert('RGB')


SWAMP_PROMPT = """Image 1 is a close-up crop of a 2D jungle platform game background. The ground with grass
runs along the lower part. Inside the bright magenta rectangle, paint a SWAMP sunk into that ground: a
muddy bog with dark murky olive-brown water clearly darker than the grass, filling the rectangle from its
top edge down to its bottom edge (deep water, you can see a little murk and roots below the surface), a
soft muddy bank at both ends, scattered duckweed, two or three lily pads and a few reeds poking up. The water surface is at
the top edge of the rectangle (the ground line). Crisp pixel art with clean pixel edges, exactly the same
pixel size, outline and colour style as the grass and rocks around it - not blurry, not painterly.

Rules: change ONLY the inside of the magenta rectangle and remove the magenta outline; everything outside
it stays exactly the same (same framing, no zoom, no shift). No characters, no text."""

TRAP_PROMPT = """Image 1 is a close-up crop of a 2D jungle platform game background. The ground with grass
runs along the lower part. Inside the bright magenta rectangle, paint a hidden PIT TRAP in that ground: a
pit dug into the earth, its top covered with a loose mat of thin branches, dry palm fronds and leaves lying
across it at the ground line, with dark gaps between them hinting at the deep hole below; the earth walls
of the pit are visible underneath, going down into darkness. It must blend with the grass on both sides.
Crisp pixel art with clean pixel edges, exactly the same pixel size, outline and colour style as the grass
and rocks around it - not blurry, not painterly. No coins, no gold, no logs, no planks.

Rules: change ONLY the inside of the magenta rectangle and remove the magenta outline; everything outside
it stays exactly the same (same framing, no zoom, no shift). No characters, no text."""

NEST_PROMPT = """Draw ONE BIRD'S NEST as a game prop, seen exactly FROM THE SIDE at eye level (not from
above): very WIDE and FLAT and LOW, about four times wider than tall, a shallow rim woven from golden-brown
twigs, dry straw and grass, a few loose straws sticking out sideways, warm sunlit colours. The inside is not
visible (side view). Crisp high-detail pixel art in the same style as the sprites in image 1 (but draw only the nest).
Flat pure magenta #FF00FF background everywhere, no ground, no branch, no shadow, no eggs, no bird, no text."""
LEDGE_PROMPT = """Image 1 is a close-up crop of a 2D jungle platform game background. Inside the bright magenta
rectangle there is a red rock ledge with sky above it. Repaint that area as a plain smooth red rock ledge
top (same rock as the rest of the ledge) with open sky above it: remove any spikes, stakes or objects.
Crisp pixel art, exactly the same pixel size and colour style as the surroundings.

Rules: change ONLY the inside of the magenta rectangle and remove the magenta outline; everything outside
it stays exactly the same (same framing, no zoom, no shift). No characters, no text."""
CLEAR_PROMPT = """Image 1 is a close-up crop of a 2D jungle platform game background. Inside the bright magenta
rectangle there is an object the background must not have. Repaint that area as the same surroundings
continued naturally (the same rock ledge / ground and the same cave or sky behind), with no object: no gold,
no coin, no glow, no treasure. Crisp pixel art, exactly the same pixel size and colour style as around it.

Rules: change ONLY the inside of the magenta rectangle and remove the magenta outline; everything outside
it stays exactly the same (same framing, no zoom, no shift). No characters, no text."""
PLATE_PROMPT = """Image 1 is a close-up crop of a stone temple floor in a 2D platform game. Each bright magenta
rectangle marks a hidden PRESSURE PLATE trap in the floor: paint there a slightly sunken square slab of dark
RED brick / terracotta, clearly different from the surrounding floor stones, with a thin dark gap around it
and a faint worn carved symbol. Inside each rectangle only; the plates sit flush with the floor top.
Crisp pixel art, exactly the same pixel size and colour style as the floor around it.

Rules: change ONLY the insides of the magenta rectangles and remove the magenta outlines; everything else
stays exactly the same (same framing, no zoom, no shift). No characters, no text."""
PLATE_TILES = {192, 193}

WELL_PROMPT = """Image 1 is a close-up crop of a dark cave in a 2D platform game. Inside the bright magenta
rectangle, standing on the floor, paint an old stone WELL that the player has to jump over: a low round
wall of large pale grey-blue stones with lighter capstones on top and a dark opening inside, clearly lit
so it stands out against the dark cave behind it (light rim highlights, a soft shadow at its base). It fills
the rectangle exactly: its top edge is the top of the rectangle, its base sits on the floor.
Crisp pixel art, exactly the same pixel size and colour style as the surroundings.

Rules: change ONLY the inside of the magenta rectangle and remove the magenta outline; everything else
stays exactly the same (same framing, no zoom, no shift). No characters, no text."""
WELL_TILES = {245, 246, 247}  # the well's rim; the row under it is its stone wall

# Cells (col, row) where the model painted something that must not be in the background.
CLEAR_CELLS = {0x09: [(28, 14), (29, 14), (30, 14), (31, 14), (28, 15), (29, 15), (30, 15), (31, 15)]}
NEST_TILES = {134, 135, 136}  # woven twigs in a ledge: where the gold lies

# Local repaints on aligned backgrounds: kind -> (prompt, rooms). The patch file
# raw/room_XX_<kind>.png is the model's repaint of a close-up crop around the cells;
# finish() pastes back only the cells themselves, so nothing else can move.
PATCHES = {
    'swamp': (SWAMP_PROMPT, SWAMP_PAINT),
    'trap': (TRAP_PROMPT, (0x05, 0x06, 0x11, 0x15, 0x17)),
    'clear': (CLEAR_PROMPT, tuple(CLEAR_CELLS)),
    'plate': (PLATE_PROMPT, (0x1d, 0x1e, 0x1f, 0x20)),
    'well': (WELL_PROMPT, (0x34,)),
    'ledge': (LEDGE_PROMPT, (0x39,)),  # clears the spikes the model drew where the nest goes
    'nest': (NEST_PROMPT, (0x39,)),   # a keyed prop placed on the ledge, not a repaint
}
PATCH_CROP_PAD = (2, 4, 2, 1)  # cells around the patch in the crop: left, up, right, down
TRAP_TILES = {203, 204}        # trapdoor; the cell under it (202) is part of the pit


def patch_cells(room, kind):
    tiles, _ = gfx.room_map(room)
    if kind == 'swamp':  # the swamp row plus the earth row under it: room for depth
        cells = [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in SWAMP_TILES]
        return cells + [(c, r + 1) for c, r in cells if r + 1 < gfx.MAP_H]
    if kind == 'clear':
        return CLEAR_CELLS[room]
    if kind == 'well':
        rim = [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in WELL_TILES]
        return rim + [(c, r + 1) for c, r in rim]
    if kind == 'plate':
        return [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in PLATE_TILES]
    if kind in ('nest', 'ledge'):  # the nest row plus the rows above it (the model drew spikes there)
        cells = [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in NEST_TILES]
        return cells + [(c, r - k) for c, r in cells for k in (1, 2) if r - k >= 0]
    cells = [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in TRAP_TILES]
    return cells + [(c, r + 1) for c, r in cells if r + 1 < gfx.MAP_H]


def patch_box(room, kind):
    """Exact box (full-res px) of the cells."""
    cell = W // gfx.MAP_W
    cells = patch_cells(room, kind)
    return (min(c for c, _ in cells) * cell, min(r for _, r in cells) * cell,
            (max(c for c, _ in cells) + 1) * cell, (max(r for _, r in cells) + 1) * cell)


def patch_crop(room, kind):
    cell = W // gfx.MAP_W
    x0, y0, x1, y1 = patch_box(room, kind)
    l, u, r, d = PATCH_CROP_PAD
    return max(0, x0 - l * cell), max(0, y0 - u * cell), min(W, x1 + r * cell), min(H, y1 + d * cell)


def apply_patch(base, patch, room, kind):
    """Patch (crop-sized) pasted onto base over the exact cells. The model shifts colours a
    little across the whole crop, so the patch is colour-matched using the ring around the
    cells (which should be unchanged), then pasted with a one-art-pixel soft edge."""
    from PIL import ImageFilter, ImageStat
    cx0, cy0, cx1, cy1 = patch_crop(room, kind)
    x0, y0, x1, y1 = patch_box(room, kind)
    patch = patch.resize((cx1 - cx0, cy1 - cy0), Image.LANCZOS).convert('RGB')
    ref = base.crop((cx0, cy0, cx1, cy1))
    ring = Image.new('L', patch.size, 255)
    ImageDraw.Draw(ring).rectangle((x0 - cx0, y0 - cy0, x1 - cx0 - 1, y1 - cy0 - 1), fill=0)
    ps, rs = ImageStat.Stat(patch, ring), ImageStat.Stat(ref, ring)
    bands = []
    for i, band in enumerate(patch.split()):
        k = rs.stddev[i] / ps.stddev[i] if ps.stddev[i] > 1 else 1.0
        k = max(0.8, min(1.25, k))
        m_p, m_r = ps.mean[i], rs.mean[i]
        bands.append(band.point(lambda v, k=k, m_p=m_p, m_r=m_r: max(0, min(255, round((v - m_p) * k + m_r)))))
    patch = Image.merge('RGB', bands)
    # leftovers of the magenta marker: take the background there instead
    pp, rp = patch.load(), ref.load()
    for y in range(patch.height):
        for x in range(patch.width):
            r, g, b = pp[x, y]
            if r > 150 and b > 120 and g < 0.6 * min(r, b):
                pp[x, y] = rp[x, y]
    full = base.copy()
    full.paste(patch, (cx0, cy0))
    mask = Image.new('L', (W, H), 0)
    if kind == 'plate':  # several separate plates: only their own cells
        cell = W // gfx.MAP_W
        for c, r in patch_cells(room, kind):
            ImageDraw.Draw(mask).rectangle((c * cell, r * cell, (c + 1) * cell - 1, (r + 1) * cell - 1), fill=255)
    else:
        ImageDraw.Draw(mask).rectangle((x0 + PIXEL, y0 + PIXEL, x1 - PIXEL - 1, y1 - 1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(PIXEL))
    return pixelize(Image.composite(full, base, mask))


def base_image(room):
    """Aligned background without patches (pixelized raw)."""
    raw = Image.open(os.path.join(ASSETS, 'raw', f'room_{room:02x}.png')).convert('RGB')
    return pixelize(raw.resize((W, H + PAD), Image.LANCZOS).crop((0, PAD, W, H + PAD)))


def nest_prop(room):
    """Nest drawn on magenta by the model, keyed and placed on the ledge over its cells."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import gen_sprites as gs
    import gen_bank as gb
    ref = Image.open(os.path.join(ASSETS, 'raw', 'hero_sheet.png'))  # a sprite sheet: draws a sprite, not a scene
    raw = gemini.generate(NEST_PROMPT, [ref], aspect='1:1', label=f'nest {room:02x}')
    raw.save(os.path.join(ASSETS, 'raw', f'room_{room:02x}_nest_raw.png'))
    fig = gb.largest_blob(gs.key_out(raw))
    fig = fig.crop(fig.getbbox())
    fig.save(os.path.join(ASSETS, 'raw', f'room_{room:02x}_nest.png'))
    finish(room)


def place_nest(base, nest, room):
    cell = W // gfx.MAP_W
    tiles, _ = gfx.room_map(room)
    cells = [(i % gfx.MAP_W, i // gfx.MAP_W) for i, t in enumerate(tiles) if t in NEST_TILES]
    x0 = min(c for c, _ in cells) * cell
    x1 = (max(c for c, _ in cells) + 1) * cell
    ledge = min(r for _, r in cells) * cell          # top of the ledge row
    # Low and wide, rim a bit above the ledge top so the gold (drawn by the game on the
    # ledge) sits in it; wide enough to hide the cleared spikes.
    w = round((x1 - x0) * 1.3)
    h = min(round(nest.height * w / nest.width), round(cell * 1.6))
    nest = nest.resize((w, h), Image.LANCZOS)
    out = base.convert('RGBA')
    out.alpha_composite(nest, ((x0 + x1 - w) // 2, ledge + cell - h))  # bottom on the walking line
    return pixelize(out.convert('RGB'))


def inpaint(room, kind):
    if kind == 'nest':
        return nest_prop(room)
    prompt, _ = PATCHES[kind]
    base = base_image(room)
    cx0, cy0, cx1, cy1 = patch_crop(room, kind)
    x0, y0, x1, y1 = patch_box(room, kind)
    crop = base.crop((cx0, cy0, cx1, cy1))
    if kind == 'plate':  # one rectangle per plate (a run of plate cells in a row)
        cell = W // gfx.MAP_W
        cells = sorted(patch_cells(room, kind), key=lambda q: (q[1], q[0]))
        runs = []
        for c, r in cells:
            if runs and runs[-1][1] == r and runs[-1][2] == c - 1:
                runs[-1][2] = c
            else:
                runs.append([c, r, c])
        for c0, r, c1 in runs:
            ImageDraw.Draw(crop).rectangle((c0 * cell - cx0, r * cell - cy0, (c1 + 1) * cell - cx0 - 1,
                                            (r + 1) * cell - cy0 - 1), outline=(255, 0, 255), width=3)
    else:
        ImageDraw.Draw(crop).rectangle((x0 - cx0, y0 - cy0, x1 - cx0 - 1, y1 - cy0 - 1), outline=(255, 0, 255), width=3)
    # the crop, scaled up for detail, in a 21:9 canvas (closest supported ratio)
    k = 1792 / crop.width
    big = crop.resize((1792, min(768, round(crop.height * k))), Image.NEAREST)
    canvas = Image.new('RGB', (1792, 768), (0, 0, 0))
    oy = (768 - big.height) // 2
    canvas.paste(big, (0, oy))
    out = gemini.generate(prompt, [canvas], aspect='21:9', label=f'{kind} {room:02x}')
    out = out.resize((1792, 768), Image.LANCZOS).crop((0, oy, 1792, oy + big.height))
    out.save(os.path.join(ASSETS, 'raw', f'room_{room:02x}_{kind}.png'))
    finish(room)


def finish(room):
    """raw Gemini output -> crop to the playfield -> pixelize (-> logo) -> rooms/."""
    out = base_image(room)
    for kind, (_, rooms) in PATCHES.items():
        patch = os.path.join(ASSETS, 'raw', f'room_{room:02x}_{kind}.png')
        if room in rooms and os.path.exists(patch) and kind == 'nest':
            out = place_nest(out, Image.open(patch).convert('RGBA'), room)
        elif room in rooms and os.path.exists(patch):  # local repaint from --patch
            out = apply_patch(out, Image.open(patch).convert('RGB'), room, kind)
        elif kind == 'swamp' and room in rooms:
            out = paint_swamp(out, room)
    if room == TITLE_ROOM:
        out.save(TITLE_BG)
        out = logo(out)
    path = os.path.join(ASSETS, 'rooms', f'room_{room:02x}.png')
    out.save(path)
    print(f'room {room:02x}: {path}')


def generate(room):
    g = guide(room)
    style = Image.open(STYLE_REF)
    cave = gfx.room_palette(room) == 1 or room in MINE_ROOMS or room in CAVE_ROOMS
    prompt = PROMPT_TITLE if room == TITLE_ROOM else PROMPT_CAVE if cave else PROMPT_OUTDOOR
    if room in HINTS:
        prompt += '\n\nAbout this screen: ' + HINTS[room]
    out = gemini.generate(prompt, [g, style], aspect='16:9', label=f'room {room:02x}')
    os.makedirs(os.path.join(ASSETS, 'raw'), exist_ok=True)
    out.save(os.path.join(ASSETS, 'raw', f'room_{room:02x}.png'))
    finish(room)


def main():
    args = sys.argv[1:]
    if '--logo' in args:
        # --logo [--edition NAME] [--out PATH]
        global LOGO_TEXT, LOGO_SUBTITLE, LOGO_CREDIT
        edition = args[args.index('--edition') + 1] if '--edition' in args else 'release'
        LOGO_TEXT, LOGO_SUBTITLE, LOGO_CREDIT = EDITIONS[edition]
        out = args[args.index('--out') + 1] if '--out' in args else os.path.join(ASSETS, 'rooms', f'room_{TITLE_ROOM:02x}.png')
        logo(Image.open(TITLE_BG)).save(out)
        print(f'title logo ({edition}) -> {out}')
        return
    guides_only = '--guides-only' in args
    if '--patch' in args:  # --patch KIND [rooms]: local repaint (swamp, trap)
        kind = args[args.index('--patch') + 1]
        rooms = [int(a, 16) for a in args[args.index('--patch') + 2:] if not a.startswith('--')]
        with ThreadPoolExecutor(PARALLEL) as pool:
            list(pool.map(lambda r: inpaint(r, kind), rooms or list(PATCHES[kind][1])))
        return
    rooms = [int(a, 16) for a in args if not a.startswith('--')]
    if '--finish' in args:
        for r in rooms or sorted(int(f[5:7], 16) for f in os.listdir(os.path.join(ASSETS, 'raw'))
                                 if f.startswith('room_') and len(f) == len('room_00.png')):
            finish(r)
        return
    if guides_only:
        for r in rooms:
            guide(r)
            print(f'guide {r:02x}')
        return
    with ThreadPoolExecutor(PARALLEL) as pool:
        list(pool.map(generate, rooms))


if __name__ == '__main__':
    main()
