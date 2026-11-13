# unittest of the Python originals: every scenario must give its expected trace
# (tests/expected/<name>.txt). Each runs in its own process, as module state
# (nebio's snapshot, the sent-values cache) carries over within one.
#   python3 -m unittest discover -s tests/py -p "test_*.py"
import glob
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)


class Originals(unittest.TestCase):
    pass


def make_test(scenario, expected):
    def test(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "runner.py"), scenario],
                           capture_output=True, cwd="/tmp")
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        with open(expected, encoding="utf-8") as f:
            want = f.read()
        self.assertEqual(p.stdout.decode("utf-8", "replace"), want)
    return test


for scenario in sorted(glob.glob(os.path.join(TESTS, "scenarios", "*.txt"))):
    name = os.path.splitext(os.path.basename(scenario))[0]
    expected = os.path.join(TESTS, "expected", name + ".txt")
    if os.path.exists(expected):
        setattr(Originals, "test_" + name, make_test(scenario, expected))


if __name__ == "__main__":
    unittest.main()
