# Opt-in cProfile of the main loop (ui.update() + updateAll()), for finding
# where the Python main thread spends its time. Only runs when the flag file
# exists, so it can be tried without a new firmware:
#   touch /home/alarm/nebulae_profile   (optional content: seconds, default 60)
# Results: /tmp/nebulae_profile.pstats and /tmp/nebulae_profile.txt
import cProfile
import io
import os
import pstats
import time

PROFILE_FLAG = "/home/alarm/nebulae_profile"
PROFILE_OUT = "/tmp/nebulae_profile"


class LoopProfile(object):

    def __init__(self, log):
        self.log = log
        self.prof = None
        self.passes = 0
        if not os.path.exists(PROFILE_FLAG):
            return
        try:
            with open(PROFILE_FLAG) as f:
                self.duration = float(f.read().strip() or 60)
        except (IOError, ValueError):
            self.duration = 60.0
        self.log.info("main loop profile: %.0f s -> %s.txt", self.duration, PROFILE_OUT)
        self.prof = cProfile.Profile()
        self.start = time.time()
        self.prof.enable()

    # Call once per loop pass.
    def tick(self):
        if self.prof is None:
            return
        self.passes += 1
        elapsed = time.time() - self.start
        if elapsed < self.duration:
            return
        self.prof.disable()
        self.prof.dump_stats(PROFILE_OUT + ".pstats")
        out = io.StringIO()
        out.write("%d passes in %.1f s = %.1f passes/s\n\n" % (self.passes, elapsed, self.passes / elapsed))
        stats = pstats.Stats(self.prof, stream=out)
        stats.sort_stats("tottime").print_stats(40)
        stats.sort_stats("cumulative").print_stats(40)
        with open(PROFILE_OUT + ".txt", "w") as f:
            f.write(out.getvalue())
        self.log.info("main loop profile written: %s.txt", PROFILE_OUT)
        self.prof = None
