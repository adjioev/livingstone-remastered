#include "machine.h"

#include <cstring>
#include <deque>
#include <stdexcept>
#include <string>

#include <unicorn/unicorn.h>

namespace {

constexpr uint32_t MEM_SIZE = 0x110000;
constexpr uint16_t PSP = 0x1000;
constexpr uint16_t GAME_SEG = PSP + 0x20;   // the joystick wrapper hands over to PSP+0x20:0000
constexpr uint32_t VRAM = 0xB8000;
constexpr uint16_t BIOS_SEG = 0xF000;
constexpr uint16_t IRET_STUB = 0xFF00;      // every unclaimed vector points at an IRET
constexpr uint32_t RESET = 0xFFFF0;         // Ctrl+Alt+Del in the game jumps here
constexpr uint64_t INSNS_PER_TICK = 20000;  // generous: the game busy-waits on the timer
constexpr uint64_t INSNS_PER_KEY = 2000;    // enough for the INT 9 handler to finish
constexpr uint16_t FRAME_WAIT = 0x274, FRAME_WAIT_END = 0x27b;  // main loop: wait for the next frame

void check(uc_err err, const char* what) {
    if (err != UC_ERR_OK) throw std::runtime_error(std::string(what) + ": " + uc_strerror(err));
}

class UnicornMachine final : public Machine {
public:
    UnicornMachine(const std::vector<uint8_t>& com, bool wrapper) : mem_(MEM_SIZE, 0) {
        check(uc_open(UC_ARCH_X86, UC_MODE_16, &uc_), "uc_open");
        check(uc_mem_map_ptr(uc_, 0, MEM_SIZE, UC_PROT_ALL, mem_.data()), "uc_mem_map_ptr");

        if (wrapper) {
            std::memcpy(&mem_[PSP * 16 + 0x100], com.data(), com.size());
        } else {  // plain COM run directly in the game segment (which is its own PSP)
            std::memcpy(&mem_[GAME_SEG * 16 + 0x100], com.data() + 0x200, com.size() - 0x200);
            mem_[GAME_SEG * 16] = 0xCD, mem_[GAME_SEG * 16 + 1] = 0x20;  // PSP: INT 20h
        }
        mem_[BIOS_SEG * 16 + IRET_STUB] = 0xCF;
        mem_[RESET] = 0xF4;  // HLT
        for (int v = 0; v < 256; v++) set_vector(v, BIOS_SEG, IRET_STUB);

        for (int r : {UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS}) write(r, wrapper ? PSP : GAME_SEG);
        write(UC_X86_REG_IP, 0x100);
        write(UC_X86_REG_SP, 0xFFFE);

        uc_hook h;
        check(uc_hook_add(uc_, &h, UC_HOOK_INSN, (void*)on_in, this, 1, 0, UC_X86_INS_IN), "hook in");
        check(uc_hook_add(uc_, &h, UC_HOOK_INSN, (void*)on_out, this, 1, 0, UC_X86_INS_OUT), "hook out");
        // Software INTs (only INT 10h: set mode / palette) are ignored; the renderer
        // reads the palette choice from the game's own variable.
        check(uc_hook_add(uc_, &h, UC_HOOK_INTR, (void*)on_intr, this, 1, 0), "hook intr");
    }

    ~UnicornMachine() override { uc_close(uc_); }

    void tick() override {
        if (halted_) return;
        run(INSNS_PER_TICK);
        game_ip_ = read(UC_X86_REG_CS) == GAME_SEG ? int(read(UC_X86_REG_IP)) : -1;
        if (pending_call_ && game_ip_ >= FRAME_WAIT && game_ip_ < FRAME_WAIT_END) {
            for (const Poke& p : pending_call_->pokes) poke(p.addr, p.data.data(), p.data.size());
            uint16_t sp = uint16_t(read(UC_X86_REG_SP) - 2);
            uint16_t ret = uint16_t(game_ip_);
            std::memcpy(&mem_[read(UC_X86_REG_SS) * 16 + sp], &ret, 2);  // near call: push IP
            write(UC_X86_REG_SP, sp);
            write(UC_X86_REG_SI, pending_call_->si);
            write(UC_X86_REG_IP, pending_call_->target);
            pending_call_.reset();
        }
        // Deliver IRQs between slices, where IF is normally set. The keyboard goes first
        // because the timer handler leaves IF clear until its IRET.
        while (!keys_.empty() && !halted_) {
            port60_ = keys_.front();
            if (!irq(9)) break;
            keys_.pop_front();
            run(INSNS_PER_KEY);
        }
        irq(0x1C);
    }

    void key(uint8_t scancode, bool down) override {
        keys_.push_back(down ? scancode : uint8_t(scancode | 0x80));
    }

    const uint8_t* ram() const override { return &mem_[GAME_SEG * 16]; }
    const uint8_t* vram() const override { return &mem_[VRAM]; }
    bool halted() const override { return halted_; }
    int game_ip() const override { return game_ip_; }

    Speaker speaker() const override {
        bool on = (port61_ & 3) == 3 && divisor_ > 0;
        return {on, on ? PIT_HZ / divisor_ : 0.0};
    }

    void call_at_frame_wait(uint16_t target, uint16_t si, std::vector<Poke> pokes) override {
        pending_call_ = PendingCall{target, si, std::move(pokes)};
    }

    void poke(uint16_t addr, const uint8_t* data, size_t n) override {
        uint64_t at = uint64_t(GAME_SEG) * 16 + addr;
        check(uc_mem_write(uc_, at, data, n), "uc_mem_write");
        check(uc_ctl_remove_cache(uc_, at, at + n), "uc_ctl_remove_cache");
    }

private:
    uint64_t read(int reg) const {
        uint64_t v = 0;
        uc_reg_read(uc_, reg, &v);
        return v;
    }
    void write(int reg, uint64_t v) { uc_reg_write(uc_, reg, &v); }

    void set_vector(int v, uint16_t seg, uint16_t off) {
        mem_[v * 4 + 0] = off & 0xFF;
        mem_[v * 4 + 1] = off >> 8;
        mem_[v * 4 + 2] = seg & 0xFF;
        mem_[v * 4 + 3] = seg >> 8;
    }

    void run(uint64_t count) {
        uint64_t linear = read(UC_X86_REG_CS) * 16 + read(UC_X86_REG_IP);
        check(uc_emu_start(uc_, linear, 0, 0, count), "uc_emu_start");
        if (read(UC_X86_REG_CS) == BIOS_SEG && read(UC_X86_REG_IP) >= 0xFFF0) halted_ = true;
    }

    // Hardware interrupt: push FLAGS/CS/IP and enter the handler from the IVT.
    bool irq(int vec) {
        uint64_t flags = read(UC_X86_REG_EFLAGS);
        if (!(flags & 0x200)) return false;
        uint16_t sp = uint16_t(read(UC_X86_REG_SP) - 6);
        uint32_t ss = uint32_t(read(UC_X86_REG_SS));
        uint16_t frame[3] = {uint16_t(read(UC_X86_REG_IP)), uint16_t(read(UC_X86_REG_CS)), uint16_t(flags)};
        std::memcpy(&mem_[ss * 16 + sp], frame, sizeof frame);
        write(UC_X86_REG_SP, sp);
        write(UC_X86_REG_EFLAGS, flags & ~uint64_t(0x300));  // clear IF and TF
        write(UC_X86_REG_IP, mem_[vec * 4] | mem_[vec * 4 + 1] << 8);
        write(UC_X86_REG_CS, mem_[vec * 4 + 2] | mem_[vec * 4 + 3] << 8);
        return true;
    }

    static uint32_t on_in(uc_engine*, uint32_t port, int, void* self) {
        auto* m = static_cast<UnicornMachine*>(self);
        if (port == 0x60) return m->port60_;
        if (port == 0x61) return m->port61_;
        if (port == 0x202) return 0xFF;  // no joystick: the wrapper skips its IRQ6 hook
        return 0;
    }
    static void on_out(uc_engine*, uint32_t port, int, uint32_t value, void* self) {
        auto* m = static_cast<UnicornMachine*>(self);
        uint8_t v = uint8_t(value);
        switch (port) {
        case 0x43:  // PIT mode: the game only uses B6h (ch 2, lo/hi, square wave)
            if ((v >> 6) == 2) m->latch_hi_ = false;
            break;
        case 0x42:
            if (m->latch_hi_) m->divisor_ = (m->divisor_ & 0x00FF) | v << 8;
            else m->divisor_ = (m->divisor_ & 0xFF00) | v;
            m->latch_hi_ = !m->latch_hi_;
            break;
        case 0x61:
            m->port61_ = v;
            break;
        }
    }
    static void on_intr(uc_engine*, uint32_t, void*) {}

    uc_engine* uc_ = nullptr;
    std::vector<uint8_t> mem_;
    std::deque<uint8_t> keys_;
    uint8_t port60_ = 0;
    uint8_t port61_ = 0;
    uint16_t divisor_ = 0;
    bool latch_hi_ = false;
    static constexpr double PIT_HZ = 1193182.0;
    bool halted_ = false;
    int game_ip_ = -1;
    struct PendingCall {
        uint16_t target, si;
        std::vector<Poke> pokes;
    };
    std::optional<PendingCall> pending_call_;
};

}  // namespace

std::unique_ptr<Machine> make_unicorn_machine(const std::vector<uint8_t>& com, bool wrapper) {
    return std::make_unique<UnicornMachine>(com, wrapper);
}
