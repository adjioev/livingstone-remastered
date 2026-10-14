// Livingstone remaster: the original LSTONE.COM (Opera Soft) runs unmodified in an
// emulated 8086; the renderer redraws its state in widescreen with optional HD art.
//
//   livingstone [path/to/LSTONE.COM] [assets dir]
//
// Game keys: arrows plus QAOP or WASD (K cycles; in WASD Enter cycles weapons),
// Space (fire; hold to charge),
// 1-4 (weapon: boomerang, knife, grenade, pole), Enter, S, D, F1.
// V ambient effects (mist, water) on/off, Tab demo now from the title screen (gamepad Y), R original/remastered view, L infinite lives on/off, F full screen, M sound on/off,
// Gamepad: d-pad/stick move, A fire (hold to charge), B jump, X/RB next weapon, LB previous,
// Select original/remastered, Start pause (paused: X teleport, Y new game).
// Esc pause; while paused: X quit, N new game, T teleport (left/right pick a room,
// Enter go, Esc cancel).
// Prototype keys: F7 original HUD, F8 smoothing (motion + HD walk cycle), F9 debug overlay,
// F10 original CGA view, F11 CGA intensity, Esc quit.
//
//   livingstone --test <out_dir> [script]
//     Scripted run in emulated time; saves frames and player.csv, then quits.
//     Script tokens: "<sec>+<key>" press, "<sec>-<key>" release, "<sec>@shot", "<sec>@quit",
//     "<sec>@view" (original/remastered), "<sec>@lives" (infinite lives), "<sec>@pause"
//     (pause for 2 s of wall-clock time), "<sec>@cycle" (next weapon, as Enter in WASD),
//     "<sec>@roomXX" (teleport to hex room XX), "<sec>@newgame".
//     Keys: space left right up down enter 1 2 3 4.

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>

#include <raylib.h>

#include "gamedata.h"
#include "audio.h"
#include "gamefile.h"
#include "gamepad.h"
#include "machine.h"
#include "renderer.h"
#include "smooth.h"

namespace {

#ifndef WINDOW_TITLE
#define WINDOW_TITLE "Livingstone Remastered"
#endif
#ifndef APP_NAME
#define APP_NAME WINDOW_TITLE  // Application Support folder
#endif

constexpr float TICK = 0.01f;   // game timer is reprogrammed to ~100 Hz
constexpr int MAX_TICKS_PER_FRAME = 6;

// Game scancodes, from the key table at 0x7d07 (weapons are Q/W/E/R in the original).
constexpr uint8_t SC_WEAPON1 = 0x10, SC_WEAPON2 = 0x11, SC_WEAPON3 = 0x12, SC_WEAPON4 = 0x13;
constexpr uint8_t SC_LEFT = 0x4B, SC_RIGHT = 0x4D, SC_UP = 0x48, SC_DOWN = 0x50;
constexpr uint8_t SC_SPACE = 0x39, SC_ENTER = 0x1C;
constexpr uint8_t SC_DEMO = 0x20;  // D: the title screen's own "play the demo now" key

using KeyBinding = std::pair<int, uint8_t>;  // raylib key -> game scancode

// Always active. Several keys may share a scancode.
const std::vector<KeyBinding> COMMON_KEYS = {
    {KEY_ONE, SC_WEAPON1}, {KEY_TWO, SC_WEAPON2}, {KEY_THREE, SC_WEAPON3}, {KEY_FOUR, SC_WEAPON4},
    {KEY_LEFT, SC_LEFT}, {KEY_RIGHT, SC_RIGHT}, {KEY_UP, SC_UP}, {KEY_DOWN, SC_DOWN},
    {KEY_SPACE, SC_SPACE}, {KEY_F1, 0x3B}, {KEY_SCROLL_LOCK, 0x46},
};

// Extra direction keys, cycled with K. (QAOP and WASD both use A, so only one at a time.)
// Enter is the original's own pause key; in WASD (right hand free) it cycles weapons.
struct Layout {
    const char* name;
    std::vector<KeyBinding> keys;
    bool enter_cycles_weapon;
};
const Layout LAYOUTS[] = {
    {"ARROWS", {{KEY_S, 0x1F}, {KEY_D, 0x20}, {KEY_ENTER, SC_ENTER}}, false},  // the original's S / D
    {"QAOP", {{KEY_Q, SC_UP}, {KEY_A, SC_DOWN}, {KEY_O, SC_LEFT}, {KEY_P, SC_RIGHT}, {KEY_ENTER, SC_ENTER}}, false},
    {"WASD", {{KEY_W, SC_UP}, {KEY_A, SC_LEFT}, {KEY_S, SC_DOWN}, {KEY_D, SC_RIGHT}}, true},
};
constexpr double WEAPON_TAP = 0.1;  // s; the game polls weapon keys once per ~0.03 s frame
constexpr int LAYOUT_COUNT = sizeof(LAYOUTS) / sizeof(LAYOUTS[0]);

// Presses one game key once even if several keyboard keys map to it.
// The SC_* codes above are the Kiev port's key table (0x7d07). Other releases list other
// keys at the same table positions (Opera Soft: 1-4 and QAOP), so codes are translated
// position for position into the loaded game's own table.
constexpr uint8_t REFERENCE_KEYS[] = {0x10, 0x11, 0x12, 0x13, 0x4b, 0x4d, 0x48, 0x50, 0x39, 0x46, 0x1c,
                                      0x12, 0x13, 0x1f, 0x20, 0x38, 0x1d, 0x53, 0x3b};

class KeyRouter {
public:
    KeyRouter(Machine& m, const std::vector<uint8_t>& game_keys) : m_(&m) {
        for (int i = 0; i < 256; i++) tr_[i] = uint8_t(i);
        for (size_t i = sizeof REFERENCE_KEYS; i-- > 0;)  // first occurrence wins
            if (i < game_keys.size()) tr_[REFERENCE_KEYS[i]] = game_keys[i];
    }
    void set(uint8_t logical, bool down) {
        uint8_t sc = tr_[logical];
        int& n = held_[sc];
        if (down && n++ == 0) m_->key(sc, true);
        if (!down && n > 0 && --n == 0) m_->key(sc, false);
    }
    void rebind(Machine& m) {  // new game: fresh machine, nothing held
        m_ = &m;
        held_.clear();
    }

private:
    Machine* m_;
    std::map<uint8_t, int> held_;
    uint8_t tr_[256];
};

struct ScriptEvent {
    double t;
    char op;  // '+' press, '-' release, '@' action
    std::string arg;
};

const std::map<std::string, uint8_t> SCRIPT_KEYS = {
    {"space", SC_SPACE}, {"left", SC_LEFT}, {"right", SC_RIGHT}, {"up", SC_UP}, {"down", SC_DOWN},
    {"enter", SC_ENTER}, {"1", SC_WEAPON1}, {"2", SC_WEAPON2}, {"3", SC_WEAPON3}, {"4", SC_WEAPON4},
};

// Default smoke test: start the game, walk right, a frame every 3 s.
constexpr const char* DEFAULT_SCRIPT =
    "1+space 1.2-space 2+right 2@shot 5@shot 8@shot 11@shot 14@shot 17@shot 20@quit";

std::vector<ScriptEvent> parse_script(const std::string& text) {
    std::vector<ScriptEvent> out;
    std::istringstream in(text);
    std::string tok;
    while (in >> tok) {
        size_t i = tok.find_first_of("+-@");
        if (i == std::string::npos || i == 0) throw std::runtime_error("bad script token: " + tok);
        std::string arg = tok.substr(i + 1);
        if (tok[i] != '@' && !SCRIPT_KEYS.count(arg)) throw std::runtime_error("unknown key: " + arg);
        out.push_back({std::stod(tok.substr(0, i)), tok[i], arg});
    }
    return out;
}

// No copy found: a drop target until a supported LSTONE.COM is dropped (or the window closes).
std::optional<LoadedGame> ask_for_game(const std::string& data_dir, const std::string& test_dir) {
    std::string error;
    for (int frame = 0; !WindowShouldClose(); frame++) {
        if (!test_dir.empty() && frame == 10) {  // --test without a game: capture this screen, quit
            Image shot = LoadImageFromScreen();  // TakeScreenshot only writes into the working dir
            ExportImage(shot, (test_dir + "/drop_screen.png").c_str());
            UnloadImage(shot);
            return std::nullopt;
        }
        if (IsFileDropped()) {
            FilePathList files = LoadDroppedFiles();
            for (unsigned i = 0; i < files.count; i++) {
                if (auto data = adopt_dropped(files.paths[i], data_dir, error)) {
                    UnloadDroppedFiles(files);
                    return data;
                }
            }
            UnloadDroppedFiles(files);
        }
        BeginDrawing();
        ClearBackground({18, 24, 20, 255});
        int w = GetScreenWidth(), h = GetScreenHeight();
        auto centred = [&](const char* t, int y, int size, Color c) {
            DrawText(t, (w - MeasureText(t, size)) / 2, y, size, c);
        };
        DrawRectangleLinesEx({40.0f, 40.0f, float(w - 80), float(h - 80)}, 4, Fade(RAYWHITE, 0.5f));
        centred(WINDOW_TITLE, h / 2 - 170, 56, {255, 214, 96, 255});
        centred("Drop your copy of LSTONE.COM onto this window", h / 2 - 60, 32, RAYWHITE);
        centred("The original game is not included: you need your own copy.", h / 2 - 10, 24, Fade(RAYWHITE, 0.7f));
        centred(GAME_VERSION, h / 2 + 30, 24, Fade(RAYWHITE, 0.7f));
        if (!error.empty()) centred(error.c_str(), h / 2 + 110, 24, {255, 110, 90, 255});
        EndDrawing();
    }
    return std::nullopt;
}

}  // namespace

int main(int argc, char** argv) {
    std::string test_dir;
    std::vector<ScriptEvent> script;
    if (argc > 2 && std::string(argv[1]) == "--test") {
        test_dir = argv[2];
        try {
            script = parse_script(argc > 3 ? argv[3] : DEFAULT_SCRIPT);
        } catch (const std::exception& e) {
            std::fprintf(stderr, "%s\n", e.what());
            return 1;
        }
        argc = 1;
    }
    // Inside the .app the assets live in Contents/Resources; otherwise use the source tree.
    // The game itself is the user's own copy (not shipped): a path argument, an embedded
    // copy (family builds), Application Support, or next to the .app / binary.
    std::string res = std::string(GetApplicationDirectory()) + "../Resources/";
    bool bundled = DirectoryExists((res + "assets").c_str());
    std::string assets = argc > 2 ? argv[2] : bundled ? res + "assets" : PROJECT_ROOT "/assets";
    std::string data_dir = user_data_dir(APP_NAME);
    std::vector<std::string> candidates;
    if (argc > 1) candidates.push_back(argv[1]);
    if (const char* p = std::getenv("LIVINGSTONE_GAME")) candidates.push_back(p);  // e.g. tests
    for (const char* name : {GAME_FILE}) {
        candidates.push_back(res + name);
        candidates.push_back(data_dir + name);
        candidates.push_back(std::string(GetApplicationDirectory()) + "../../../" + name);  // beside the .app
        candidates.push_back(std::string(GetApplicationDirectory()) + name);
    }
#ifndef APP_BUNDLE
    candidates.push_back(PROJECT_ROOT "/../original/" + std::string(GAME_FILE));  // dev builds only
#endif
    if (std::getenv("LIVINGSTONE_NO_GAME")) candidates.clear();  // testing the drop screen
    auto found = load_game(candidates);

    SetConfigFlags(FLAG_WINDOW_RESIZABLE | FLAG_WINDOW_HIGHDPI | FLAG_VSYNC_HINT);
    InitWindow(1600, 900, WINDOW_TITLE);
    if (!found) found = ask_for_game(data_dir, test_dir);
    if (!found) {
        CloseWindow();
        return 0;
    }
    const GameVariant& variant = *found->variant;
    std::vector<uint8_t> com = std::move(found->com);
    TraceLog(LOG_INFO, "Game: %s", variant.name);
    SetExitKey(KEY_NULL);  // Esc pauses; quit from the pause screen (X) or the window

    {
        GameData data(com);
        auto start_machine = [&] {
            auto m = make_unicorn_machine(com, variant.wrapper);
            for (const auto& [at, bytes] : variant.restore) m->poke(at, bytes.data(), bytes.size());
            return m;
        };
        auto machine = start_machine();
        Renderer renderer(data, assets);
        Smoother smoother;
        SpeakerAudio audio;
        double game_t = 0;  // seconds of emulated game time
        KeyRouter keys(*machine, data.key_table());
        auto teleport = [&](int room) {
            if (GameData::room(machine->ram()) == 0x3d) {  // title / demo: nothing to teleport
                renderer.toast("START A GAME FIRST");
                return;
            }
            machine->call_at_frame_wait(addr::ENTER_ROOM, addr::OBJECTS, {{addr::ROOM, {uint8_t(room)}}});
            char msg[32];
            std::snprintf(msg, sizeof msg, "TELEPORT: ROOM %02X", room);
            renderer.toast(msg);
        };
        // Demo: tap the title's own D key.
        double demo_tap_at = -1, demo_release_at = -1;
        auto new_game = [&] {
            machine = start_machine();
            keys.rebind(*machine);
            smoother = Smoother();
            renderer.infinite_lives = false;
            renderer.toast("NEW GAME");
        };
        // Only from the title screen: in a game Tab is too easy to hit by mistake.
        auto demo_now = [&] {
            if (GameData::room(machine->ram()) != 0x3d) return;
            demo_tap_at = game_t;
            renderer.toast("DEMO");
        };
        float acc = 0;
        size_t next_event = 0;
        int shots = 0;
        std::unique_ptr<FILE, int (*)(FILE*)> trace(
            test_dir.empty() ? nullptr : std::fopen((test_dir + "/player.csv").c_str(), "w"), std::fclose);

        auto toggle_view = [&] {
            renderer.classic = !renderer.classic;
            renderer.toast(renderer.classic ? "ORIGINAL 1986" : "REMASTERED");
        };
        auto toggle_lives = [&] {
            static constexpr uint8_t NOPS[2] = {0x90, 0x90}, DEC_AH[2] = {0xfe, 0xcc};
            renderer.infinite_lives = !renderer.infinite_lives;
            machine->poke(addr::LOSE_LIFE, renderer.infinite_lives ? NOPS : DEC_AH, 2);
            renderer.toast(renderer.infinite_lives ? "INFINITE LIVES: ON" : "INFINITE LIVES: OFF");
        };

        bool paused = false;
        int layout = 1;  // QAOP, as before
        uint8_t weapon_tap = 0;  // weapon key held briefly for Enter-cycles-weapon
        double weapon_tap_until = 0;
        auto cycle_weapon = [&](int dir = 1) {
            if (weapon_tap) return;
            int cur = machine->ram()[addr::WEAPON] & 0x0f;
            if (cur < 1 || cur > 4) cur = dir > 0 ? 4 : 1;
            int next = (cur - 1 + dir + 4) % 4;  // 0..3, wrapping
            weapon_tap = uint8_t(SC_WEAPON1 + next);
            keys.set(weapon_tap, true);
            weapon_tap_until = game_t + WEAPON_TAP;
        };
        renderer.layout_name = LAYOUTS[layout].name;
        Pad pad;
        bool pad_was_connected = false;
        double test_pause_until = 0;
        bool paused_shot = false;

        while (!WindowShouldClose() && !machine->halted()) {
            pad.update();
            if (pad.connected() != pad_was_connected) {
                pad_was_connected = pad.connected();
                renderer.toast(pad.connected() ? "GAMEPAD CONNECTED" : "GAMEPAD DISCONNECTED");
            }
            renderer.gamepad = pad.connected();
            if (IsKeyPressed(KEY_ESCAPE) || pad.pressed(Pad::START) ||
                (renderer.picker_room >= 0 && pad.pressed(Pad::B))) {
                if (renderer.picker_room >= 0) renderer.picker_room = -1;  // cancel the room picker
                else paused = !paused;
            }
            if (!script.empty() && test_pause_until > 0) {  // scripted pause: wall-clock seconds
                paused = GetTime() < test_pause_until;
                if (!paused) test_pause_until = 0;
            }
            if (paused) {
                if (renderer.picker_room >= 0) {
                    int& r = renderer.picker_room;
                    if (IsKeyPressed(KEY_RIGHT) || IsKeyPressed(KEY_D) || IsKeyPressed(KEY_P) || pad.pressed(Pad::RIGHT))
                        r = (r + 1) % addr::ROOM_COUNT;
                    if (IsKeyPressed(KEY_LEFT) || IsKeyPressed(KEY_A) || IsKeyPressed(KEY_O) || pad.pressed(Pad::LEFT))
                        r = (r + addr::ROOM_COUNT - 1) % addr::ROOM_COUNT;
                    if (IsKeyPressed(KEY_ENTER) || pad.pressed(Pad::A)) {
                        teleport(r);
                        r = -1;
                        paused = false;
                    }
                } else {
                    if (IsKeyPressed(KEY_X)) break;
                    if (IsKeyPressed(KEY_N) || pad.pressed(Pad::Y)) new_game(), paused = false;
                    if (IsKeyPressed(KEY_T) || pad.pressed(Pad::X)) {
                        int cur = GameData::room(machine->ram());
                        renderer.picker_room = cur < addr::ROOM_COUNT ? cur : 0;
                    }
                }
                if (test_pause_until > 0 && GetTime() > test_pause_until - 1.0 && !paused_shot) {
                    renderer.save_canvas((test_dir + "/paused.png").c_str());
                    paused_shot = true;
                }
                audio.set(false, 0);
                renderer.paused = true;
                renderer.frame(machine->ram(), machine->vram(), smoother.at(game_t + acc), 0);
                renderer.present();
                continue;
            }
            renderer.paused = false;
            if (IsKeyPressed(KEY_K)) {
                for (auto [key, sc] : LAYOUTS[layout].keys)  // let go of anything held in the old layout
                    if (IsKeyDown(key)) keys.set(sc, false);
                layout = (layout + 1) % LAYOUT_COUNT;
                renderer.layout_name = LAYOUTS[layout].name;
                renderer.toast(std::string("CONTROLS: ARROWS") + (layout ? std::string(" + ") + LAYOUTS[layout].name : ""));
            }
            if (LAYOUTS[layout].enter_cycles_weapon && IsKeyPressed(KEY_ENTER)) cycle_weapon();
            if (weapon_tap && game_t >= weapon_tap_until) {
                keys.set(weapon_tap, false);
                weapon_tap = 0;
            }
            // Gamepad -> the same game keys.
            const std::pair<Pad::Btn, uint8_t> PAD_KEYS[] = {
                {Pad::LEFT, SC_LEFT}, {Pad::RIGHT, SC_RIGHT}, {Pad::UP, SC_UP}, {Pad::DOWN, SC_DOWN},
                {Pad::A, SC_SPACE}, {Pad::B, SC_UP},
            };
            for (auto [b, sc] : PAD_KEYS) {
                if (pad.pressed(b)) keys.set(sc, true);
                if (pad.released(b)) keys.set(sc, false);
            }
            if (pad.pressed(Pad::X) || pad.pressed(Pad::RB)) cycle_weapon(1);
            if (pad.pressed(Pad::LB)) cycle_weapon(-1);
            if (pad.pressed(Pad::SELECT)) toggle_view();
            for (const auto* set : {&COMMON_KEYS, &LAYOUTS[layout].keys})
                for (auto [key, sc] : *set) {
                    if (IsKeyPressed(key)) keys.set(sc, true);
                    if (IsKeyReleased(key)) keys.set(sc, false);
                }
            if (IsKeyPressed(KEY_F7)) renderer.classic_hud = !renderer.classic_hud;
            if (IsKeyPressed(KEY_F8)) renderer.smooth_anim = smoother.enabled = !smoother.enabled;
            if (IsKeyPressed(KEY_F9)) renderer.debug = !renderer.debug;
            if (IsKeyPressed(KEY_F10) || IsKeyPressed(KEY_R)) toggle_view();
            if (IsKeyPressed(KEY_L)) toggle_lives();
            if (IsKeyPressed(KEY_F)) ToggleBorderlessWindowed();
            if (IsKeyPressed(KEY_V)) {
                renderer.ambient = !renderer.ambient;
                renderer.toast(renderer.ambient ? "AMBIENT FX: ON" : "AMBIENT FX: OFF");
            }
            if (IsKeyPressed(KEY_TAB) || pad.pressed(Pad::Y)) demo_now();
            if (demo_tap_at >= 0 && game_t >= demo_tap_at) {
                keys.set(SC_DEMO, true);
                demo_tap_at = -1;
                demo_release_at = game_t + 0.15;
            }
            if (demo_release_at >= 0 && game_t >= demo_release_at) {
                keys.set(SC_DEMO, false);
                demo_release_at = -1;
            }
            if (IsKeyPressed(KEY_M)) {
                audio.toggle_mute();
                renderer.toast(audio.muted() ? "SOUND OFF" : "SOUND ON");
            }
            if (IsKeyPressed(KEY_F11)) renderer.bright = !renderer.bright;

            float dt = GetFrameTime();
            bool quit = false;
            for (; next_event < script.size() && script[next_event].t <= game_t; next_event++) {
                const ScriptEvent& e = script[next_event];
                if (e.op == '+' || e.op == '-') keys.set(SCRIPT_KEYS.at(e.arg), e.op == '+');
                else if (e.arg == "shot")
                    renderer.save_canvas((test_dir + "/frame_" + std::to_string(shots++) + ".png").c_str());
                else if (e.arg == "quit") quit = true;
                else if (e.arg == "view") toggle_view();
                else if (e.arg == "lives") toggle_lives();
                else if (e.arg == "pause") test_pause_until = GetTime() + 2.0;
                else if (e.arg == "cycle") cycle_weapon();
                else if (e.arg.rfind("room", 0) == 0) teleport(std::stoi(e.arg.substr(4), nullptr, 16));
                else if (e.arg == "newgame") new_game();
                else if (e.arg == "demo") demo_now();
            }
            if (quit || (!script.empty() && next_event == script.size())) break;
            if (renderer.transitioning()) {
                acc = 0;  // hold the game while the camera slides to the next room
            } else {
                acc += dt;
                int n = 0;
                while (acc >= TICK && n++ < MAX_TICKS_PER_FRAME) {
                    machine->tick();
                    acc -= TICK;
                    game_t += TICK;
                    smoother.sample(data, machine->ram(), machine->game_ip(), game_t);
                    auto spk = machine->speaker();
                    audio.set(spk.on, spk.hz, machine->ram()[addr::MUSIC_PLAYING] != 0);
                }
                if (n >= MAX_TICKS_PER_FRAME) acc = 0;
            }
            auto objects = smoother.at(game_t + acc);
            if (trace)
                for (const auto& o : objects)
                    if (o.sprite == LOG_SPRITE)
                        std::fprintf(trace.get(), "LOG,%.4f,%d,%.2f\n", game_t + acc, o.x, o.fx);
            if (trace && !objects.empty() && objects[0].slot == 0)
                std::fprintf(trace.get(), "%.4f,%d,%.2f,%04x,%02x,%d,%.0f\n", game_t + acc, objects[0].x,
                             objects[0].fx, objects[0].sprite, GameData::room(machine->ram()),
                             machine->ram()[addr::LIVES], machine->speaker().hz);
            if (trace) std::fprintf(trace.get(), "W,%.3f,%d\n", game_t, machine->ram()[addr::WEAPON] & 0x0f);
            if (trace) {
                std::fprintf(trace.get(), "O,%.3f,%02x", game_t, GameData::room(machine->ram()));
                for (const auto& o : data.objects(machine->ram())) std::fprintf(trace.get(), ",%d:%04x", o.slot, o.sprite);
                std::fprintf(trace.get(), "\n");
            }
            renderer.frame(machine->ram(), machine->vram(), objects, dt);
            renderer.present();
        }
    }
    CloseWindow();
    return 0;
}
