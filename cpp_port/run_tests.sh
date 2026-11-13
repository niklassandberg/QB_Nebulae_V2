#!/bin/bash
# Builds the port and runs every test: C++ unit tests and scenarios (ctest),
# the Python originals against the same expected traces (unittest), and the
# side-by-side comparison (compare.py). Needs g++/cmake and a Python 3 with
# numpy (PYTHON=..., default python3).
#   ./run_tests.sh [build-dir]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="${1:-$HERE/build}"
PYTHON="${PYTHON:-python3}"

cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=RelWithDebInfo > /dev/null
cmake --build "$BUILD" -j"$(nproc)"

echo "== C++ port (W): unit tests and scenarios"
(cd "$BUILD" && ctest --output-on-failure)

echo "== Python originals (B): scenarios"
"$PYTHON" -m unittest discover -s "$HERE/tests/py" -p "test_*.py"

echo "== B and W side by side"
"$PYTHON" "$HERE/tests/compare.py" --python "$PYTHON" --runner "$BUILD/scenario_runner"
