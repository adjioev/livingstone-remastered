#include "gamedata.h"

#include <stdexcept>

Palette cga_palette(int which, bool bright) {
    // BIOS mode 4 leaves the colour-select register at 0x30: black background, intensity on.
    const uint8_t hi = bright ? 255 : 170, lo = bright ? 85 : 0;
    if (which == 0)
        return {{{0, 0, 0, 0}, {lo, hi, lo, 255}, {hi, lo, lo, 255}, {hi, uint8_t(bright ? 255 : 85), lo, 255}}};
    return {{{0, 0, 0, 0}, {lo, hi, hi, 255}, {hi, lo, hi, 255}, {hi, hi, hi, 255}}};
}

GameData::GameData(std::vector<uint8_t> com) {
    if (com.size() < 0x100 + addr::SPRITES_END) throw std::runtime_error("game image too small");
    img_.assign(com.begin() + 0x100, com.end());
    img_.resize(0x10000, 0);

    uint32_t p = addr::SPRITES;
    while (p < addr::SPRITES_END) {
        int w = img_[p], h = img_[p + 1];
        sprite_index_[uint16_t(p)] = sprites_.size();
        sprites_.push_back({uint16_t(p), w * 4, h});
        p += 2 + w * h;
    }
    if (p != addr::SPRITES_END) throw std::runtime_error("sprite bank does not end at 0xdd99");
}

std::optional<SpriteRec> GameData::sprite_at(uint16_t a) const {
    auto it = sprite_index_.find(a);
    if (it == sprite_index_.end()) return std::nullopt;
    return sprites_[it->second];
}

std::vector<Rgba> GameData::decode_tile_atlas(const Palette& pal) const {
    std::vector<Rgba> px(128 * 128);
    for (int t = 0; t < 256; t++) {
        const uint8_t* src = &img_[addr::TILES_A + t * 16];
        for (int row = 0; row < 8; row++) {
            int bits = src[row * 2] << 8 | src[row * 2 + 1];
            for (int k = 0; k < 8; k++)
                px[((t / 16) * 8 + row) * 128 + (t % 16) * 8 + k] = pal[(bits >> (14 - 2 * k)) & 3];
        }
    }
    return px;
}

std::vector<Rgba> GameData::decode_sprite(const SpriteRec& s, const Palette& pal) const {
    int wb = s.w_px / 4;
    std::vector<Rgba> px(size_t(s.w_px) * s.h);
    const uint8_t* src = &img_[s.addr + 2];
    for (int y = 0; y < s.h; y++)
        for (int xb = 0; xb < wb; xb++) {
            uint8_t b = src[y * wb + xb];
            for (int k = 0; k < 4; k++) px[y * s.w_px + xb * 4 + k] = pal[(b >> (6 - 2 * k)) & 3];
        }
    return px;
}

std::vector<ObjectView> GameData::objects(const uint8_t* ram) const {
    std::vector<ObjectView> out;
    for (uint32_t a = addr::OBJECTS; a < addr::TILEMAP && ram[a] != 0xff; a += addr::OBJECT_SIZE) {
        const uint8_t* o = ram + a;
        if (!(o[0] & 0x80)) continue;  // slot not in use
        auto spr = sprite_at(uint16_t(o[0x26] | o[0x27] << 8));
        if (!spr) continue;
        // +0x1a/+0x1b position (x in 4-px bytes, y in 2-px units), +0x1c/+0x1d window
        // offset inside the frame, +0x1e/+0x1f visible size (bytes x rows).
        int slot = int((a - addr::OBJECTS) / addr::OBJECT_SIZE);
        out.push_back({slot, spr->addr, o[0x1a] * 4, o[0x1b] * 2, o[0x1c] * 4, o[0x1d], o[0x1e] * 4, o[0x1f]});
    }
    return out;
}

std::vector<LogView> find_logs(const uint8_t* m) {
    std::vector<LogView> out;
    auto is_log = [](uint8_t t) { return t == LOG_L || t == LOG_MID || t == LOG_R; };
    for (int row = 0; row < MAP_H; row++) {
        const uint8_t* line = m + row * MAP_W;
        for (int c = 0; c < MAP_W;) {
            if (!is_log(line[c])) {
                c++;
                continue;
            }
            int start = c;
            bool has_l = false, has_r = false;
            for (; c < MAP_W && is_log(line[c]); c++) {
                has_l |= line[c] == LOG_L;
                has_r |= line[c] == LOG_R;
            }
            int end = c - 1;
            // LOG_MID alone is also a beam tile elsewhere: need at least one end piece.
            if (has_l && line[start] == LOG_L) out.push_back({row, start});
            else if (has_r && line[end] == LOG_R) out.push_back({row, end - (LOG_CELLS - 1)});
        }
    }
    return out;
}

std::vector<uint8_t> GameData::key_table() const {
    std::vector<uint8_t> keys;
    for (uint16_t a = 0x7d07; img_[a] && keys.size() < 32; a++) keys.push_back(img_[a]);
    return keys;
}
