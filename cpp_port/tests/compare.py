#!/usr/bin/env python3
# Every scenario through the Python originals (B) and the C++ port (W); the
# two traces must be identical. Exit status 1 on any difference.
#   compare.py [--python PY] [--runner BIN] [scenario.txt ...]
import argparse
import difflib
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, cwd="/tmp")
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if p.returncode != 0:
        return None, err or "exit %d\n" % p.returncode
    return out, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--runner", default=os.path.join(HERE, "..", "build", "scenario_runner"))
    ap.add_argument("--traces", default=os.path.join(HERE, "traces"))
    ap.add_argument("scenarios", nargs="*")
    args = ap.parse_args()
    scenarios = args.scenarios or sorted(glob.glob(os.path.join(HERE, "scenarios", "*.txt")))
    os.makedirs(args.traces, exist_ok=True)
    failed = 0
    lines_total = 0
    for sc in scenarios:
        name = os.path.splitext(os.path.basename(sc))[0]
        py, py_err = run([args.python, os.path.join(HERE, "py", "runner.py"), os.path.abspath(sc)])
        cpp, cpp_err = run([os.path.abspath(args.runner), os.path.abspath(sc)])
        if py is None or cpp is None:
            failed += 1
            print("CRASH %s\n%s%s" % (name, py_err if py is None else "", cpp_err if cpp is None else ""))
            continue
        with open(os.path.join(args.traces, name + ".py.txt"), "w") as f:
            f.write(py)
        with open(os.path.join(args.traces, name + ".cpp.txt"), "w") as f:
            f.write(cpp)
        n = py.count("\n")
        lines_total += n
        if py == cpp:
            print("same  %-28s %5d lines" % (name, n))
        else:
            failed += 1
            print("DIFF  %s" % name)
            diff = difflib.unified_diff(py.splitlines(), cpp.splitlines(), "python", "c++", lineterm="", n=1)
            for i, line in enumerate(diff):
                if i > 40:
                    print("  ...")
                    break
                print("  " + line)
    print("%d scenarios, %d trace lines, %d different" % (len(scenarios), lines_total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
