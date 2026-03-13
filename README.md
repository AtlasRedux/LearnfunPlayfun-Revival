# Learnfun & Playfun Revival

A Windows port of Tom Murphy VII's (tom7) **Learnfun / Playfun** system for
automatically playing NES games.  The AI watches a human-recorded replay to
learn what "progress" looks like, then plays the game itself using a
distributed search over emulator states.

Originally built for Linux with SDL, GCC, and hand-rolled Makefiles, this
revival targets **Windows 10/11 x64** with MSVC, CMake, and vcpkg.  SDL and
SDL_net have been replaced by native Winsock2 networking.

> Based on the code and paper from
> **"The First Level of Super Mario Bros. is Easy with Lexicographic
> Orderings and Time Travel"** (tom7, SIGBOVIK 2013).
> Original source: <http://tom7.org/mario/>


<img width="320" height="358" alt="Skjermbilde 2026-03-13 171953" src="https://github.com/user-attachments/assets/a08726eb-be74-43d6-bcbc-2f559ab56f2d" />

---

## Architecture

```
                    learnfun.exe
                         |
               ROM + replay (.fm2)
                         |
                         v
              .objectives + .motifs
                         |
                         v
    playfun.exe --master PORT PORT PORT ...
         |           |           |
         v           v           v
    --helper 1   --helper 2   --helper N
```

**learnfun** watches a human replay and learns a set of weighted memory
objectives -- what "getting better" looks like.

**playfun** uses a master / helper architecture (MARIONET protocol) to run
a distributed search.  Each helper is a separate process running its own
headless FCEUX emulator instance, evaluating candidate input sequences in
parallel.

---

## Quick start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Visual Studio 2022 | 17.x | C++ desktop workload |
| CMake | 3.20+ | Included with VS |
| vcpkg | latest | See below |
| Python 3.10+ | optional | For the GUI launcher |

**Install vcpkg** (if you don't have it):

```powershell
cd C:\
git clone https://github.com/microsoft/vcpkg.git
.\vcpkg\bootstrap-vcpkg.bat
```

If vcpkg is installed somewhere other than `C:\vcpkg`, update the
`CMAKE_TOOLCHAIN_FILE` path in `tasbot/CMakePresets.json`.

### Build

```powershell
cd tasbot
cmake --preset default          # configure (uses vcpkg toolchain)
cmake --build --preset default  # build Release
```

The first build fetches and compiles dependencies (protobuf, zlib, lz4,
libpng) via vcpkg -- this takes a few minutes.

Binaries and the GUI launcher land in `tasbot/build/Release/`.

To build Debug instead: `cmake --build --preset debug`

### Run

**Step 1 -- Learn.**  Provide a NES ROM and a human-played replay (`.fm2`
format, recordable in FCEUX).  Create a `config.txt` in the working
directory:

```
game GAMENAME
movie replay.fm2
```

`game` is the ROM filename without extension.  Place the ROM
(`GAMENAME.nes`), the `.fm2` replay, and `config.txt` alongside the
executables, then run:

```
learnfun.exe
```

This outputs `GAMENAME.objectives` and `GAMENAME.motifs`.

**Step 2 -- Play.**  With the `.objectives` and `.motifs` files in place,
launch helpers and a master:

```
playfun.exe --helper 8000
playfun.exe --helper 8001
playfun.exe --helper 8002
playfun.exe --master 8000 8001 8002
```

Or let playfun auto-detect your CPU cores:

```
playfun.exe --auto
```

**GUI launcher** -- a tkinter GUI is included and auto-copied to the build
output directory:

```powershell
cd build\Release
pythonw tasbot_gui.pyw
```

The GUI auto-detects ROM / replay files in its directory, lets you
configure helper count and ports, spawns everything, and streams master
output.

### Watching replays (FCEUX integration)

Place FCEUX in a `FCEUX\` subfolder next to the executables.  The GUI
auto-detects `fceux64.exe` or `fceux.exe` and enables the
**Watch Replay (FCEUX)** button.  This opens the current
`*-playfun-futures-progress.fm2` in FCEUX so you can watch the current
progress.  If no FCEUX is found the button is greyed out.

```
build/Release/
  learnfun.exe
  playfun.exe
  tasbot_gui.pyw
  FCEUX/
    fceux64.exe   (or fceux.exe)
```

---

## Frequently asked questions

### Do I need to build from source?

Only if you want to modify the C++ code.  Pre-built binaries are available
on the [Releases](https://github.com/AtlasRedux/LearnfunPlayfun-Revival/releases)
page.

### Where do I get FCEUX?

Download from <https://fceux.com>.  Extract it into a `FCEUX\` subfolder
next to the executables.  Both 32-bit (`fceux.exe`) and 64-bit
(`fceux64.exe`) are supported -- the GUI prefers 64-bit if both are present.

### Where do I get a replay (.fm2) file?

Record one yourself in FCEUX: **File > Movie > Record Movie**.  Play
through the section of the game you want the AI to learn from, then stop
recording.  The resulting `.fm2` file is your training data.

### The AI is stuck / not making progress

- Make sure your training replay demonstrates clear forward progress
  (advancing through levels, increasing score, etc.).
- More helpers = faster search.  Use as many as your CPU allows.
- Some games are inherently harder for the algorithm.  Games with clear
  left-to-right scrolling (platformers) work best.

### Can I use this with games other than Super Mario Bros.?

Yes.  Any NES game with an `.nes` ROM and a recorded `.fm2` replay will
work.  Results vary depending on how well the game's memory layout maps
to the lexicographic objective function.

### I get "helpers exited during startup"

This usually means the port range is already in use.  Change the start
port in the GUI or make sure no other instances are running.

---

## Changes from the original

### Networking

- **SDL / SDL_net removed.**  All networking uses Winsock2 (`ws2_32`).
- **One request per connection.**  Restored the original tom7 helper
  lifecycle: each helper processes a single work item per TCP connection,
  then hangs up and listens again.  The revival's persistent-connection
  `HelperPool` has been disabled as it was incompatible with this model.

### Build system

- **CMake + vcpkg** replaces hand-rolled Makefiles and in-tree dependency
  source.  Dependencies are fetched and built automatically.
- **MSVC 2022 x64** is the primary (and only tested) target.

### Bug fixes

- **StateCache use-after-free** (`emulator.cc`):  `MaybeResize()` and
  `Resize()` deleted key/value vectors *before* erasing them from the
  `unordered_map`.  On MSVC, `erase(iterator)` recomputes the key's hash
  to locate the bucket, so accessing a freed key is undefined behaviour.
  Fixed by erasing first, then deleting.  (GCC's libstdc++ caches hashes
  in nodes, hiding this bug on Linux.)

- **AVX2 alignment crash:**  Removed `/arch:AVX2` -- the FCEUX PPU uses
  unaligned `uint32*` casts that the auto-vectoriser turns into aligned
  AVX2 stores, causing `ACCESS_VIOLATION`.

- **MSVC hardened containers:**  Disabled via
  `_MSVC_STL_HARDENED_VECTORS=0` -- FCEUX's `EMUFILE_MEMORY` deliberately
  accesses vector capacity beyond logical size.

### Additions

- **Windows crash handler** with `StackWalk64` stack traces for diagnosing
  crashes.
- **ANSI colour support** -- enables Windows Virtual Terminal Processing so
  the coloured progress bars render natively in modern consoles (no
  ansicon required).
- **GUI launcher** (`tasbot_gui.pyw`) -- tkinter front-end that manages
  helper / master lifecycle, with:
  - Auto-detection of ROM and replay files
  - Configurable helper count and port range
  - Resume from last progress file
  - **FCEUX replay integration** -- watch the AI's progress FM2 in FCEUX
    directly from the GUI (auto-detects `FCEUX\fceux64.exe` or
    `FCEUX\fceux.exe`; button is disabled if neither is found)
  - **Help button** -- links to the GitHub repository for documentation
- **`--auto` mode** -- `playfun.exe --auto [N]` spawns N helpers (default:
  CPU cores - 1) and a master in one command with automatic cleanup via
  Windows Job Objects.

### Removed

- SDL and SDL_net dependencies
- `/wd4700` warning suppression (uninitialized variable use is a real bug)

---

## Project structure

```
LearnfunPlayfun-Revival/
  README.md
  .gitignore
  cc-lib/                 Tom7's utility library (subset)
    base/                 stringprintf, logging macros
    city/                 CityHash (used by StateCache)
    opt/                  opt.h
  tasbot/
    CMakeLists.txt        Build configuration
    CMakePresets.json      VS 2022 / vcpkg presets
    vcpkg.json            Dependency manifest
    marionet.proto        Protobuf schema (MARIONET protocol)
    playfun.cc            Distributed player (master + helper)
    learnfun.cc           Objective learning from replays
    emulator.cc / .h      FCEUX wrapper + StateCache
    netutil.cc / .h       Winsock2 networking
    tasbot_gui.pyw        Python / tkinter GUI launcher
    fceu/                 Embedded FCEUX 2.1.6 fork (headless)
      boards/             Mapper board implementations
      drivers/common/     Video scaling / blitting
      input/              Input device emulation
      mappers/            NES mapper implementations
      palettes/           Colour palette data
      utils/              MD5, memory, etc.
```

## Security note

The MARIONET protocol is **not secure**.  It loads raw emulator savestates
from the network without validation.  Do not expose helper ports to
untrusted networks.

## License

The original code was released by Tom Murphy VII.  The embedded FCEUX is
under the GPL.  See `fceu/COPYING`.
