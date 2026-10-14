#pragma once

#include <array>
#include <string>

#include <raylib.h>

#include "gamedata.h"

// Remastered status bar, drawn from the game's HUD variables instead of its CGA pixels.
//   left:   STRENGTH (throw/vault power, with the original 0-9 scale), FOOD, WATER
//   centre: lives and score
//   right:  the four weapons, keys 1-4, the selected one highlighted
class Hud {
public:
    struct Icons {
        const Texture2D* life;                    // hero frame; its top part (hat + face) is used
        std::array<const Texture2D*, 4> weapons;  // boomerang, knife, grenade, pole
    };

    explicit Hud(const std::string& font_path);
    ~Hud();

    void draw(const HudState& s, const Icons& icons, Rectangle area, float dt);

private:
    void panel(Rectangle r) const;
    void meter(Rectangle r, const char* label, float value, Color fill, bool warn, bool scale) const;
    void text(const char* t, Vector2 centre, float size, Color c) const;

    Font font_{};
    bool own_font_ = false;
    float shown_[3] = {0, METER_MAX, METER_MAX};  // eased bar values
    // The game zeroes strength when a throw/vault is released; the bar keeps the last
    // charge until the next one starts.
    int held_strength_ = 0;
    bool charging_ = false;
    float time_ = 0;
};
