cmake_minimum_required(VERSION 3.16)
project(audrey CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(JACK REQUIRED IMPORTED_TARGET jack)
pkg_check_modules(LIBLO REQUIRED IMPORTED_TARGET liblo)

add_executable(audrey
  main.cc
  src/audrey/BiquadFilters.cpp
  src/audrey/DCBlock.cpp
  src/audrey/FeedbackSynthEngine.cpp
  src/audrey/KarplusString.cpp
  src/daisysp/Dynamics/crossfade.cpp
  src/daisysp/Dynamics/limiter.cpp
  src/daisysp/Effects/overdrive.cpp
  src/daisysp/Synthesis/oscillator.cpp
  src/daisysp-lgpl/Effects/reverbsc.cpp
  src/daisysp-lgpl/Filters/tone.cpp)
# shim/ first: daisysp.h and memory/sdram_alloc.h for the Pi instead of the Daisy's
target_include_directories(audrey PRIVATE shim src/audrey src/daisysp src/daisysp/Utility src/daisysp-lgpl)
# The vendored code is not ours to clean up: no warnings from it
target_compile_options(audrey PRIVATE -O2 -w)
target_link_libraries(audrey PRIVATE PkgConfig::JACK PkgConfig::LIBLO pthread)
