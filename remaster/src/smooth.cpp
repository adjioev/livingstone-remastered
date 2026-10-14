#include "smooth.h"

#include <algorithm>
#include <cmath>

namespace {

constexpr double FALLBACK_SAMPLE = 0.1;            // screens that never reach the main-loop wait
// Glide over the whole gap between steps, up to MAX_PERIOD: slow steady movers (the
// hero riding a log steps every 0.18 s) then move evenly instead of hop-and-wait.
constexpr double MIN_PERIOD = 0.02, MAX_PERIOD = 0.3;
constexpr double DEFAULT_PERIOD = 0.05;            // first step after standing still
constexpr int MAX_STEP_X = 64, MAX_STEP_Y = 48;    // bigger jumps are teleports: don't slide

}  // namespace

void Smoother::position(const Track& tr, double t, float& x, float& y) {
    float a = float(std::clamp((t - tr.start) / tr.period, 0.0, 1.0));
    x = tr.from_x + (tr.to_x - tr.from_x) * a;
    y = tr.from_y + (tr.to_y - tr.from_y) * a;
}

void Smoother::sample(const GameData& data, const uint8_t* ram, int game_ip, double t) {
    // Only read objects once the game has finished its frame and is spinning on the
    // timer; mid-frame the table can be half updated.
    bool frame_done = game_ip >= addr::FRAME_WAIT && game_ip < addr::FRAME_WAIT_END;
    if (!frame_done && t - last_sample_ < FALLBACK_SAMPLE) return;
    last_sample_ = t;

    int room = GameData::room(ram);
    if (room != room_) tracks_.clear();
    room_ = room;
    objs_ = data.objects(ram);
    // Floating logs move by rewriting the tile map; track them like objects (game time,
    // whole frames), so a log and the hero riding it glide in step.
    for (const LogView& l : find_logs(GameData::tilemap(ram)))
        objs_.push_back({LOG_SLOT_BASE + l.row, LOG_SPRITE, l.left * 8, l.row * 8, 0, 0, LOG_CELLS * 8, 8});

    std::unordered_map<int, Track> next;
    for (const auto& o : objs_) {
        auto it = tracks_.find(o.slot);
        if (it == tracks_.end()) {
            next[o.slot] = {float(o.x), float(o.y), o.x, o.y, t, DEFAULT_PERIOD};
            continue;
        }
        Track tr = it->second;
        if (o.x != tr.to_x || o.y != tr.to_y) {
            float cx, cy;
            position(tr, t, cx, cy);
            bool teleport = std::abs(o.x - tr.to_x) > MAX_STEP_X || std::abs(o.y - tr.to_y) > MAX_STEP_Y;
            double since = t - tr.start;
            tr.period = since > MAX_PERIOD ? DEFAULT_PERIOD : std::max(since, MIN_PERIOD);
            tr.from_x = teleport ? float(o.x) : cx;
            tr.from_y = teleport ? float(o.y) : cy;
            tr.to_x = o.x;
            tr.to_y = o.y;
            tr.start = t;
        }
        next[o.slot] = tr;
    }
    tracks_ = std::move(next);
}

std::vector<ObjectView> Smoother::at(double t) const {
    std::vector<ObjectView> out = objs_;
    for (auto& o : out) {
        o.fx = float(o.x);
        o.fy = float(o.y);
        auto it = tracks_.find(o.slot);
        if (enabled && it != tracks_.end()) position(it->second, t, o.fx, o.fy);
    }
    return out;
}
