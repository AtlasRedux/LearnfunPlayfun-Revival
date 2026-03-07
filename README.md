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
objectives — what "getting better" looks like.

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
libpng) via vcpkg — this takes a few minutes.

Binaries, required DLLs, and the GUI launcher land in
`tasbot/build/Release/`.

To build Debug instead: `cmake --build --preset debug`

### Binary distribution

To run on a machine without building from source, copy these files from
`build/Release/` into a single folder:

```
playfun.exe
learnfun.exe
tasbot_gui.pyw          (optional — requires Python 3.10+)
abseil_dll.dll
libprotobuf.dll
libpng16.dll
lz4.dll
zlib1.dll
```

Then add your game files (`.nes`, `.fm2`, `.objectives`, `.motifs`,
`config.txt`) to the same folder.

### Run

**Step 1 — Learn.**  Provide a NES ROM and a human-played replay (`.fm2`
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

**Step 2 — Play.**  With the `.objectives` and `.motifs` files in place,
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

**GUI launcher** — a tkinter GUI is included and auto-copied to the build
output directory:

```powershell
cd build\Release
pythonw tasbot_gui.pyw
```

The GUI auto-detects ROM / replay files in its directory, lets you
configure helper count and ports, spawns everything, and streams master
output.

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

- **AVX2 alignment crash:**  Removed `/arch:AVX2` — the FCEUX PPU uses
  unaligned `uint32*` casts that the auto-vectoriser turns into aligned
  AVX2 stores, causing `ACCESS_VIOLATION`.

- **MSVC hardened containers:**  Disabled via
  `_MSVC_STL_HARDENED_VECTORS=0` — FCEUX's `EMUFILE_MEMORY` deliberately
  accesses vector capacity beyond logical size.

### Additions

- **Windows crash handler** with `StackWalk64` stack traces for diagnosing
  crashes.
- **ANSI colour support** — enables Windows Virtual Terminal Processing so
  the coloured progress bars render natively in modern consoles (no
  ansicon required).
- **GUI launcher** (`tasbot_gui.pyw`) — tkinter front-end that manages
  helper / master lifecycle.
- **`--auto` mode** — `playfun.exe --auto [N]` spawns N helpers (default:
  CPU cores − 1) and a master in one command with automatic cleanup via
  Windows Job Objects.

### Removed

- SDL and SDL_net dependencies
- `/wd4700` warning suppression (uninitialized variable use is a real bug)

---

## Project structure

```
LFPFRevival1.0/
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
