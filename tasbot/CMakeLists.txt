cmake_minimum_required(VERSION 3.20)
project(tasbot CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Find packages from vcpkg ---
find_package(Protobuf CONFIG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(lz4 CONFIG REQUIRED)
find_package(PNG)

# --- Protobuf code generation ---
protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS
    ${CMAKE_CURRENT_SOURCE_DIR}/marionet.proto
)

# --- cc-lib sources (compiled a la carte, mirrors makefile line 59) ---
set(CCLIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../cc-lib")
set(CCLIB_SOURCES
    ${CCLIB_DIR}/util.cc
    ${CCLIB_DIR}/arcfour.cc
    ${CCLIB_DIR}/base/stringprintf.cc
    ${CCLIB_DIR}/city/city.cc
    ${CCLIB_DIR}/textsvg.cc
)
# stb_image.h is header-only when STB_IMAGE_IMPLEMENTATION is defined.
# Check if there's a .cc wrapper; otherwise we need to create one.
if(EXISTS "${CCLIB_DIR}/stb_image.cc")
    list(APPEND CCLIB_SOURCES ${CCLIB_DIR}/stb_image.cc)
endif()

# --- FCEUX fork sources ---
# Core emulation (mirrors makefile line 75)
set(FCEU_CORE_SOURCES
    fceu/asm.cpp fceu/cart.cpp fceu/cheat.cpp fceu/conddebug.cpp
    fceu/config.cpp fceu/debug.cpp fceu/drawing.cpp fceu/emufile.cpp
    fceu/fceu.cpp fceu/fds.cpp fceu/file.cpp fceu/filter.cpp
    fceu/ines.cpp fceu/input.cpp fceu/movie.cpp fceu/netplay.cpp
    fceu/nsf.cpp fceu/oldmovie.cpp fceu/palette.cpp fceu/ppu.cpp
    fceu/sound.cpp fceu/state.cpp fceu/unif.cpp fceu/video.cpp
    fceu/vsuni.cpp fceu/wave.cpp fceu/x6502.cpp
)

# Mappers (mirrors makefile line 63)
file(GLOB MAPPER_SOURCES fceu/mappers/*.cpp fceu/mappers/*.c)

# Boards (mirrors makefile line 71)
file(GLOB BOARD_SOURCES fceu/boards/*.cpp fceu/boards/*.c)

# Input devices (mirrors makefile line 73)
file(GLOB INPUT_SOURCES fceu/input/*.cpp fceu/input/*.c)

# Utils (mirrors makefile line 66)
file(GLOB UTILS_SOURCES fceu/utils/*.cpp fceu/utils/*.c)

# Drivers common (mirrors makefile line 78)
set(DRIVERS_COMMON_SOURCES
    fceu/drivers/common/args.cpp
    fceu/drivers/common/cheat.cpp
    fceu/drivers/common/hq2x.cpp
    fceu/drivers/common/hq3x.cpp
    fceu/drivers/common/scale2x.cpp
    fceu/drivers/common/scale3x.cpp
    fceu/drivers/common/scalebit.cpp
    fceu/drivers/common/vidblit.cpp
)
# nes_ntsc.c is a C file
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/fceu/drivers/common/nes_ntsc.c")
    list(APPEND DRIVERS_COMMON_SOURCES fceu/drivers/common/nes_ntsc.c)
endif()

set(ALL_FCEU_SOURCES
    ${FCEU_CORE_SOURCES}
    ${MAPPER_SOURCES}
    ${BOARD_SOURCES}
    ${INPUT_SOURCES}
    ${UTILS_SOURCES}
    ${DRIVERS_COMMON_SOURCES}
)

# --- TASBot core sources (mirrors makefile line 85) ---
set(TASBOT_CORE_SOURCES
    headless-driver.cc
    simplefm2.cc
    emulator.cc
    basis-util.cc
    objective.cc
    weighted-objectives.cc
    motifs.cc
    util.cc
    netutil.cc
    ${PROTO_SRCS}
)

# --- Core static library ---
add_library(tasbot_core STATIC
    ${TASBOT_CORE_SOURCES}
    ${CCLIB_SOURCES}
    ${ALL_FCEU_SOURCES}
)

target_include_directories(tasbot_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../cc-lib
    ${CMAKE_CURRENT_SOURCE_DIR}/../cc-lib/city
    ${CMAKE_CURRENT_BINARY_DIR}  # for generated .pb.h files
)

target_compile_definitions(tasbot_core PUBLIC
    MARIONET=1
    DUMMY_UI
    NOWINSTUFF
    PSS_STYLE=1
    _CRT_SECURE_NO_WARNINGS
    _WINSOCK_DEPRECATED_NO_WARNINGS
    NOMINMAX
    # Disable MSVC 2022+ hardened container checks.
    # The FCEUX EMUFILE_MEMORY wrapper uses vector[] to access bytes
    # within the vector's capacity but beyond its logical size (the
    # EMUFILE tracks its own 'len' independently).  This is safe
    # (the memory is allocated) but trips the hardened bounds check.
    # Tom7's original code relied on GCC's unchecked operator[].
    _MSVC_STL_HARDENED_VECTORS=0
)

# MSVC-specific settings
if(MSVC)
    target_compile_options(tasbot_core PUBLIC
        /W3
        /wd4244  # conversion from larger to smaller type
        /wd4996  # deprecated functions (strdup, etc.)
        /wd4267  # size_t to int conversion
        /wd4018  # signed/unsigned mismatch
        /wd4101  # unreferenced local variable
        /wd4305  # truncation from double to float
        /wd4805  # unsafe mix of bool and int
        /wd4309  # truncation of constant value
        /wd4838  # narrowing conversion
        /wd4146  # unary minus on unsigned
        /wd4804  # unsafe use of type bool
        /wd4715  # not all control paths return
        # /wd4700 removed — hiding "uninitialized local variable used"
        # masks real undefined-behaviour bugs; fix them instead.
        /wd4554  # check operator precedence
        /wd4002  # too many actual parameters for macro
        /wd4005  # macro redefinition
        /Zc:strictStrings-  # allow string literals to char* (FCEUX legacy)
    )
endif()

# --- Release optimizations ---
# NOTE: /arch:AVX2 was removed because the FCEUX PPU code uses uint32*
# casts and FCEU_dwmemset extensively.  The auto-vectoriser turns these
# into aligned AVX2 stores (vmovdqa) that crash with ACCESS_VIOLATION
# when the destination buffer is not 32-byte aligned.
# /GL and /LTCG are kept; they are safe with the default SSE2 codegen.
if(MSVC)
    target_compile_options(tasbot_core PUBLIC
        $<$<CONFIG:Release>:/GL>        # Whole-program optimization
    )
    target_link_options(tasbot_core PUBLIC
        $<$<CONFIG:Release>:/LTCG>      # Link-time code generation
    )
endif()

target_link_libraries(tasbot_core PUBLIC
    protobuf::libprotobuf
    ZLIB::ZLIB
    lz4::lz4
    ws2_32    # Winsock2 for networking
)

# --- Executables ---

add_executable(learnfun learnfun.cc)
target_link_libraries(learnfun tasbot_core)

add_executable(playfun playfun.cc)
target_link_libraries(playfun tasbot_core)

# Copy the GUI launcher alongside the executables so it can find them.
add_custom_command(TARGET playfun POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/tasbot_gui.pyw"
        "$<TARGET_FILE_DIR:playfun>/tasbot_gui.pyw"
    COMMENT "Copying tasbot_gui.pyw to output directory"
)

add_executable(tasbot_exe tasbot.cc)
set_target_properties(tasbot_exe PROPERTIES OUTPUT_NAME "tasbot")
target_link_libraries(tasbot_exe tasbot_core)

add_executable(emu_test emu_test.cc)
target_link_libraries(emu_test tasbot_core)

add_executable(objective_test objective_test.cc)
target_link_libraries(objective_test tasbot_core)

add_executable(weighted_objectives_test weighted-objectives_test.cc)
target_link_libraries(weighted_objectives_test tasbot_core)

# --- PNG-dependent visualization targets (optional) ---
if(PNG_FOUND)
    add_executable(scopefun scopefun.cc pngsave.cc wave.cc)
    target_link_libraries(scopefun tasbot_core PNG::PNG)
    target_include_directories(scopefun PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/libpng)

    add_executable(pinviz pinviz.cc pngsave.cc wave.cc)
    target_link_libraries(pinviz tasbot_core PNG::PNG)
    target_include_directories(pinviz PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/libpng)
endif()
