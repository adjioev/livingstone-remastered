#include "audio.h"

#include <array>
#include <cmath>
#include <algorithm>
#include <cstdint>

namespace {

constexpr int RATE = 44100;
constexpr float PI2 = 6.2831853f;

// Original: bare square wave, edges softened a little.
constexpr float RAW_VOLUME = 0.12f;
constexpr float RAW_SMOOTH = 0.35f;

// Remastered: same notes, fuller sound.
constexpr float DETUNE = 1.006f;            // second square, slightly sharp: chorus
constexpr float SUB_MIX = 0.55f;            // sine an octave down: weight
constexpr float SUB_MIN_HZ = 160.0f;        // no sub under low notes (mud)
constexpr float ATTACK = 0.006f, DECAY = 0.12f, SUSTAIN = 0.7f, RELEASE = 0.05f;  // seconds / level
constexpr float DRIVE = 1.2f, OUT_GAIN = 0.22f;
constexpr float TONE = 0.25f;               // one-pole low-pass (~2 kHz): softer, less buzzy
constexpr int ECHO_SAMPLES = RATE * 90 / 1000;
constexpr float ECHO_FEEDBACK = 0.28f, ECHO_MIX = 0.22f;

// Accompaniment for the tune.
constexpr float BASS_MIX = 0.55f, PAD_MIX = 0.18f, KICK_MIX = 0.9f, SNARE_MIX = 0.35f;
constexpr float KICK_TIME = 0.14f, SNARE_TIME = 0.09f;      // seconds
constexpr float BASS_TONE = 0.08f;                          // low-pass: round bass

// Shared with the audio thread (one speaker, one stream).
std::atomic<bool> g_on{false}, g_muted{false}, g_enhanced{true}, g_music{false};
std::atomic<float> g_hz{0.0f};

struct SynthState {
    float p1 = 0, p2 = 0, psub = 0;  // oscillator phases
    float env = 0, hz = 0;
    int stage = 0;                   // 0 off, 1 attack, 2 decay/sustain, 3 release
    float raw_phase = 0, raw_level = 0;
    std::array<float, ECHO_SAMPLES> echo{};
    int echo_pos = 0;
    float tone = 0;
    // accompaniment
    float bass_phase = 0, pad_phase = 0, bass = 0, bass_hz = 0, bass_env = 0;
    float kick_t = 1, kick_phase = 0, snare_t = 1;
    unsigned note_count = 0, noise = 12345;
} g;

float noise_sample() {
    g.noise = g.noise * 1664525u + 1013904223u;
    return float(int32_t(g.noise >> 8) & 0xFFFF) / 32768.0f - 1.0f;
}

// Called when a new melody note starts while the tune plays.
void accompany_note(float hz) {
    g.bass_hz = hz * 0.25f;
    while (g.bass_hz > 160.0f) g.bass_hz *= 0.5f;  // keep the bass low
    g.bass_env = 1.0f;
    if (g.note_count++ % 2 == 0) g.kick_t = 0, g.kick_phase = 0;
    else g.snare_t = 0;
}

float accompaniment(bool on, float hz) {
    float v = 0.0f;
    const float dt = 1.0f / RATE;
    if (g.bass_hz > 0.0f) {  // bass: square + sine, rounded off
        g.bass_phase += g.bass_hz * dt;
        if (g.bass_phase >= 1.0f) g.bass_phase -= 1.0f;
        float raw = 0.6f * std::sin(PI2 * g.bass_phase) + 0.4f * (g.bass_phase < 0.5f ? 1.0f : -1.0f);
        g.bass += (raw - g.bass) * BASS_TONE;
        g.bass_env = on ? std::max(0.75f, g.bass_env - dt * 2.0f) : std::max(0.0f, g.bass_env - dt * 6.0f);
        v += BASS_MIX * g.bass * g.bass_env;
    }
    if (on && hz > 0.0f) {  // pad: soft triangle a fifth below the melody
        g.pad_phase += hz * (2.0f / 3.0f) * dt;
        if (g.pad_phase >= 1.0f) g.pad_phase -= 1.0f;
        v += PAD_MIX * (4.0f * std::fabs(g.pad_phase - 0.5f) - 1.0f);
    }
    if (g.kick_t < KICK_TIME) {  // kick: falling sine 140 -> 45 Hz
        float k = g.kick_t / KICK_TIME;
        g.kick_phase += (140.0f - 95.0f * k) * dt;
        v += KICK_MIX * std::sin(PI2 * g.kick_phase) * (1.0f - k) * (1.0f - k);
        g.kick_t += dt;
    }
    if (g.snare_t < SNARE_TIME) {  // snare: noise burst
        float k = g.snare_t / SNARE_TIME;
        v += SNARE_MIX * noise_sample() * (1.0f - k) * (1.0f - k);
        g.snare_t += dt;
    }
    return v;
}

// Band-limited step correction for a phase oscillator (polyBLEP).
float blep(float t, float dt) {
    if (t < dt) {
        t /= dt;
        return t + t - t * t - 1.0f;
    }
    if (t > 1.0f - dt) {
        t = (t - 1.0f) / dt;
        return t * t + t + t + 1.0f;
    }
    return 0.0f;
}

float square(float& phase, float hz) {
    float dt = hz / RATE;
    phase += dt;
    if (phase >= 1.0f) phase -= std::floor(phase);
    float v = phase < 0.5f ? 1.0f : -1.0f;
    v += blep(phase, dt);
    float half = phase + 0.5f;
    if (half >= 1.0f) half -= 1.0f;
    return v - blep(half, dt);
}

float enhanced_sample(bool on, float hz, bool music) {
    // envelope: a new note (or a pitch jump) restarts the attack
    if (on && (g.stage == 0 || g.stage == 3 || std::fabs(hz - g.hz) > 1.0f)) {
        g.stage = 1;
        if (music) accompany_note(hz);
    }
    if (!music) g.bass_hz = 0.0f;
    if (!on && g.stage != 0) g.stage = 3;
    if (on) g.hz = hz;
    switch (g.stage) {
    case 1:
        g.env += 1.0f / (ATTACK * RATE);
        if (g.env >= 1.0f) g.env = 1.0f, g.stage = 2;
        break;
    case 2:
        g.env += (SUSTAIN - g.env) / (DECAY * RATE) * 3.0f;
        break;
    case 3:
        g.env -= 1.0f / (RELEASE * RATE);
        if (g.env <= 0.0f) g.env = 0.0f, g.stage = 0;
        break;
    }

    float v = 0.0f;
    if (g.env > 0.0f && g.hz > 0.0f) {
        v = 0.5f * square(g.p1, g.hz) + 0.5f * square(g.p2, g.hz * DETUNE);
        if (g.hz >= SUB_MIN_HZ) {
            g.psub += g.hz * 0.5f / RATE;
            if (g.psub >= 1.0f) g.psub -= 1.0f;
            v += SUB_MIX * std::sin(PI2 * g.psub);
        }
        v = std::tanh(DRIVE * v * g.env);
    }
    if (music) v = 0.75f * v + accompaniment(on, g.hz);
    g.tone += (v - g.tone) * TONE;
    v = g.tone;
    float delayed = g.echo[g.echo_pos];
    g.echo[g.echo_pos] = v + delayed * ECHO_FEEDBACK;
    g.echo_pos = (g.echo_pos + 1) % ECHO_SAMPLES;
    return (v + delayed * ECHO_MIX) * OUT_GAIN;
}

float raw_sample(bool on, float hz) {
    float target = 0.0f;
    if (on) {
        g.raw_phase += hz / RATE;
        if (g.raw_phase >= 1.0f) g.raw_phase -= std::floor(g.raw_phase);
        target = g.raw_phase < 0.5f ? RAW_VOLUME : -RAW_VOLUME;
    }
    g.raw_level += (target - g.raw_level) * RAW_SMOOTH;
    return g.raw_level;
}

}  // namespace

SpeakerAudio::SpeakerAudio() {
    InitAudioDevice();
    SetAudioStreamBufferSizeDefault(512);  // ~12 ms: notes start on time
    stream_ = LoadAudioStream(RATE, 16, 1);
    SetAudioStreamCallback(stream_, callback);
    PlayAudioStream(stream_);
}

SpeakerAudio::~SpeakerAudio() {
    UnloadAudioStream(stream_);
    CloseAudioDevice();
}

void SpeakerAudio::set(bool on, double hz, bool music) {
    g_music = music;
    g_hz = float(hz);
    g_on = on && hz >= 20.0 && hz <= 20000.0;
    g_muted = muted_.load();
    g_enhanced = enhanced;
}

void SpeakerAudio::callback(void* buffer, unsigned int frames) {
    auto* out = static_cast<int16_t*>(buffer);
    const bool on = g_on && !g_muted;
    const float hz = g_hz;
    const bool enhanced = g_enhanced, music = g_music;
    for (unsigned int i = 0; i < frames; i++) {
        float s = enhanced ? enhanced_sample(on, hz, music) : raw_sample(on, hz);
        if (s > 1.0f) s = 1.0f;
        if (s < -1.0f) s = -1.0f;
        out[i] = int16_t(s * 32767.0f);
    }
}
