#pragma once

// Static data in LSTONE.COM and the live state the renderer reads from game RAM.
// Addresses are game-segment offsets (file offset - 0x100); see docs/graphics.md.

#include <array>
#include <cstdint>
#include <optional>
#include <unordered_map>
#include <vector>

namespace addr {
constexpr uint16_t TILES_A = 0x59ac;      // 256 room tiles, 8x8, 16 bytes each
constexpr uint16_t SPRITES = 0x8ddd;      // {w_bytes, h} + w*h bytes, colour 0 transparent
constexpr uint16_t SPRITES_END = 0xdd99;
constexpr uint16_t TILEMAP = 0xe04c;      // live 40x20 room tile map
constexpr uint16_t ROOM = 0xe04a;
constexpr uint16_t OBJECTS = 0xde46;      // 0x28-byte slots, list ends with 0xff
constexpr uint16_t OBJECT_SIZE = 0x28;
constexpr uint16_t PALETTE = 0x35db;      // 0 or 1, set by the INT 10h/0Bh wrappers
constexpr uint16_t FRAME_WAIT = 0x274;    // main loop spins here until the next 3-tick frame
constexpr uint16_t FRAME_WAIT_END = 0x27b;
// HUD values (see docs/graphics.md, HUD)
constexpr uint16_t STRENGTH = 0xddb5;     // throw/vault power while Space is held, 0..60
constexpr uint16_t FOOD = 0xddac;         // 0..60, starts full
constexpr uint16_t WATER = 0xddad;        // 0..60, starts full
constexpr uint16_t LIVES = 0xdda2;        // starts at 7
constexpr uint16_t SCORE = 0xddde;        // word; shown x10 (the last "0" is a fixed tile)
constexpr uint16_t WEAPON = 0xddb1;       // low nibble: 1 boomerang, 2 knife, 3 grenade, 4 pole
// "dec ah" that takes a life; the game's own cheat (Left+Right+E+R+Down) NOPs it.
constexpr uint16_t LOSE_LIFE = 0x644;
constexpr uint16_t MUSIC_PLAYING = 0x7fb5;  // 1 while the tune plays (0x3e0d), 0 for effects
// Room entry used by the exits (0x0afe/0x0b20 set ROOM, then jump here): reloads tiles
// and objects, saves the restart point, returns to the main loop. SI = hero slot.
constexpr uint16_t ENTER_ROOM = 0x0b38;
constexpr int ROOM_COUNT = 0x3d;  // 0x00..0x3c are play rooms (0x3d is the title screen)
}  // namespace addr

constexpr int METER_MAX = 60;

// Floating log: room tiles LOG_L, LOG_MID..., LOG_R that the game moves by rewriting the
// tile map. The remaster draws it as an HD prop over the background.
constexpr uint8_t LOG_L = 222, LOG_MID = 217, LOG_R = 132;
constexpr int LOG_CELLS = 10;

// Stake gate blocking a doorway in these rooms; a lever clears it from the tile map.
constexpr uint8_t GATE_TIP = 249, GATE_STAKE = 250;
constexpr int GATE_ROOMS[] = {0x37, 0x3a};

constexpr uint16_t LOG_SPRITE = 0;   // ObjectView::sprite of a log (see Smoother)
constexpr int LOG_SLOT_BASE = 100;   // ObjectView::slot of a log = base + its row

struct LogView {
    int row;
    int left;  // column of the log's left end; negative or > 30 when cut by the screen edge
};
std::vector<LogView> find_logs(const uint8_t* tilemap);

struct HudState {
    int strength, food, water, lives, score, weapon;
    bool infinite_lives = false;
};

constexpr int MAP_W = 40, MAP_H = 20;     // tiles
constexpr int FIELD_W = 320, FIELD_H = 160;  // playfield pixels; HUD is rows 160..199

struct Rgba { uint8_t r, g, b, a; };
using Palette = std::array<Rgba, 4>;
Palette cga_palette(int which, bool bright);

struct SpriteRec {
    uint16_t addr;
    int w_px, h;
};

// What the renderer draws for one active object slot.
struct ObjectView {
    int slot;                  // index in the object table
    uint16_t sprite;           // record address in the sprite bank
    int x, y;                  // playfield pixels
    int src_x, src_y, w, h;    // visible window inside the sprite, pixels
    float fx = 0, fy = 0;      // interpolated position (set by Smoother)
    bool operator==(const ObjectView& o) const {
        return slot == o.slot && sprite == o.sprite && x == o.x && y == o.y && src_x == o.src_x &&
               src_y == o.src_y && w == o.w && h == o.h;
    }
};

class GameData {
public:
    explicit GameData(std::vector<uint8_t> com);

    const std::vector<SpriteRec>& sprites() const { return sprites_; }
    std::optional<SpriteRec> sprite_at(uint16_t addr) const;

    // RGBA decoders (colour index 0 -> transparent).
    std::vector<Rgba> decode_tile_atlas(const Palette& pal) const;  // 16x16 tiles, 128x128 px
    std::vector<Rgba> decode_sprite(const SpriteRec& s, const Palette& pal) const;

    // Live state.
    static int room(const uint8_t* ram) { return ram[addr::ROOM]; }
    static int palette(const uint8_t* ram) { return ram[addr::PALETTE] & 1; }
    static const uint8_t* tilemap(const uint8_t* ram) { return ram + addr::TILEMAP; }
    static HudState hud(const uint8_t* ram) {
        return {ram[addr::STRENGTH], ram[addr::FOOD], ram[addr::WATER], ram[addr::LIVES],
                (ram[addr::SCORE] | ram[addr::SCORE + 1] << 8) * 10, ram[addr::WEAPON] & 0x0f};
    }
    std::vector<ObjectView> objects(const uint8_t* ram) const;
    // The game's key table (0x7d07): scancodes, 0-terminated.
    std::vector<uint8_t> key_table() const;

private:
    std::vector<uint8_t> img_;
    std::vector<SpriteRec> sprites_;
    std::unordered_map<uint16_t, size_t> sprite_index_;
};
