# Livingstone Remastered

An HD remaster of *Livingstone Supongo* (Opera Soft, 1986) for DOS. The original game runs
unmodified inside a CPU emulator (unicorn); the remaster reads its state and draws repainted
1920×1080 rooms, sprites, effects and a new HUD on top. Press **R** to flip to the original
CGA graphics at any time.

**The game itself is not included.** You need your own copy of `LSTONE.COM`
(62 336 bytes, SHA-1 `9cadce0a57e5b8052889e007fa698c29bd75fea7`). Drop it onto the window
on first start, or put it at `original/LSTONE.COM` when running from source.

*Livingstone Supongo* is © Opera Soft. This project is a fan work and is not affiliated
with the rights holders.

## Download

Windows and Linux builds are on the [Releases](../../releases/latest) page:

- **Windows**: unzip `LivingstoneRemastered-windows.zip` and run `Livingstone.exe`. The exe is
  not signed, so SmartScreen may warn about an unknown publisher: *More info → Run anyway*.
- **Linux** (x86-64, X11 or XWayland): unpack `LivingstoneRemastered-linux-x86_64.tar.gz` and run
  `./livingstone`.

Then drag your `LSTONE.COM` onto the window; it is remembered for the next start.

## Build (macOS)

```sh
brew install cmake pkgconf raylib unicorn   # run.sh does this if missing
./run.sh                 # build and run from source
./make_app.sh            # dist/Livingstone Remastered.app (without the game file)
```

## Keys

| Key | Action |
|---|---|
| Arrows (+ QAOP or WASD, switch with K) | move, jump, crouch |
| 1–4 | boomerang, knife, grenade, pole |
| Space | fire / charge a throw or vault |
| Esc | pause (N new game, T teleport, X quit) |
| R | original / remastered graphics |
| V | effects on/off |
| M | sound on/off |
| F | full screen |
| L | infinite lives |

## Layout

- `remaster/src` — runtime (C++20, raylib, unicorn)
- `remaster/assets` — HD rooms, sprites, animations, effect masks, shaders
- `tools` — asset pipeline (Gemini image generation, extraction, checks)
- `docs` — notes on the game's data layout

## License

Code: GPL-2.0 (see `LICENSE`). The remastered artwork in `remaster/assets` is a fan
recreation of *Livingstone Supongo* (© Opera Soft) and is provided for personal,
non-commercial use only; it is not covered by the GPL.
