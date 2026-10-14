#pragma once

#include <atomic>

#include <raylib.h>

// PC speaker output at the frequency the game programs into the PIT, synthesised on
// raylib's audio thread: either the bare square wave (original) or the same notes
// through a small synth (detuned squares, sub octave, envelope, drive, echo). While the
// game plays its tune, the synth adds an accompaniment from the melody notes: bass two
// octaves down, a soft fifth below, kick and snare alternating on note starts.
class SpeakerAudio {
public:
    SpeakerAudio();
    ~SpeakerAudio();

    void set(bool on, double hz, bool music = false);  // from the game loop; music: tune, not effects
    void toggle_mute() { muted_ = !muted_; }
    bool muted() const { return muted_; }
    bool enhanced = true;

private:
    static void callback(void* buffer, unsigned int frames);

    AudioStream stream_{};
    std::atomic<bool> muted_{false};
};
