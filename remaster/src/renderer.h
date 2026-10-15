#pragma once

#include <memory>
#include <string>
#include <unordered_map>

#include <raylib.h>

#include "gamedata.h"
#include "hud.h"

// Widescreen presentation of the running game: a 1920x1080 canvas with the 2:1
// playfield at 6x on top and the original HUD below. HD art in assets/ overrides
// the original room tiles (assets/rooms/room_XX.png) and sprites
// (assets/sprites/XXXX.png, named by sprite record address).
class Renderer {
public:
    static constexpr int CANVAS_W = 1920, CANVAS_H = 1080;
    static constexpr int SCALE = CANVAS_W / FIELD_W;  // 6
    static constexpr int FIELD_PX_H = FIELD_H * SCALE;  // 960

    Renderer(const GameData& data, const std::string& assets_dir);
    ~Renderer();

    // objects: what to draw this frame (already smoothed), see Smoother.
    void frame(const uint8_t* ram, const uint8_t* vram, const std::vector<ObjectView>& objects, float dt);
    void present() const;  // canvas -> window, letterboxed

    bool transitioning() const { return transition_ < 1.0f; }
    void save_canvas(const char* path) const;
    void toast(std::string message);  // short message at the top of the screen
    bool infinite_lives = false;      // shown in the HUD
    bool paused = false;              // dim the screen and show the pause panel
    std::string layout_name;          // shown on the pause panel
    bool gamepad = false;             // show gamepad hints on the pause panel
    int picker_room = -1;             // >= 0: teleport room picker open on the pause panel

    bool debug = false;
    bool classic = false;  // show the untouched CGA screen instead
    bool bright = true;    // CGA intensity bit (not confirmed on real hardware)
    bool smooth_anim = true;   // play the HD walk cycle instead of the 3 original frames
    bool classic_hud = false;  // original CGA status bar instead of the remastered one

private:
    void rebuild_palette_textures();
    void draw_field(const uint8_t* ram, const std::vector<ObjectView>& objects, RenderTexture2D& target);
    void draw_background(int room, int palette);
    void draw_hud();
    void update_vram_texture(const uint8_t* vram, int palette);
    void start_transition();
    void draw_hd(const uint8_t* ram, float dt);  // remastered field + HUD into the current target
    void draw_flip();                            // R: the picture dissolves into big pixels and back
    void draw_blocky(const Texture2D& tex, Rectangle src, Rectangle dst, float block, float alpha);
    void load_walk_cycle();
    const Texture2D* hero_override(const ObjectView& o);
    const Texture2D* sprite_texture(uint16_t addr) const;  // HD if present, else original

    const GameData& data_;
    std::string assets_;
    RenderTexture2D canvas_{}, field_{}, prev_field_{}, hd_canvas_{}, blocks_{};
    Texture2D tiles_[2]{};
    std::unordered_map<uint16_t, Texture2D> sprites_[2];
    std::unordered_map<int, Texture2D> hd_rooms_;
    std::unordered_map<uint16_t, Texture2D> hd_sprites_;
    Texture2D vram_tex_{};
    std::unique_ptr<Hud> hud_;
    std::vector<Texture2D> walk_[2];  // [0] right, [1] left (mirrored)
    Texture2D log_tex_{};
    Texture2D gate_tip_tex_{}, gate_tex_{};
    void draw_gates(const uint8_t* ram);
    // Rooms whose background shows something a lever removes (2d, 2f: spikes): an "open"
    // background is drawn over those cells once the live map no longer has them.
    std::unordered_map<int, Texture2D> open_rooms_;
    std::unordered_map<int, std::vector<std::pair<int, int>>> open_cells_;
    void draw_opened(const uint8_t* ram);
    // Ambient mist and clouds (jungle rooms): shader over the background, masked to air cells.
    Shader ambient_{};
    Texture2D air_tex_{};
    bool ambient_ok_ = false;
    void load_ambient();
    void draw_ambient(const uint8_t* ram);
    Shader water_{};
    Texture2D water_mask_{};
    bool water_ok_ = false;
    void draw_water(const uint8_t* ram, const Texture2D& bg);
    void draw_swamp_bubbles(const uint8_t* ram);
    void draw_lights(const uint8_t* ram);
    void draw_mushrooms(const uint8_t* ram, const Texture2D& bg);
    void draw_crystals(int room, const Texture2D& bg);
    void draw_braziers(const uint8_t* ram);
    Shader glow_{}, opaque_{}, plume_{};
    std::unordered_map<int, Texture2D> glow_masks_, fire_masks_;
    std::unordered_map<int, std::vector<Vector2>> fire_points_;  // painted flame tops, canvas px
    void draw_smoke(const uint8_t* ram);
    std::unordered_map<int, Vector2> volcano_;  // crater on the painted background, canvas px
    void draw_volcano_smoke(int room);
    void draw_treasure_glow(const ObjectView& o);
public:
    bool ambient = true;
private:
    // HD animation cycles played instead of a sprite's original frames.
    struct Anim {
        std::vector<Texture2D> frames;
        float fps;
    };
    std::unordered_map<uint16_t, const Anim*> anim_by_sprite_;
    std::vector<std::unique_ptr<Anim>> anims_;
    void load_anims();
    double last_walk_seen_ = -1;
    int walk_dir_ = 0;
    float walk_phase_ = 0;
    bool built_bright_ = true;

    int room_ = -1;
    int last_player_x_ = 160, last_player_y_ = 80;
    float transition_ = 1.0f;  // 0..1, 1 = idle
    // R flip: 0..1, 1 = idle.
    float flip_ = 1.0f;
    bool shown_classic_ = false, flip_to_classic_ = false;
    int dir_x_ = 0, dir_y_ = 0;
    float time_ = 0.0f;
    std::string toast_;
    float toast_until_ = 0.0f;
};
