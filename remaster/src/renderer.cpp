#include "renderer.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace {

constexpr float TRANSITION_SECONDS = 0.45f;
constexpr int HUD_Y = FIELD_H, HUD_H = 200 - FIELD_H;  // CGA rows 160..199
constexpr int HUD_SCALE = 3;
constexpr const char* HUD_FONT = "/System/Library/Fonts/Supplemental/Impact.ttf";
constexpr uint16_t LIFE_ICON = 0x8e69;  // hero standing
// Sprites replaced by an HD cycle from assets/anim/<name>_<i>.png.
struct AnimDef {
    const char* name;
    std::vector<uint16_t> sprites;
    float fps;
};
const AnimDef ANIM_DEFS[] = {
    {"drum", {0xae8d, 0xaf13}, 7.0f},   // title-screen drummers (2 frames in the original)
    {"dance", {0xb8df, 0xc54f}, 6.0f},  // gold dancer
};
constexpr uint16_t WEAPON_ICONS[4] = {0x9729, 0x9769, 0x9777, 0x9acb};  // boomerang, knife, grenade, pole

// Hero walk: the game cycles 8ef5 -> 8e69 -> 8f81 -> 8e69, one frame per ~0.06 s
// (left-facing: c8bd, c831, c949). 8e69/c831 alone is also the standing pose.
constexpr uint16_t WALK_RIGHT[] = {0x8ef5, 0x8f81}, WALK_LEFT[] = {0xc8bd, 0xc949};
constexpr uint16_t STAND_RIGHT = 0x8e69, STAND_LEFT = 0xc831;
constexpr float WALK_CYCLE_SECONDS = 0.24f;
constexpr double WALK_HOLD = 0.15;  // still walking if a stride frame was seen this recently

bool is_any(uint16_t s, const uint16_t (&set)[2]) { return s == set[0] || s == set[1]; }

Texture2D texture_from(const std::vector<Rgba>& px, int w, int h, int filter) {
    Image img{const_cast<Rgba*>(px.data()), w, h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8};
    Texture2D t = LoadTextureFromImage(img);
    SetTextureFilter(t, filter);
    return t;
}

// Rooms 0x2c..0x37 and 0x3a are caves (the game switches them to CGA palette 1).
bool is_cave(int palette) { return palette == 1; }

float smoothstep(float t) { return t * t * (3 - 2 * t); }

Rectangle flipped(const RenderTexture2D& rt) {
    return {0, 0, float(rt.texture.width), -float(rt.texture.height)};
}

}  // namespace

Renderer::Renderer(const GameData& data, const std::string& assets_dir) : data_(data), assets_(assets_dir) {
    canvas_ = LoadRenderTexture(CANVAS_W, CANVAS_H);
    field_ = LoadRenderTexture(CANVAS_W, FIELD_PX_H);
    prev_field_ = LoadRenderTexture(CANVAS_W, FIELD_PX_H);
    SetTextureFilter(canvas_.texture, TEXTURE_FILTER_BILINEAR);

    std::vector<Rgba> blank(320 * 200);
    vram_tex_ = texture_from(blank, 320, 200, TEXTURE_FILTER_POINT);

    for (int r = 0; r < 0x40; r++) {
        char path[64];
        std::snprintf(path, sizeof path, "/rooms/room_%02x.png", r);
        if (FileExists((assets_ + path).c_str())) {
            Texture2D t = LoadTexture((assets_ + path).c_str());
            SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
            hd_rooms_[r] = t;
        }
    }
    for (const auto& s : data_.sprites()) {
        char path[64];
        std::snprintf(path, sizeof path, "/sprites/%04x.png", s.addr);
        if (FileExists((assets_ + path).c_str())) {
            Texture2D t = LoadTexture((assets_ + path).c_str());
            SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
            hd_sprites_[s.addr] = t;
        }
    }
    load_walk_cycle();
    if (FileExists((assets_ + "/props/gate.png").c_str())) {
        gate_tip_tex_ = LoadTexture((assets_ + "/props/gate_tip.png").c_str());
        gate_tex_ = LoadTexture((assets_ + "/props/gate.png").c_str());
    }
    if (FileExists((assets_ + "/props/log.png").c_str())) {
        log_tex_ = LoadTexture((assets_ + "/props/log.png").c_str());
        SetTextureFilter(log_tex_, TEXTURE_FILTER_BILINEAR);
    }
    hud_ = std::make_unique<Hud>(HUD_FONT);

    opaque_ = LoadShaderFromMemory(nullptr,
        "#version 330\nin vec2 fragTexCoord; in vec4 fragColor; out vec4 finalColor;\n"
        "uniform sampler2D texture0; uniform vec4 colDiffuse;\n"
        "void main() { finalColor = vec4(texture(texture0, fragTexCoord).rgb, 1.0) * colDiffuse * fragColor; }\n");
    load_ambient();
    load_anims();
    TraceLog(LOG_INFO, "HD overrides: %d rooms, %d sprites, %d walk frames", int(hd_rooms_.size()),
             int(hd_sprites_.size()), int(walk_[0].size()));
    rebuild_palette_textures();
}

Renderer::~Renderer() {
    UnloadRenderTexture(canvas_);
    UnloadRenderTexture(field_);
    UnloadRenderTexture(prev_field_);
    UnloadTexture(vram_tex_);
    for (auto& t : tiles_) UnloadTexture(t);
    for (auto& set : sprites_)
        for (auto& [_, t] : set) UnloadTexture(t);
    for (auto& [_, t] : hd_rooms_) UnloadTexture(t);
    for (auto& [_, t] : hd_sprites_) UnloadTexture(t);
    for (auto& dir : walk_)
        for (auto& t : dir) UnloadTexture(t);
    if (log_tex_.id) UnloadTexture(log_tex_);
    if (gate_tex_.id) UnloadTexture(gate_tex_), UnloadTexture(gate_tip_tex_);
    if (ambient_ok_) UnloadShader(ambient_), UnloadTexture(air_tex_);
    if (water_ok_) UnloadShader(water_), UnloadTexture(water_mask_);
    if (glow_.id) UnloadShader(glow_);
    UnloadShader(opaque_);
    for (auto& [_, t] : open_rooms_) UnloadTexture(t);
    if (plume_.id) UnloadShader(plume_);
    for (auto& [_, t] : glow_masks_) UnloadTexture(t);
    for (auto& [_, t] : fire_masks_) UnloadTexture(t);
    for (auto& a : anims_)
        for (auto& t : a->frames) UnloadTexture(t);
}

const Texture2D* Renderer::sprite_texture(uint16_t addr) const {
    if (auto it = hd_sprites_.find(addr); it != hd_sprites_.end()) return &it->second;
    if (auto it = sprites_[0].find(addr); it != sprites_[0].end()) return &it->second;
    return nullptr;
}

void Renderer::load_walk_cycle() {
    for (int i = 0;; i++) {
        std::string path = assets_ + "/anim/walk_r_" + std::to_string(i) + ".png";
        if (!FileExists(path.c_str())) break;
        Image img = LoadImage(path.c_str());
        walk_[0].push_back(LoadTextureFromImage(img));
        ImageFlipHorizontal(&img);
        walk_[1].push_back(LoadTextureFromImage(img));
        UnloadImage(img);
    }
    for (auto& dir : walk_)
        for (auto& t : dir) SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
}

// HD walk-cycle frame to draw for the hero instead of the game's frame, or null.
const Texture2D* Renderer::hero_override(const ObjectView& o) {
    if (!smooth_anim || walk_[0].empty() || o.slot != 0 || o.src_x || o.src_y) return nullptr;
    bool right = is_any(o.sprite, WALK_RIGHT) || o.sprite == STAND_RIGHT;
    bool left = is_any(o.sprite, WALK_LEFT) || o.sprite == STAND_LEFT;
    if (!right && !left) return nullptr;
    if (is_any(o.sprite, WALK_RIGHT) || is_any(o.sprite, WALK_LEFT)) {
        last_walk_seen_ = time_;
        walk_dir_ = right ? 0 : 1;
    }
    if (time_ - last_walk_seen_ > WALK_HOLD || walk_dir_ != (right ? 0 : 1)) return nullptr;
    const auto& frames = walk_[walk_dir_];
    return &frames[size_t(walk_phase_) % frames.size()];
}

void Renderer::rebuild_palette_textures() {
    for (int p = 0; p < 2; p++) {
        if (tiles_[p].id) UnloadTexture(tiles_[p]);
        for (auto& [_, t] : sprites_[p]) UnloadTexture(t);
        sprites_[p].clear();

        Palette pal = cga_palette(p, bright);
        tiles_[p] = texture_from(data_.decode_tile_atlas(pal), 128, 128, TEXTURE_FILTER_POINT);
        for (const auto& s : data_.sprites())
            sprites_[p][s.addr] = texture_from(data_.decode_sprite(s, pal), s.w_px, s.h, TEXTURE_FILTER_POINT);
    }
    built_bright_ = bright;
}

void Renderer::frame(const uint8_t* ram, const uint8_t* vram, const std::vector<ObjectView>& objects, float dt) {
    time_ += dt;
    if (bright != built_bright_) rebuild_palette_textures();

    int room = GameData::room(ram);
    if (room != room_) {
        if (room_ >= 0) start_transition();
        room_ = room;
    }
    if (transition_ < 1.0f) transition_ = std::min(1.0f, transition_ + dt / TRANSITION_SECONDS);
    if (!walk_[0].empty() && !transitioning()) {
        walk_phase_ += dt * walk_[0].size() / WALK_CYCLE_SECONDS;
        walk_phase_ = std::fmod(walk_phase_, float(walk_[0].size()));
    }

    int palette = GameData::palette(ram);
    update_vram_texture(vram, palette);

    // While sliding, the emulation is paused, so the new room is drawn once and held.
    draw_field(ram, objects, field_);

    BeginTextureMode(canvas_);
    ClearBackground(BLACK);
    if (classic) {
        // Untouched CGA output at 4:3, for comparison.
        DrawTexturePro(vram_tex_, {0, 0, 320, 200}, {240, 0, 1440, 1080}, {0, 0}, 0, WHITE);
    } else {
        // The field is opaque, but translucent effects drawn into its render texture
        // lowered its stored alpha (alpha is blended like colour); draw it back opaque.
        BeginShaderMode(opaque_);
        if (transition_ < 1.0f) {
            float e = smoothstep(transition_);
            if (dir_x_ || dir_y_) {
                Vector2 out{-dir_x_ * e * CANVAS_W, -dir_y_ * e * FIELD_PX_H};
                Vector2 in{dir_x_ * (1 - e) * CANVAS_W, dir_y_ * (1 - e) * FIELD_PX_H};
                DrawTextureRec(prev_field_.texture, flipped(prev_field_), out, WHITE);
                DrawTextureRec(field_.texture, flipped(field_), in, WHITE);
            } else {
                DrawTextureRec(prev_field_.texture, flipped(prev_field_), {0, 0}, WHITE);
                DrawTextureRec(field_.texture, flipped(field_), {0, 0}, Fade(WHITE, e));
            }
        } else {
            DrawTextureRec(field_.texture, flipped(field_), {0, 0}, WHITE);
        }
        EndShaderMode();
        if (classic_hud) {
            draw_hud();
        } else {
            Hud::Icons icons{sprite_texture(LIFE_ICON), {}};
            for (int i = 0; i < 4; i++) icons.weapons[i] = sprite_texture(WEAPON_ICONS[i]);
            HudState hs = GameData::hud(ram);
            hs.infinite_lives = infinite_lives;
            hud_->draw(hs, icons,
                       {0, float(FIELD_PX_H), float(CANVAS_W), float(CANVAS_H - FIELD_PX_H)}, dt);
        }
    }

    if (paused) {
        auto centred = [](const char* t, int y, int size, float alpha) {
            DrawText(t, (CANVAS_W - MeasureText(t, size)) / 2, y, size, Fade(RAYWHITE, alpha));
        };
        if (picker_room >= 0) {
            char title[32];
            std::snprintf(title, sizeof title, "TELEPORT  <  ROOM %02X  >", picker_room);
            centred(title, 120, 72, 1.0f);
            Rectangle box{CANVAS_W / 2.0f - 640, 230, 1280, 640};
            auto it = hd_rooms_.find(picker_room);
            if (it != hd_rooms_.end()) {
                const Texture2D& t = it->second;
                DrawTexturePro(t, {0, 0, float(t.width), float(t.height)}, box, {0, 0}, 0, WHITE);
            } else {
                DrawRectangleRec(box, Fade(DARKGRAY, 0.8f));
                centred("no HD background", int(box.y + box.height / 2 - 20), 40, 0.8f);
            }
            DrawRectangleLinesEx(box, 4, RAYWHITE);
            centred(gamepad ? "LEFT / RIGHT  choose      A  go      B  back"
                            : "LEFT / RIGHT  choose      ENTER  go      ESC  back",
                    910, 36, 0.85f);
        } else {
            // Compact panel at the top: the playfield stays undimmed for screenshots.
            DrawRectangleRounded({CANVAS_W / 2.0f - 640, 16, 1280, 168}, 0.2f, 8, Fade(BLACK, 0.72f));
            char title[48];
            std::snprintf(title, sizeof title, "PAUSED   -   ROOM %02X", room_);
            centred(title, 30, 64, 1.0f);
            centred(gamepad ? "START  resume      Y  new game      X  teleport"
                            : "ESC  resume      N  new game      T  teleport      X  quit",
                    104, 32, 0.85f);
            std::string ctl = "CONTROLS: ARROWS" + (layout_name == "ARROWS" ? std::string() : " + " + layout_name) +
                              "   (K to change)" + (layout_name == "WASD" ? "   ENTER: next weapon" : "");
            centred(ctl.c_str(), 144, 26, 0.7f);
        }
    }
    if (time_ < toast_until_ && !paused) {
        float a = std::min(1.0f, (toast_until_ - time_) / 0.4f);
        int w = MeasureText(toast_.c_str(), 40) + 60;
        DrawRectangleRounded({float(CANVAS_W - w) / 2, 40, float(w), 64}, 0.4f, 8, Fade(BLACK, 0.7f * a));
        DrawText(toast_.c_str(), (CANVAS_W - w) / 2 + 30, 52, 40, Fade(RAYWHITE, a));
    }
    if (debug) {
        char line[128];
        std::snprintf(line, sizeof line, "room %02x  palette %d  fps %d  %s", room, palette, GetFPS(),
                      hd_rooms_.count(room) ? "HD room" : "original tiles");
        DrawRectangle(0, 0, 760, 40, Fade(BLACK, 0.6f));
        DrawText(line, 12, 8, 24, RAYWHITE);
        for (const auto& o : objects) {
            DrawRectangleLines(int(o.fx * SCALE), int(o.fy * SCALE), o.w * SCALE, o.h * SCALE, YELLOW);
            std::snprintf(line, sizeof line, "%04x", o.sprite);
            DrawText(line, int(o.fx * SCALE), int(o.fy * SCALE) - 20, 18, YELLOW);
        }
    }
    EndTextureMode();
}

void Renderer::start_transition() {
    // field_ still holds the last frame of the old room.
    std::swap(field_, prev_field_);
    dir_x_ = dir_y_ = 0;
    if (last_player_x_ < 24) dir_x_ = -1;
    else if (last_player_x_ > FIELD_W - 48) dir_x_ = 1;
    else if (last_player_y_ < 16) dir_y_ = -1;
    else if (last_player_y_ > FIELD_H - 40) dir_y_ = 1;
    transition_ = 0.0f;
}

void Renderer::draw_background(int room, int palette) {
    if (is_cave(palette)) {
        DrawRectangleGradientV(0, 0, CANVAS_W, FIELD_PX_H, {8, 10, 24, 255}, {28, 26, 46, 255});
        return;
    }
    DrawRectangleGradientV(0, 0, CANVAS_W, FIELD_PX_H, {38, 92, 186, 255}, {164, 206, 236, 255});

    // Slow clouds and two hill layers; phase depends on the room so neighbours differ.
    for (int i = 0; i < 6; i++) {
        float x = std::fmod(i * 410.0f + time_ * (8 + i * 3) + room * 137.0f, CANVAS_W + 400.0f) - 200;
        float y = 80 + (i * 97 + room * 31) % 260;
        Color c = Fade(WHITE, 0.35f);
        DrawEllipse(int(x), int(y), 120, 34, c);
        DrawEllipse(int(x + 70), int(y - 18), 80, 30, c);
        DrawEllipse(int(x - 60), int(y + 6), 70, 22, c);
    }
    auto hills = [&](float base, float amp, float freq, float phase, Color c) {
        for (int x = 0; x < CANVAS_W; x += 6) {
            float h = base + amp * std::sin(x * freq + phase) + amp * 0.4f * std::sin(x * freq * 2.7f + phase * 1.9f);
            DrawRectangle(x, int(FIELD_PX_H - h), 6, int(h), c);
        }
    };
    hills(330, 60, 0.0021f, room * 1.3f, {92, 140, 150, 255});
    hills(230, 45, 0.0037f, room * 2.1f + 1.0f, {52, 104, 92, 255});
}

void Renderer::draw_field(const uint8_t* ram, const std::vector<ObjectView>& objects, RenderTexture2D& target) {
    int room = GameData::room(ram), palette = GameData::palette(ram);
    BeginTextureMode(target);
    ClearBackground(BLACK);

    auto hd = hd_rooms_.find(room);
    if (hd != hd_rooms_.end()) {
        const Texture2D& t = hd->second;
        DrawTexturePro(t, {0, 0, float(t.width), float(t.height)}, {0, 0, float(CANVAS_W), float(FIELD_PX_H)},
                       {0, 0}, 0, WHITE);
    } else {
        draw_background(room, palette);
        const uint8_t* map = GameData::tilemap(ram);
        const float ts = 8.0f * SCALE;
        for (int i = 0; i < MAP_W * MAP_H; i++) {
            int t = map[i];
            if (!t) continue;
            Rectangle src{float(t % 16 * 8), float(t / 16 * 8), 8, 8};
            DrawTexturePro(tiles_[palette], src, {(i % MAP_W) * ts, (i / MAP_W) * ts, ts, ts}, {0, 0}, 0, WHITE);
        }
    }

    const bool hd_room = hd != hd_rooms_.end();
    if (hd_room) draw_volcano_smoke(room);
    if (hd_room) draw_water(ram, hd->second);
    if (hd_room) draw_swamp_bubbles(ram);
    if (hd_room) draw_mushrooms(ram, hd->second);
    if (hd_room) draw_lights(ram);
    if (hd_room) draw_crystals(room, hd->second);
    if (hd_room) draw_braziers(ram);
    if (hd_room) draw_smoke(ram);

    if (hd_room) draw_ambient(ram);
    if (hd_room) draw_opened(ram);
    if (hd_room) draw_gates(ram);
    // Logs first: everything else stands on them.
    if (hd_room && log_tex_.id)
        for (const auto& o : objects)
            if (o.sprite == LOG_SPRITE)
                DrawTexturePro(log_tex_, {0, 0, float(log_tex_.width), float(log_tex_.height)},
                               {o.fx * SCALE, o.fy * SCALE, float(o.w * SCALE), float(o.h * SCALE)}, {0, 0}, 0,
                               WHITE);
    for (const auto& o : objects) {
        if (o.sprite == LOG_SPRITE) continue;  // tiles in the original: already drawn
        if (hd_room && ambient) draw_treasure_glow(o);
        Rectangle dst{o.fx * SCALE, o.fy * SCALE, float(o.w * SCALE), float(o.h * SCALE)};
        auto rec = data_.sprite_at(o.sprite);
        auto hs = hd_sprites_.find(o.sprite);
        auto anim = anim_by_sprite_.find(o.sprite);
        if (anim != anim_by_sprite_.end() && !o.src_x && !o.src_y) {
            // own cycle; objects offset so neighbours (the two drummers) aren't in step
            const Anim& a = *anim->second;
            const Texture2D& t = a.frames[size_t(time_ * a.fps + o.slot * 2) % a.frames.size()];
            DrawTexturePro(t, {0, 0, float(t.width), float(t.height)}, dst, {0, 0}, 0, WHITE);
        } else if (const Texture2D* walk = hero_override(o)) {
            DrawTexturePro(*walk, {0, 0, float(walk->width), float(walk->height)}, dst, {0, 0}, 0, WHITE);
        } else if (hs != hd_sprites_.end()) {
            // HD frame covers the whole original frame; map the visible window proportionally.
            const Texture2D& t = hs->second;
            float sx = float(t.width) / rec->w_px, sy = float(t.height) / rec->h;
            DrawTexturePro(t, {o.src_x * sx, o.src_y * sy, o.w * sx, o.h * sy}, dst, {0, 0}, 0, WHITE);
        } else {
            DrawTexturePro(sprites_[palette].at(o.sprite), {float(o.src_x), float(o.src_y), float(o.w), float(o.h)},
                           dst, {0, 0}, 0, WHITE);
        }
    }
    EndTextureMode();

    const uint8_t* player = ram + addr::OBJECTS;
    if (player[0] & 0x80) {
        last_player_x_ = player[0x1a] * 4;
        last_player_y_ = player[0x1b] * 2;
    }
}

void Renderer::update_vram_texture(const uint8_t* vram, int palette) {
    Palette pal = cga_palette(palette, bright);
    pal[0] = {0, 0, 0, 255};
    static std::vector<Rgba> px(320 * 200);
    for (int y = 0; y < 200; y++) {
        const uint8_t* line = vram + (y & 1) * 0x2000 + (y >> 1) * 80;
        for (int xb = 0; xb < 80; xb++)
            for (int k = 0; k < 4; k++) px[y * 320 + xb * 4 + k] = pal[(line[xb] >> (6 - 2 * k)) & 3];
    }
    UpdateTexture(vram_tex_, px.data());
}

void Renderer::draw_hud() {
    // Original HUD pixels (bars, score, weapons) at 3x, centred under the playfield.
    const int w = 320 * HUD_SCALE, h = HUD_H * HUD_SCALE, x = (CANVAS_W - w) / 2;
    DrawRectangleGradientV(0, FIELD_PX_H, CANVAS_W, CANVAS_H - FIELD_PX_H, {20, 16, 12, 255}, {6, 5, 4, 255});
    DrawTexturePro(vram_tex_, {0, float(HUD_Y), 320, float(HUD_H)},
                   {float(x), float(FIELD_PX_H), float(w), float(h)}, {0, 0}, 0, WHITE);
}

void Renderer::present() const {
    BeginDrawing();
    ClearBackground(BLACK);
    float sw = float(GetScreenWidth()), sh = float(GetScreenHeight());
    float s = std::min(sw / CANVAS_W, sh / CANVAS_H);
    float w = CANVAS_W * s, h = CANVAS_H * s;
    DrawTexturePro(canvas_.texture, flipped(canvas_), {(sw - w) / 2, (sh - h) / 2, w, h}, {0, 0}, 0, WHITE);
    EndDrawing();
}

void Renderer::save_canvas(const char* path) const {
    Image img = LoadImageFromTexture(canvas_.texture);
    ImageFlipVertical(&img);
    ExportImage(img, path);
    UnloadImage(img);
}

void Renderer::toast(std::string message) {
    toast_ = std::move(message);
    toast_until_ = time_ + 1.8f;
}


void Renderer::load_anims() {
    for (const AnimDef& def : ANIM_DEFS) {
        auto anim = std::make_unique<Anim>();
        anim->fps = def.fps;
        for (int i = 0;; i++) {
            std::string path = assets_ + "/anim/" + def.name + "_" + std::to_string(i) + ".png";
            if (!FileExists(path.c_str())) break;
            Texture2D t = LoadTexture(path.c_str());
            SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
            anim->frames.push_back(t);
        }
        if (anim->frames.empty()) continue;
        for (uint16_t s : def.sprites) anim_by_sprite_[s] = anim.get();
        anims_.push_back(std::move(anim));
    }
}

void Renderer::draw_gates(const uint8_t* ram) {
    int room = GameData::room(ram);
    if (!gate_tex_.id || std::find(std::begin(GATE_ROOMS), std::end(GATE_ROOMS), room) == std::end(GATE_ROOMS)) return;
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE;
    for (int i = 0; i < MAP_W * MAP_H; i++) {
        const Texture2D* t = m[i] == GATE_TIP ? &gate_tip_tex_ : m[i] == GATE_STAKE ? &gate_tex_ : nullptr;
        if (t)
            DrawTexturePro(*t, {0, 0, float(t->width), float(t->height)},
                           {(i % MAP_W) * cell, (i / MAP_W) * cell, cell, cell}, {0, 0}, 0, WHITE);
    }
}

namespace {

// Rooms under ground or indoors: no sky mist (grotto, mines, temple halls, caves).
bool indoor_room(int room, int palette) {
    return palette == 1 || (room >= 0x07 && room <= 0x10) || (room >= 0x1c && room <= 0x23);
}

constexpr int AIR_K = 4, AIR_W = MAP_W * AIR_K, AIR_H = MAP_H * AIR_K;  // mist mask resolution

constexpr uint8_t WATER_TILE = 138, FALL_TILE = 31;  // river / lake fill, waterfall / channel

// In-place separable box blur, `passes` times, radius r (on a w x h float grid).
void box_blur(std::vector<float>& a, int w, int h, int r, int passes) {
    std::vector<float> b(a.size());
    for (int p = 0; p < passes; p++) {
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                float s = 0;
                for (int d = -r; d <= r; d++) s += a[y * w + std::clamp(x + d, 0, w - 1)];
                b[y * w + x] = s / (2 * r + 1);
            }
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                float s = 0;
                for (int d = -r; d <= r; d++) s += b[std::clamp(y + d, 0, h - 1) * w + x];
                a[y * w + x] = s / (2 * r + 1);
            }
    }
}

// Tiles that are open air for the mist even though they are drawn: clouds.
bool air_tile(uint8_t t) { return t == 0 || (t >= 21 && t <= 28); }

}  // namespace

void Renderer::load_ambient() {
    std::string fs = assets_ + "/shaders/ambient.fs";
    if (!FileExists(fs.c_str())) return;
    ambient_ = LoadShader(nullptr, fs.c_str());
    std::vector<uint8_t> blank(AIR_W * AIR_H, 0);
    Image m{blank.data(), AIR_W, AIR_H, 1, PIXELFORMAT_UNCOMPRESSED_GRAYSCALE};
    air_tex_ = LoadTextureFromImage(m);
    SetTextureFilter(air_tex_, TEXTURE_FILTER_BILINEAR);

    auto set = [&](const char* name, float v) {
        SetShaderValue(ambient_, GetShaderLocation(ambient_, name), &v, SHADER_UNIFORM_FLOAT);
    };
    float mist[4] = {0.86f, 0.92f, 0.90f, 1}, cloud[4] = {1, 1, 1, 1};
    SetShaderValue(ambient_, GetShaderLocation(ambient_, "mistColor"), mist, SHADER_UNIFORM_VEC4);
    SetShaderValue(ambient_, GetShaderLocation(ambient_, "cloudColor"), cloud, SHADER_UNIFORM_VEC4);
    set("mistCenter", 0.5f), set("mistWidth", 0.16f), set("mistStrength", 0.8f);
    set("cloudCenter", 0.14f), set("cloudWidth", 0.12f), set("cloudStrength", 0.0f);  // read as smoke: off
    ambient_ok_ = ambient_.id != 0;

    if (FileExists((assets_ + "/shaders/plume.fs").c_str())) plume_ = LoadShader(nullptr, (assets_ + "/shaders/plume.fs").c_str());
    std::string gfs = assets_ + "/shaders/glow.fs";
    if (FileExists(gfs.c_str())) glow_ = LoadShader(nullptr, gfs.c_str());
    for (int r = 0; r < 0x40; r++) {
        char path[64];
        std::snprintf(path, sizeof path, "/glow/room_%02x.png", r);
        if (FileExists((assets_ + path).c_str())) {
            Texture2D t = LoadTexture((assets_ + path).c_str());
            SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
            glow_masks_[r] = t;
        }
        std::snprintf(path, sizeof path, "/glow/room_%02x_fire.png", r);
        if (FileExists((assets_ + path).c_str())) {
            Texture2D t = LoadTexture((assets_ + path).c_str());
            SetTextureFilter(t, TEXTURE_FILTER_BILINEAR);
            fire_masks_[r] = t;
        }
        std::snprintf(path, sizeof path, "/glow/room_%02x_fire.txt", r);
        if (FileExists((assets_ + path).c_str())) {
            if (char* text = LoadFileText((assets_ + path).c_str())) {  // null when the file is empty
                float x, y, w;
                int n = 0;
                for (const char* p = text; std::sscanf(p, "%f %f %f%n", &x, &y, &w, &n) == 3; p += n)
                    fire_points_[r].push_back({x, y});
                UnloadFileText(text);
            }
        }
    }
    for (int r = 0; r < 0x40; r++) {
        char path[64];
        std::snprintf(path, sizeof path, "/rooms/room_%02x_open.png", r);
        if (FileExists((assets_ + path).c_str())) open_rooms_[r] = LoadTexture((assets_ + path).c_str());
    }
    if (char* text = LoadFileText((assets_ + "/glow/open_cells.txt").c_str())) {
        int r, c, w, n = 0;
        for (const char* p = text; std::sscanf(p, "%d %d %d%n", &r, &c, &w, &n) == 3; p += n) open_cells_[r].push_back({c, w});
        UnloadFileText(text);
    }
    if (char* text = LoadFileText((assets_ + "/glow/volcano.txt").c_str())) {
        int r, n = 0;
        float x, y;
        for (const char* p = text; std::sscanf(p, "%d %f %f%n", &r, &x, &y, &n) == 3; p += n) volcano_[r] = {x, y};
        UnloadFileText(text);
    }
    std::string wfs = assets_ + "/shaders/water.fs";
    if (FileExists(wfs.c_str())) {
        water_ = LoadShader(nullptr, wfs.c_str());
        std::vector<uint8_t> z(AIR_W * AIR_H * 4, 0);
        Image wm{z.data(), AIR_W, AIR_H, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8};
        water_mask_ = LoadTextureFromImage(wm);
        SetTextureFilter(water_mask_, TEXTURE_FILTER_BILINEAR);
        water_ok_ = water_.id != 0;
    }
}

void Renderer::draw_ambient(const uint8_t* ram) {
    if (!ambient_ok_ || !ambient) return;
    int room = GameData::room(ram);
    if (indoor_room(room, GameData::palette(ram))) return;
    // Air mask at 4x the cell grid, box-blurred (3 passes ~ gaussian) so the mist thins
    // out smoothly near solid ground with no visible cell edges.
    const uint8_t* m = GameData::tilemap(ram);
    static std::vector<float> a(AIR_W * AIR_H), b(AIR_W * AIR_H);
    for (int y = 0; y < AIR_H; y++)
        for (int x = 0; x < AIR_W; x++)
            a[y * AIR_W + x] = air_tile(m[(y / AIR_K) * MAP_W + x / AIR_K]) ? 1.0f : 0.0f;
    const int r = 3;
    for (int pass = 0; pass < 3; pass++) {
        for (int y = 0; y < AIR_H; y++)  // horizontal
            for (int x = 0; x < AIR_W; x++) {
                float s = 0;
                for (int d = -r; d <= r; d++) s += a[y * AIR_W + std::clamp(x + d, 0, AIR_W - 1)];
                b[y * AIR_W + x] = s / (2 * r + 1);
            }
        for (int y = 0; y < AIR_H; y++)  // vertical
            for (int x = 0; x < AIR_W; x++) {
                float s = 0;
                for (int d = -r; d <= r; d++) s += b[std::clamp(y + d, 0, AIR_H - 1) * AIR_W + x];
                a[y * AIR_W + x] = s / (2 * r + 1);
            }
    }
    static std::vector<uint8_t> air(AIR_W * AIR_H);
    for (int i = 0; i < AIR_W * AIR_H; i++) air[i] = uint8_t(std::clamp(a[i] * 1.6f - 0.6f, 0.0f, 1.0f) * 255);
    UpdateTexture(air_tex_, air.data());
    float t = time_;
    SetShaderValue(ambient_, GetShaderLocation(ambient_, "time"), &t, SHADER_UNIFORM_FLOAT);
    BeginShaderMode(ambient_);
    DrawTexturePro(air_tex_, {0, 0, float(AIR_W), float(AIR_H)}, {0, 0, float(CANVAS_W), float(FIELD_PX_H)}, {0, 0}, 0,
                   WHITE);
    EndShaderMode();
}

void Renderer::draw_water(const uint8_t* ram, const Texture2D& bg) {
    if (!water_ok_ || !ambient) return;
    const uint8_t* m = GameData::tilemap(ram);
    auto is_water = [&](int c, int r) {
        if (c < 0 || c >= MAP_W || r < 0 || r >= MAP_H) return false;
        uint8_t t = m[r * MAP_W + c];
        return t == WATER_TILE || t == FALL_TILE;
    };
    bool any = false;
    static std::vector<float> w(AIR_W * AIR_H), top(AIR_W * AIR_H), fall(AIR_W * AIR_H);
    for (int y = 0; y < AIR_H; y++)
        for (int x = 0; x < AIR_W; x++) {
            int c = x / AIR_K, r = y / AIR_K, i = y * AIR_W + x;
            bool wt = is_water(c, r);
            any |= wt;
            w[i] = wt ? 1.0f : 0.0f;
            top[i] = wt && !is_water(c, r - 1) && y % AIR_K < 2 ? 1.0f : 0.0f;  // upper half of the top cell
            // a waterfall: water whose cells above and below are water but not left or right
            fall[i] = wt && m[r * MAP_W + c] == FALL_TILE && (is_water(c, r - 1) || is_water(c, r + 1)) ? 1.0f : 0.0f;
        }
    if (!any) return;
    box_blur(w, AIR_W, AIR_H, 1, 2);
    box_blur(top, AIR_W, AIR_H, 1, 2);
    box_blur(fall, AIR_W, AIR_H, 1, 1);
    static std::vector<uint8_t> px(AIR_W * AIR_H * 4);
    for (int i = 0; i < AIR_W * AIR_H; i++) {
        px[i * 4 + 0] = uint8_t(std::clamp(w[i], 0.0f, 1.0f) * 255);
        px[i * 4 + 1] = uint8_t(std::clamp(top[i] * 2, 0.0f, 1.0f) * 255);
        px[i * 4 + 2] = uint8_t(std::clamp(fall[i], 0.0f, 1.0f) * 255);
        px[i * 4 + 3] = 255;
    }
    UpdateTexture(water_mask_, px.data());
    float t = time_;
    float cs[2] = {1.0f / MAP_W, 1.0f / MAP_H};
    SetShaderValue(water_, GetShaderLocation(water_, "time"), &t, SHADER_UNIFORM_FLOAT);
    SetShaderValue(water_, GetShaderLocation(water_, "cellSize"), cs, SHADER_UNIFORM_VEC2);
    BeginShaderMode(water_);
    SetShaderValueTexture(water_, GetShaderLocation(water_, "waterMask"), water_mask_);
    DrawTexturePro(bg, {0, 0, float(bg.width), float(bg.height)}, {0, 0, float(CANVAS_W), float(FIELD_PX_H)}, {0, 0}, 0,
                   WHITE);
    EndShaderMode();
}

void Renderer::draw_swamp_bubbles(const uint8_t* ram) {
    if (!ambient) return;
    constexpr uint8_t SWAMP_TILE = 137;
    constexpr int PER_CELL = 3;             // bubbles per swamp cell
    constexpr float RISE = 1.6f, POP = 0.35f;  // seconds rising, seconds popping
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE, art = 5.0f;  // art pixel: matches the backgrounds' grid
    auto hash = [](uint32_t x) {
        x ^= x >> 16, x *= 0x7feb352d, x ^= x >> 15, x *= 0x846ca68b, x ^= x >> 16;
        return (x & 0xffffff) / float(0x1000000);
    };
    auto snap = [&](float v) { return std::floor(v / art) * art; };
    for (int i = 0; i < MAP_W * MAP_H; i++) {
        if (m[i] != SWAMP_TILE) continue;
        float cx = (i % MAP_W) * cell, top = (i / MAP_W) * cell + cell * 0.25f;
        for (int k = 0; k < PER_CELL; k++) {
            uint32_t id = uint32_t(i * 7 + k * 131);
            float period = RISE + POP + 0.6f + hash(id) * 1.6f;   // pause between bubbles
            float t = std::fmod(time_ + hash(id + 1) * period, period);
            float x = snap(cx + 8 + hash(id + 2) * (cell - 16) + std::sin(time_ * 2 + id) * 3);
            if (t < RISE) {  // rising through the murky water
                float a = t / RISE;
                float y = snap(top + cell * 1.1f * (1 - a));
                float r = art * (1.0f + a * 1.4f);
                DrawCircle(int(x), int(y), r + 2, Fade({40, 55, 25, 255}, 0.5f * (0.4f + 0.6f * a)));  // dark rim
                DrawCircle(int(x), int(y), r, Fade({150, 190, 90, 255}, 0.55f + 0.35f * a));
                DrawCircle(int(x - r * 0.35f), int(y - r * 0.35f), r * 0.4f, Fade({240, 250, 210, 255}, 0.9f));
            } else if (t < RISE + POP) {  // pop: a ring spreading on the surface
                float a = (t - RISE) / POP;
                for (int ring = 0; ring < 2; ring++)
                    DrawEllipseLines(int(x), int(top), art * (2.0f + a * 4) + ring, art * (0.8f + a * 1.4f) + ring,
                                     Fade({215, 235, 160, 255}, 0.9f * (1 - a)));
            }
        }
    }
}

// Gold the hero collects: a pulsing glow with slowly turning rays behind the sprite.
void Renderer::draw_treasure_glow(const ObjectView& o) {
    float cx = (o.fx + o.w * 0.5f) * SCALE, cy = (o.fy + o.h * 0.5f) * SCALE;
    if (o.sprite == 0xb547 || o.sprite == 0xb56d) {  // fireball: flickering fiery halo
        float f = 0.5f + 0.3f * std::sin(time_ * 11.0f + cx) + 0.2f * std::sin(time_ * 19.0f + cy);
        BeginBlendMode(BLEND_ADDITIVE);
        DrawCircleGradient({cx, cy}, o.w * SCALE * (1.3f + 0.3f * f), Fade({255, 120, 30, 255}, 0.35f + 0.15f * f),
                           Fade({255, 60, 10, 255}, 0));
        EndBlendMode();
        return;
    }
    if (o.sprite != 0xabf7 && o.sprite != 0xac15) return;
    float pulse = 0.5f + 0.5f * std::sin(time_ * 3.0f + cx * 0.01f);
    float r = o.w * SCALE * (0.75f + 0.12f * pulse);
    BeginBlendMode(BLEND_ADDITIVE);  // light, not paint: stays golden on any background
    DrawCircleGradient({cx, cy}, r, Fade({255, 200, 60, 255}, 0.35f + 0.2f * pulse), Fade({255, 160, 20, 255}, 0));
    const int rays = 10;
    for (int i = 0; i < rays; i++) {
        float a = time_ * 0.6f + i * 2 * PI / rays;
        float len = r * (i % 2 ? 0.9f : 1.25f) * (0.85f + 0.15f * pulse);
        Vector2 tip{cx + std::cos(a) * len, cy + std::sin(a) * len};
        Vector2 l{cx + std::cos(a + 0.12f) * r * 0.35f, cy + std::sin(a + 0.12f) * r * 0.35f};
        Vector2 rr{cx + std::cos(a - 0.12f) * r * 0.35f, cy + std::sin(a - 0.12f) * r * 0.35f};
        DrawTriangle(tip, l, rr, Fade({255, 210, 90, 255}, 0.35f + 0.25f * pulse));
        DrawTriangle(tip, rr, l, Fade({255, 210, 90, 255}, 0.35f + 0.25f * pulse));
    }
    EndBlendMode();
}

// Mine lanterns flicker and skulls' eyes flare now and then (dark rooms only). Both are
// room tiles in the original, so their place on the painted background is known.
void Renderer::draw_lights(const uint8_t* ram) {
    if (!ambient) return;
    int room = GameData::room(ram);
    if (!indoor_room(room, GameData::palette(ram))) return;
    constexpr uint8_t LAMP_BODY = 107, SKULL_LEFT = 78;
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE;
    auto noise = [](float t, float seed) {  // smooth flicker in 0..1
        return 0.5f + 0.25f * std::sin(t * 7.3f + seed) + 0.15f * std::sin(t * 13.1f + seed * 2.1f) +
               0.1f * std::sin(t * 23.7f + seed * 3.3f);
    };
    BeginBlendMode(BLEND_ADDITIVE);
    for (int i = 0; i < MAP_W * MAP_H; i++) {
        float x = (i % MAP_W) * cell, y = (i / MAP_W) * cell;
        if (m[i] == LAMP_BODY) {  // lantern: 2x2 tiles, this is its bottom-left
            float cx = x + cell, cy = y + cell * 0.35f, f = noise(time_, float(i));
            DrawCircleGradient({cx, cy}, cell * (2.2f + 0.4f * f), Fade({255, 170, 70, 255}, 0.22f + 0.12f * f),
                               Fade({255, 120, 30, 255}, 0));
            // flame: a small teardrop that sways and stretches
            float sway = std::sin(time_ * 6.0f + i) * 3.0f, h = cell * (0.38f + 0.12f * f);
            DrawTriangle({cx + sway, cy - h}, {cx - 7, cy + 4}, {cx + 7, cy + 4}, Fade({255, 210, 110, 255}, 0.75f));
            DrawCircle(int(cx), int(cy + 3), 7, Fade({255, 190, 90, 255}, 0.7f));
            DrawCircle(int(cx), int(cy + 3), 3, Fade({255, 250, 220, 255}, 0.8f));
        } else if (m[i] == SKULL_LEFT) {  // skull: 2 tiles wide; eyes flare for about a second
            float period = 5.0f + std::fmod(i * 0.37f, 3.0f);
            float t = std::fmod(time_ + i * 1.7f, period);
            if (t < 1.2f) {
                float a = std::sin(t / 1.2f * PI);  // fade in and out
                float ey = y + cell * 0.45f;
                for (float ex : {x + cell * 0.72f, x + cell * 1.28f}) {
                    DrawCircleGradient({ex, ey}, cell * 0.55f, Fade({255, 60, 30, 255}, 0.55f * a),
                                       Fade({255, 30, 10, 255}, 0));
                    DrawCircle(int(ex), int(ey), 4, Fade({255, 200, 160, 255}, 0.9f * a));
                }
            }
        }
    }
    EndBlendMode();
}

// Cave mushrooms (2x2 tiles, 142 at the cap's top-left): the painted mushroom sways from
// its base (the background is redrawn in thin strips shifted more towards the cap) and
// its cap glows softly. Dark rooms only.
void Renderer::draw_mushrooms(const uint8_t* ram, const Texture2D& bg) {
    if (!ambient) return;
    if (!indoor_room(GameData::room(ram), GameData::palette(ram))) return;
    constexpr uint8_t MUSHROOM_TOP_LEFT = 142;
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE;
    const float sx = float(bg.width) / CANVAS_W, sy = float(bg.height) / FIELD_PX_H;
    for (int i = 0; i < MAP_W * MAP_H; i++) {
        if (m[i] != MUSHROOM_TOP_LEFT) continue;
        // box a bit wider than the 2x2 cells and reaching above them (painted caps are bigger)
        float x0 = (i % MAP_W) * cell - cell * 0.25f, w = cell * 2.5f;
        float y1 = (i / MAP_W + 2) * cell, h = cell * 2.6f, y0 = y1 - h;
        float phase = time_ * 1.6f + i * 0.9f;
        float sway = std::sin(phase) * 5.0f + std::sin(phase * 2.3f) * 1.5f;
        const int strips = 26;
        for (int k = 0; k < strips; k++) {
            float ys = y0 + h * k / strips, hs = h / strips + 1;
            float lift = 1.0f - float(k) / strips;  // 1 at the cap, 0 at the base
            float off = std::round(sway * lift * lift);
            DrawTexturePro(bg, {(x0 - off) * sx, ys * sy, w * sx, hs * sy}, {x0, ys, w, hs}, {0, 0}, 0, WHITE);
        }
        float pulse = 0.5f + 0.5f * std::sin(time_ * 2.0f + i);
        BeginBlendMode(BLEND_ADDITIVE);
        DrawCircleGradient({x0 + w / 2 + sway * 0.8f, y1 - cell * 1.4f}, cell * (1.3f + 0.3f * pulse),
                           Fade({255, 90, 120, 255}, 0.18f + 0.14f * pulse), Fade({255, 60, 90, 255}, 0));
        EndBlendMode();
    }
}

void Renderer::draw_crystals(int room, const Texture2D& bg) {
    if (!ambient || !glow_.id) return;
    float t = time_;
    SetShaderValue(glow_, GetShaderLocation(glow_, "time"), &t, SHADER_UNIFORM_FLOAT);
    // crystals pulse slowly, painted flames flicker
    for (auto [masks, flicker] : {std::pair{&glow_masks_, 0.0f}, std::pair{&fire_masks_, 1.0f}}) {
        auto it = masks->find(room);
        if (it == masks->end()) continue;
        SetShaderValue(glow_, GetShaderLocation(glow_, "flicker"), &flicker, SHADER_UNIFORM_FLOAT);
        BeginBlendMode(BLEND_ADDITIVE);
        BeginShaderMode(glow_);
        SetShaderValueTexture(glow_, GetShaderLocation(glow_, "glowMask"), it->second);
        DrawTexturePro(bg, {0, 0, float(bg.width), float(bg.height)}, {0, 0, float(CANVAS_W), float(FIELD_PX_H)}, {0, 0},
                       0, WHITE);
        EndShaderMode();
        EndBlendMode();
    }
}

// Smoke curling up from flames: the original's brazier tiles plus flames found on the
// painted background (not in the mines, where they are closed lanterns).
void Renderer::draw_smoke(const uint8_t* ram) {
    if (!ambient) return;
    int room = GameData::room(ram);
    if (room >= 0x0c && room <= 0x10) return;
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE;
    std::vector<Vector2> src;
    for (int i = 0; i < MAP_W * MAP_H; i++)
        if (m[i] == 141) src.push_back({(i % MAP_W) * cell + cell * 0.5f, (i / MAP_W) * cell});
    if (auto it = fire_points_.find(room); it != fire_points_.end())
        for (Vector2 p : it->second) {
            bool dup = false;
            for (Vector2 q : src) dup |= std::fabs(p.x - q.x) < 60 && std::fabs(p.y - q.y) < 80;
            if (!dup) src.push_back(p);
        }
    constexpr int PUFFS = 6;
    constexpr float LIFE = 3.2f;
    for (size_t s = 0; s < src.size(); s++) {
        for (int k = 0; k < PUFFS; k++) {
            float t = std::fmod(time_ + k * LIFE / PUFFS + s * 0.37f, LIFE) / LIFE;  // 0..1 along the life
            float rise = t * cell * 3.2f;
            float drift = std::sin(time_ * 0.8f + k * 1.3f + s) * cell * 0.25f * t + t * t * cell * 0.4f;
            float r = cell * (0.18f + 0.55f * t);
            float a = std::sin(t * PI) * 0.22f;
            DrawCircle(int(src[s].x + drift), int(src[s].y - rise), r, Fade({190, 185, 180, 255}, a));
            DrawCircle(int(src[s].x + drift - r * 0.3f), int(src[s].y - rise - r * 0.2f), r * 0.6f,
                       Fade({220, 215, 210, 255}, a * 0.7f));
        }
    }
}

// Braziers and fire pits (tile 141 is the flame cell in the original): dancing tongues
// of fire and a flickering warm light.
void Renderer::draw_braziers(const uint8_t* ram) {
    if (!ambient) return;
    constexpr uint8_t FLAME = 141;
    const uint8_t* m = GameData::tilemap(ram);
    const float cell = 8.0f * SCALE;
    BeginBlendMode(BLEND_ADDITIVE);
    for (int i = 0; i < MAP_W * MAP_H; i++) {
        if (m[i] != FLAME) continue;
        float cx = (i % MAP_W) * cell + cell * 0.5f, base = (i / MAP_W + 1) * cell - cell * 0.15f;
        float f = 0.5f + 0.3f * std::sin(time_ * 9.0f + i) + 0.2f * std::sin(time_ * 17.0f + i * 1.7f);
        DrawCircleGradient({cx, base - cell * 0.4f}, cell * (1.8f + 0.4f * f), Fade({255, 150, 50, 255}, 0.18f + 0.1f * f),
                           Fade({255, 90, 20, 255}, 0));
        for (int k = 0; k < 4; k++) {  // tongues
            float ph = time_ * (5.0f + k) + i * 2.3f + k * 1.9f;
            float h = cell * (0.55f + 0.25f * std::sin(ph) + 0.15f * k / 3.0f);
            float sway = std::sin(ph * 0.7f) * cell * 0.12f;
            float half = cell * (0.22f - 0.04f * k);
            float x = cx + (k - 1.5f) * cell * 0.12f;
            Color c = k < 2 ? Color{255, 120, 30, 255} : Color{255, 220, 110, 255};
            DrawTriangle({x + sway, base - h}, {x - half, base}, {x + half, base}, Fade(c, 0.55f));
        }
        DrawCircle(int(cx), int(base - cell * 0.12f), cell * 0.18f, Fade({255, 245, 200, 255}, 0.6f));
    }
    EndBlendMode();
}

// A slow plume from the volcano crater on the painted background: puffs rise, swell,
// lean with the wind and thin out. Behind the mist layer, so it sits in the distance.
void Renderer::draw_volcano_smoke(int room) {
    if (!ambient || !plume_.id) return;
    auto it = volcano_.find(room);
    if (it == volcano_.end()) return;
    const Vector2 c = it->second;
    const float w = 560, h = 340, pixel = 5;  // quad; the crater sits at 18% across, at the bottom
    float size[2] = {w, h}, t = time_, seed = float(room);
    SetShaderValue(plume_, GetShaderLocation(plume_, "time"), &t, SHADER_UNIFORM_FLOAT);
    SetShaderValue(plume_, GetShaderLocation(plume_, "size"), size, SHADER_UNIFORM_VEC2);
    SetShaderValue(plume_, GetShaderLocation(plume_, "pixel"), &pixel, SHADER_UNIFORM_FLOAT);
    SetShaderValue(plume_, GetShaderLocation(plume_, "seed"), &seed, SHADER_UNIFORM_FLOAT);
    BeginShaderMode(plume_);
    DrawTexturePro(air_tex_, {0, 0, float(air_tex_.width), float(air_tex_.height)}, {c.x - w * 0.18f, c.y - h + 4, w, h},
                   {0, 0}, 0, WHITE);  // full source rect: fragTexCoord spans 0..1
    EndShaderMode();
}

void Renderer::draw_opened(const uint8_t* ram) {
    int room = GameData::room(ram);
    auto tex = open_rooms_.find(room);
    auto cells = open_cells_.find(room);
    if (tex == open_rooms_.end() || cells == open_cells_.end()) return;
    const uint8_t* m = GameData::tilemap(ram);
    const Texture2D& t = tex->second;
    const float cell = 8.0f * SCALE, sx = float(t.width) / CANVAS_W, sy = float(t.height) / FIELD_PX_H;
    for (auto [c, r] : cells->second) {
        uint8_t now = m[r * MAP_W + c];
        if (now == GATE_TIP || now == GATE_STAKE) continue;  // still there: keep the painted spikes
        DrawTexturePro(t, {c * cell * sx, r * cell * sy, cell * sx, cell * sy}, {c * cell, r * cell, cell, cell}, {0, 0},
                       0, WHITE);
    }
}
