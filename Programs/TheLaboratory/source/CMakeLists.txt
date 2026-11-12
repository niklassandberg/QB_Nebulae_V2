cmake_minimum_required(VERSION 3.16)
project(thelaboratory CXX)

set(CMAKE_CXX_STANDARD 17)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(JACK REQUIRED IMPORTED_TARGET jack)
pkg_check_modules(LIBLO REQUIRED IMPORTED_TARGET liblo)

add_executable(thelaboratory main.cc)
target_link_libraries(thelaboratory PRIVATE PkgConfig::JACK PkgConfig::LIBLO pthread)
