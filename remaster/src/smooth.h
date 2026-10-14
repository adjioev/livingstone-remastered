#pragma once

#include <unordered_map>
#include <vector>

#include "gamedata.h"

// Presentation-only smoothing. The game moves objects in steps of 4-8 px (x) / 2 px (y)
// every one or two of its ~33 Hz frames. Each object slot glides from where it is
// drawn now to its new position over the time its previous step took, so steady
// movement becomes continuous. Animation-frame changes don't disturb the glide.
class Smoother {
public:
    // Call after every machine tick. t = game clock in seconds.
    void sample(const GameData& data, const uint8_t* ram, int game_ip, double t);
    // Objects to draw at time t (game clock plus the unspent fraction of a tick).
    std::vector<ObjectView> at(double t) const;

    bool enabled = true;

private:
    struct Track {
        float from_x, from_y;
        int to_x, to_y;
        double start, period;
    };
    static void position(const Track& tr, double t, float& x, float& y);

    std::vector<ObjectView> objs_;
    std::unordered_map<int, Track> tracks_;  // by slot
    int room_ = -1;
    double last_sample_ = 0;
};
