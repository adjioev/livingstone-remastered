#include "hud.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace {

constexpr Color C_WOOD{54, 36, 22, 255}, C_WOOD_EDGE{150, 104, 48, 255}, C_WOOD_DARK{26, 17, 10, 255};
constexpr Color C_GOLD{255, 214, 96, 255}, C_GOLD_DIM{150, 118, 60, 255}, C_INK{255, 238, 200, 255};
constexpr float BAR_EASE = 10.0f;  // per second
constexpr int LOW = METER_MAX / 5;  // food/water warning level

}  // namespace

Hud::Hud(const std::string& font_path) {
    if (FileExists(font_path.c_str())) {
        font_ = LoadFontEx(font_path.c_str(), 96, nullptr, 0);
        SetTextureFilter(font_.texture, TEXTURE_FILTER_BILINEAR);
        own_font_ = true;
    } else {
        font_ = GetFontDefault();
    }
}

Hud::~Hud() {
    if (own_font_) UnloadFont(font_);
}

void Hud::text(const char* t, Vector2 centre, float size, Color c) const {
    Vector2 m = MeasureTextEx(font_, t, size, 1);
    Vector2 p{std::round(centre.x - m.x / 2), std::round(centre.y - m.y / 2)};
    DrawTextEx(font_, t, {p.x + 2, p.y + 2}, size, 1, Fade(BLACK, 0.6f));
    DrawTextEx(font_, t, p, size, 1, c);
}

void Hud::panel(Rectangle r) const {
    DrawRectangleRounded({r.x - 3, r.y - 3, r.width + 6, r.height + 6}, 0.18f, 6, C_WOOD_DARK);
    DrawRectangleRounded(r, 0.16f, 6, C_WOOD_EDGE);
    DrawRectangleRounded({r.x + 4, r.y + 4, r.width - 8, r.height - 8}, 0.14f, 6, C_WOOD);
}

void Hud::meter(Rectangle r, const char* label, float value, Color fill, bool warn, bool scale) const {
    text(label, {r.x + r.width / 2, r.y + 14}, 26, warn ? (std::fmod(time_, 0.6f) < 0.3f ? RED : C_INK) : C_INK);
    Rectangle bar{r.x + 8, r.y + 32, r.width - 16, 22};
    DrawRectangleRec({bar.x - 2, bar.y - 2, bar.width + 4, bar.height + 4}, C_WOOD_DARK);
    DrawRectangleRec(bar, {20, 14, 10, 255});
    float k = std::clamp(value / METER_MAX, 0.0f, 1.0f);
    Rectangle f{bar.x, bar.y, bar.width * k, bar.height};
    DrawRectangleRec(f, fill);
    DrawRectangleRec({f.x, f.y, f.width, 5}, Fade(WHITE, 0.35f));             // shine
    DrawRectangleRec({f.x, f.y + f.height - 5, f.width, 5}, Fade(BLACK, 0.25f));  // shade
    if (scale) {
        // the original's 0..9 ruler under the power bar
        for (int i = 0; i <= 9; i++) {
            float x = bar.x + bar.width * (i + 0.5f) / 10;
            char d[2] = {char('0' + i), 0};
            text(d, {x, bar.y + bar.height + 14}, 18, C_GOLD_DIM);
        }
    }
}

void Hud::draw(const HudState& s, const Icons& icons, Rectangle area, float dt) {
    time_ += dt;
    if (s.strength > 0) {
        if (!charging_) shown_[0] = 0;  // a new charge: start the bar from empty
        charging_ = true;
        held_strength_ = s.strength;
    } else {
        charging_ = false;
    }
    const float target[3] = {float(held_strength_), float(s.food), float(s.water)};
    for (int i = 0; i < 3; i++) shown_[i] += (target[i] - shown_[i]) * std::min(1.0f, dt * BAR_EASE);

    DrawRectangleGradientV(int(area.x), int(area.y), int(area.width), int(area.height), {34, 24, 14, 255},
                           {12, 8, 5, 255});
    DrawRectangle(int(area.x), int(area.y), int(area.width), 3, C_WOOD_EDGE);

    const float y = area.y + 10, h = area.height - 18;

    // meters
    Rectangle left{area.x + 20, y, 760, h};
    panel(left);
    const float mw = (left.width - 24) / 3;
    meter({left.x + 12, left.y + 4, mw, h}, "STRENGTH", shown_[0], {232, 84, 52, 255}, false, true);
    meter({left.x + 12 + mw, left.y + 4, mw, h}, "FOOD", shown_[1], {236, 178, 44, 255}, s.food < LOW, false);
    meter({left.x + 12 + 2 * mw, left.y + 4, mw, h}, "WATER", shown_[2], {64, 150, 236, 255}, s.water < LOW,
          false);

    // lives + score
    Rectangle mid{left.x + left.width + 30, y, 360, h};
    panel(mid);
    if (icons.life) {
        const Texture2D& t = *icons.life;
        Rectangle src{0, 0, float(t.width), t.height * 0.42f};
        float ih = 30, iw = ih * src.width / src.height;
        float total = std::min(s.lives, 9) * (iw * 0.7f);
        for (int i = 0; i < std::min(s.lives, 9); i++)
            DrawTexturePro(t, src, {mid.x + (mid.width - total) / 2 + i * iw * 0.7f - iw * 0.15f, mid.y + 6, iw, ih},
                           {0, 0}, 0, WHITE);
    }
    if (s.infinite_lives) {
        Rectangle b{mid.x + mid.width - 58, mid.y + 44, 46, 22};
        DrawRectangleRounded(b, 0.4f, 6, C_GOLD);
        text("INF", {b.x + b.width / 2, b.y + b.height / 2}, 18, C_WOOD_DARK);
    }
    char score[16];
    std::snprintf(score, sizeof score, "%06d", s.score);
    text(score, {mid.x + mid.width / 2, mid.y + 66}, 52, C_GOLD);

    // weapons
    Rectangle right{mid.x + mid.width + 30, y, area.x + area.width - 20 - (mid.x + mid.width + 30), h};
    panel(right);
    const float slot = (right.width - 24) / 4;
    for (int i = 0; i < 4; i++) {
        Rectangle r{right.x + 12 + i * slot + 6, right.y + 8, slot - 12, h - 16};
        bool sel = s.weapon == i + 1;
        if (sel) {
            float glow = 0.55f + 0.45f * std::sin(time_ * 6);
            DrawRectangleRounded({r.x - 4, r.y - 4, r.width + 8, r.height + 8}, 0.2f, 6, Fade(C_GOLD, glow));
        }
        DrawRectangleRounded(r, 0.2f, 6, sel ? Color{92, 64, 30, 255} : C_WOOD_DARK);
        if (const Texture2D* t = icons.weapons[i]) {
            float box = r.height - 18;
            float k = std::min(box / t->width, box / t->height);
            float w = t->width * k, hh = t->height * k;
            Vector2 c{r.x + r.width / 2, r.y + r.height / 2 - 4};
            float rot = i == 3 ? 40.0f : 0.0f;  // the pole icon is a straight pole, tilted
            if (i == 3) {  // the pole sprite is 1 px wide in the original: draw it long and thick
                hh = box * 1.3f;
                w = hh * 0.3f;  // texture is ~1/3 stroke, 2/3 transparent margin
            }
            DrawTexturePro(*t, {0, 0, float(t->width), float(t->height)}, {c.x, c.y, w, hh}, {w / 2, hh / 2}, rot,
                           sel ? WHITE : Fade(WHITE, 0.55f));
        }
        char key[2] = {char('1' + i), 0};
        text(key, {r.x + r.width - 12, r.y + r.height - 12}, 18, sel ? C_GOLD : C_GOLD_DIM);
    }
}
