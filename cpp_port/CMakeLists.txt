cmake_minimum_required(VERSION 3.16)
project(nebulae_cpp_port CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()
add_compile_options(-Wall -Wextra)

# The port (W): no hardware, everything outside goes through nebio_api.h.
add_library(nebport STATIC
    src/pyvalue.cpp
    src/textfile.cpp
    src/fatal.cpp
    src/globals.cpp
    src/classlogger.cpp
    src/configsettings.cpp
    src/nconfig.cpp
    src/nebio.cpp
    src/inputs.cpp
    src/control.cpp
    src/digitaldata.cpp
    src/encoderpages.cpp
    src/settings.cpp
    src/wavewriter.cpp
    src/nebmixer.cpp
    src/senders.cpp
    src/nebconfig.cpp
    src/controlhandler.cpp
    src/controlhandlerEncoders.cpp
    src/controlhandlerSC.cpp
    src/controlhandlerProg.cpp
    src/controlhandlerPD.cpp)
target_include_directories(nebport PUBLIC src)
find_package(Threads REQUIRED)
target_link_libraries(nebport PUBLIC Threads::Threads)

# The real backends (nebio C functions, libasound): compiled to check they fit.
add_library(nebport_real OBJECT src/real_backends.cpp)
target_include_directories(nebport_real PRIVATE src)

# Runs a scenario against the port (tests/compare.py runs it beside the Python one).
add_executable(scenario_runner tests/cpp/runner.cpp)
target_link_libraries(scenario_runner PRIVATE nebport)

# Plain C++ unit tests of the port.
add_executable(unit_tests tests/cpp/unit_tests.cpp)
target_link_libraries(unit_tests PRIVATE nebport)

# ctest: the unit tests, and every scenario against its expected trace (the
# one the Python originals give, tests/expected/).
enable_testing()
add_test(NAME unit_tests COMMAND unit_tests)
file(GLOB SCENARIOS ${CMAKE_CURRENT_SOURCE_DIR}/tests/scenarios/*.txt)
foreach(sc ${SCENARIOS})
    get_filename_component(name ${sc} NAME_WE)
    add_test(NAME scenario_${name}
             COMMAND scenario_runner ${sc} --expect ${CMAKE_CURRENT_SOURCE_DIR}/tests/expected/${name}.txt
             WORKING_DIRECTORY /tmp)
endforeach()

# ConfigSettings under threads (also run it in a -fsanitize=thread build).
add_executable(thread_tests tests/cpp/thread_tests.cpp)
target_link_libraries(thread_tests PRIVATE nebport)
add_test(NAME thread_tests COMMAND thread_tests)
