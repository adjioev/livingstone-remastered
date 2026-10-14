cmake_minimum_required(VERSION 3.20)
project(livingstone_remaster CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(RAYLIB REQUIRED IMPORTED_TARGET raylib)
if(WIN32)
  # MSYS2's unicorn.pc points at /ucrt64/include, which native CMake cannot resolve;
  # the library and headers are in the toolchain's default paths anyway.
  find_library(UNICORN_LIB NAMES unicorn REQUIRED)
else()
  pkg_check_modules(UNICORN REQUIRED IMPORTED_TARGET unicorn)
endif()

add_executable(livingstone
  src/main.cpp
  src/machine.cpp
  src/gamedata.cpp
  src/renderer.cpp
  src/smooth.cpp
  src/hud.cpp
  src/audio.cpp
  src/gamepad.cpp
  src/gamefile.cpp)
option(APP_BUNDLE "Release build: the .app (static raylib and unicorn) or the Windows zip" OFF)
if(APP_BUNDLE AND WIN32)
  # MSYS2/MinGW: raylib and unicorn DLLs are shipped next to the .exe (see .github/workflows)
  target_link_libraries(livingstone PRIVATE PkgConfig::RAYLIB ${UNICORN_LIB} -static-libgcc -static-libstdc++)
  set_target_properties(livingstone PROPERTIES WIN32_EXECUTABLE ON)  # no console window
  target_compile_definitions(livingstone PRIVATE APP_BUNDLE=1)
elseif(APP_BUNDLE)
  find_library(RAYLIB_STATIC NAMES libraylib.a PATHS ${RAYLIB_LIBRARY_DIRS} REQUIRED NO_DEFAULT_PATH)
  find_library(UNICORN_STATIC NAMES libunicorn.a PATHS ${UNICORN_LIBRARY_DIRS} REQUIRED NO_DEFAULT_PATH)
  target_include_directories(livingstone PRIVATE ${RAYLIB_INCLUDE_DIRS} ${UNICORN_INCLUDE_DIRS})
  target_link_libraries(livingstone PRIVATE ${RAYLIB_STATIC} ${UNICORN_STATIC}
    "-framework Cocoa" "-framework IOKit" "-framework CoreVideo" "-framework OpenGL"
    "-framework CoreAudio" "-framework AudioToolbox" "-framework CoreFoundation" pthread m)
  target_compile_definitions(livingstone PRIVATE APP_BUNDLE=1)
else()
  target_link_libraries(livingstone PRIVATE PkgConfig::RAYLIB PkgConfig::UNICORN)
endif()
target_compile_definitions(livingstone PRIVATE PROJECT_ROOT="${CMAKE_CURRENT_SOURCE_DIR}")
set(WINDOW_TITLE "Livingstone Remastered" CACHE STRING "Window title")
target_compile_definitions(livingstone PRIVATE WINDOW_TITLE="${WINDOW_TITLE}")
target_compile_options(livingstone PRIVATE -Wall -Wextra)
