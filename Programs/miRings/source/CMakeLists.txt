cmake_minimum_required(VERSION 3.16)
project(miRings CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(JACK REQUIRED IMPORTED_TARGET jack)
pkg_check_modules(LIBLO REQUIRED IMPORTED_TARGET liblo)

add_executable(miRings
  main.cc
  src/rings/dsp/fm_voice.cc
  src/rings/dsp/part.cc
  src/rings/dsp/resonator.cc
  src/rings/dsp/string.cc
  src/rings/dsp/string_synth_part.cc
  src/rings/resources.cc
  src/stmlib/dsp/units.cc
  src/stmlib/utils/random.cc)
target_include_directories(miRings PRIVATE src)
# TEST: stmlib's portable code instead of Cortex-M4 instructions
target_compile_definitions(miRings PRIVATE TEST)
# The vendored code is not ours to clean up: no warnings from it
target_compile_options(miRings PRIVATE -O2 -w)
target_link_libraries(miRings PRIVATE PkgConfig::JACK PkgConfig::LIBLO pthread)
