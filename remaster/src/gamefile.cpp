#include "gamefile.h"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>

namespace {

std::optional<std::vector<uint8_t>> read(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return std::nullopt;
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(f), {});
}

uint32_t rol(uint32_t v, int n) { return (v << n) | (v >> (32 - n)); }

}  // namespace

const std::vector<GameVariant> GAME_VARIANTS = {
    // Opera Soft release as commonly found: plain COM, keys 1-4 + QAOP. This copy carries a
    // trainer: game over skipped (0x64d jne -> jmp) and the speaker muted (0x3f96 out 61h ->
    // nops). Both are put back so it plays like the original.
    {"LSTONE.COM (Opera Soft)", "9cadce0a57e5b8052889e007fa698c29bd75fea7", false,
     {{0x064d, {0x75}}, {0x3f96, {0xe6, 0x61}}}},
};

std::optional<LoadedGame> identify(const std::vector<uint8_t>& data) {
    std::string h = sha1_hex(data);
    for (const auto& v : GAME_VARIANTS) {
        if (h != v.sha1) continue;
        LoadedGame g{&v, {}};
        if (!v.wrapper) g.com.assign(0x200, 0);  // plain COM: file offset 0 = address 0x100
        g.com.insert(g.com.end(), data.begin(), data.end());
        return g;
    }
    return std::nullopt;
}

std::string sha1_hex(const std::vector<uint8_t>& data) {
    uint32_t h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};
    std::vector<uint8_t> m(data);
    uint64_t bits = uint64_t(data.size()) * 8;
    m.push_back(0x80);
    while (m.size() % 64 != 56) m.push_back(0);
    for (int i = 7; i >= 0; i--) m.push_back(uint8_t(bits >> (i * 8)));
    for (size_t off = 0; off < m.size(); off += 64) {
        uint32_t w[80];
        for (int i = 0; i < 16; i++)
            w[i] = uint32_t(m[off + i * 4]) << 24 | uint32_t(m[off + i * 4 + 1]) << 16 |
                   uint32_t(m[off + i * 4 + 2]) << 8 | m[off + i * 4 + 3];
        for (int i = 16; i < 80; i++) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
        for (int i = 0; i < 80; i++) {
            uint32_t f, k;
            if (i < 20) f = (b & c) | (~b & d), k = 0x5A827999;
            else if (i < 40) f = b ^ c ^ d, k = 0x6ED9EBA1;
            else if (i < 60) f = (b & c) | (b & d) | (c & d), k = 0x8F1BBCDC;
            else f = b ^ c ^ d, k = 0xCA62C1D6;
            uint32_t t = rol(a, 5) + f + e + k + w[i];
            e = d, d = c, c = rol(b, 30), b = a, a = t;
        }
        h[0] += a, h[1] += b, h[2] += c, h[3] += d, h[4] += e;
    }
    char out[41];
    for (int i = 0; i < 5; i++) std::snprintf(out + i * 8, 9, "%08x", h[i]);
    return out;
}

std::string user_data_dir(const std::string& app) {
#ifdef _WIN32
    const char* base = std::getenv("APPDATA");  // %APPDATA%\<app>
    std::string dir = std::string(base ? base : ".") + "/" + app + "/";
#elif defined(__APPLE__)
    const char* home = std::getenv("HOME");
    std::string dir = std::string(home ? home : ".") + "/Library/Application Support/" + app + "/";
#else
    const char* xdg = std::getenv("XDG_DATA_HOME");  // ~/.local/share/<app>
    const char* home = std::getenv("HOME");
    std::string dir = xdg && *xdg ? std::string(xdg) + "/" + app + "/"
                                  : std::string(home ? home : ".") + "/.local/share/" + app + "/";
#endif
    std::error_code ec;
    std::filesystem::create_directories(dir, ec);
    return dir;
}

std::optional<LoadedGame> load_game(const std::vector<std::string>& candidates) {
    for (const auto& path : candidates)
        if (auto data = read(path))
            if (auto game = identify(*data)) return game;
    return std::nullopt;
}

std::optional<LoadedGame> adopt_dropped(const std::string& path, const std::string& dir, std::string& error) {
    auto data = read(path);
    if (!data) {
        error = "Cannot read that file.";
        return std::nullopt;
    }
    auto game = identify(*data);
    if (!game) {
        error = "This is not a supported version. Needed: " + std::string(GAME_VERSION) + ".";
        return std::nullopt;
    }
    std::ofstream out(dir + GAME_FILE, std::ios::binary);
    out.write(reinterpret_cast<const char*>(data->data()), std::streamsize(data->size()));
    if (!out) {
        error = "Could not save the file to " + dir;
        return std::nullopt;
    }
    return game;
}
