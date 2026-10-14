#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

// The PC the original game runs on. Kept behind an interface so the CPU core can be
// swapped (e.g. a portable 8086 core for a WebAssembly build).
class Machine {
public:
    virtual ~Machine() = default;

    // Advance one period of the game's 100 Hz timer (INT 1Ch).
    virtual void tick() = 0;
    // Queue a key press/release; delivered through the game's INT 9 handler.
    virtual void key(uint8_t scancode, bool down) = 0;

    // Game segment (64 KB). Address = offset in LSTONE.COM + 0x100.
    virtual const uint8_t* ram() const = 0;
    // CGA video memory at B800:0000 (16 KB).
    virtual const uint8_t* vram() const = 0;
    virtual bool halted() const = 0;
    // PC speaker: PIT channel 2 square wave, gated by port 61h bits 0-1.
    struct Speaker {
        bool on;
        double hz;
    };
    virtual Speaker speaker() const = 0;
    // Write into the game segment (e.g. a code patch); drops any cached translation.
    virtual void poke(uint16_t addr, const uint8_t* data, size_t n) = 0;
    // Next time the game is idle in its main-loop frame wait (checked inside tick(),
    // before interrupts are delivered): apply the pokes, then call a game routine as if
    // from there; it returns into the wait.
    struct Poke {
        uint16_t addr;
        std::vector<uint8_t> data;
    };
    virtual void call_at_frame_wait(uint16_t target, uint16_t si, std::vector<Poke> pokes) = 0;
    // IP inside the game segment at the end of the last tick's main slice, or -1.
    virtual int game_ip() const = 0;
};

// com: normalised image (game address A at offset A + 0x100, as in the Kiev file). wrapper: start through the
// Kiev port's joystick wrapper; otherwise start the game directly like DOS starts a COM.
std::unique_ptr<Machine> make_unicorn_machine(const std::vector<uint8_t>& com, bool wrapper);
