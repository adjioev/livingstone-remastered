#pragma once

// Finding the user's own copy of the original game (it is not shipped with the remaster),
// OpenXcom-style: look in the usual places, else ask for it to be dropped on the window.

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

// The release the remaster's addresses are mapped for: Opera Soft's LSTONE.COM. (The code
// still knows how to start a COM behind a loader wrapper, as the 1991 Kiev port had.)
struct GameVariant {
    const char* name;
    const char* sha1;
    bool wrapper;  // 256-byte joystick wrapper in front (the Kiev port); else a plain COM
    // Bytes restored in memory at start (the file on disk is never changed).
    std::vector<std::pair<uint16_t, std::vector<uint8_t>>> restore;
};
extern const std::vector<GameVariant> GAME_VARIANTS;

constexpr const char* GAME_FILE = "LSTONE.COM";  // name the dropped copy is saved under
constexpr const char* GAME_VERSION = "Livingstone Supongo for DOS (Opera Soft): LSTONE.COM, 62336 bytes";

struct LoadedGame {
    const GameVariant* variant;
    std::vector<uint8_t> com;  // normalised: game address A at offset A + 0x100
};

std::string sha1_hex(const std::vector<uint8_t>& data);

// ~/Library/Application Support/<app> (created on demand), with trailing slash.
std::string user_data_dir(const std::string& app);

// Recognise a file's bytes as a supported release.
std::optional<LoadedGame> identify(const std::vector<uint8_t>& data);

// First supported copy among the candidate paths, or nothing.
std::optional<LoadedGame> load_game(const std::vector<std::string>& candidates);

// Check a dropped file; on success copy it into dir and return it, else set error.
std::optional<LoadedGame> adopt_dropped(const std::string& path, const std::string& dir, std::string& error);
