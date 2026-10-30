cmake_minimum_required(VERSION 3.13)
project(nebio LANGUAGES CXX)

# Hardware/communication layer for QB Nebulae V2, loaded by Python via ctypes.
# Build on the device:  sh Code/scripts/build_nebio.sh
# Needs: cmake, gcc, libgpiod (>= 2.0), liblo   ->  pacman -S cmake gcc libgpiod liblo

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Threads REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GPIOD REQUIRED IMPORTED_TARGET libgpiod>=2.0)
pkg_check_modules(LIBLO REQUIRED IMPORTED_TARGET liblo)

add_library(nebio SHARED
  src/nebio.cpp
  src/gpio.cpp
  src/gpiomem.cpp
  src/adc.cpp
  src/inputs.cpp
  src/leds.cpp
  src/links.cpp
)

target_include_directories(nebio PUBLIC include)
target_link_libraries(nebio PRIVATE PkgConfig::GPIOD PkgConfig::LIBLO Threads::Threads)
target_compile_options(nebio PRIVATE -Wall -Wextra)
set_target_properties(nebio PROPERTIES
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
)
