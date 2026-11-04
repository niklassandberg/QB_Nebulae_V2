cmake_minimum_required(VERSION 3.16)
project(proxy CXX)

set(CMAKE_CXX_STANDARD 17)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(JACK REQUIRED IMPORTED_TARGET jack)
pkg_check_modules(LIBLO REQUIRED IMPORTED_TARGET liblo)

# Your own .cc/.cpp files go in this list.
add_executable(proxy main.cc)
target_link_libraries(proxy PRIVATE PkgConfig::JACK PkgConfig::LIBLO pthread)
