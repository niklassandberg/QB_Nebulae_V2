#!/usr/bin/env python3
# Load for noise_test.sh steps "poll", "leds", "cpu", "jitter", "lock",
# "wake", "gpio" and "spi":
# the parts of a running Nebulae, without Nebulae.
#   noise_test_load.py            nebio reads all inputs at Nebulae's rates and
#                                 a Python loop takes a snapshot each time new
#                                 ADC data is there (as updateAll, ~400/s)
#   noise_test_load.py --leds     the same, plus every LED at half brightness
#                                 (PWM), the reset LED too
#   noise_test_load.py --jitter F every scan interval varies randomly by up to
#                                 +-F (e.g. 0.3); the mean rate stays the same
#   noise_test_load.py --lock     scans locked to the audio clock: this program
#                                 plays the silence itself (ALSA) in blocks of
#                                 LOCK_FRAMES and triggers one scan per block
#                                 (48000 / 64 = 750 scans/s in audio time; 64 is
#                                 the smallest block the audio chip takes)
#   Finding how the scans' pulse gets into the audio:
#   noise_test_load.py --wake     no nebio, no GPIO, no SPI: only wakes up
#                                 WAKE_HZ times a second and sleeps again (CPU)
#   noise_test_load.py --rates S,D,A --nosnap
#                                 nebio at scan S, digital D and ADC A Hz, no
#                                 Python snapshot loop (gpio: 1200,400,1;
#                                 spi: 400,1,400)
import ctypes
import os
import signal
import sys
import threading
import time

WAKE_HZ = 1200  # Nebulae's scan rate

signal.signal(signal.SIGTERM, lambda signum, frame: os._exit(0))


def log(line):
    with open("/tmp/noise_test_load.log", "a") as f:
        f.write(line + "\n")


if "--wake" in sys.argv:
    period = 1000000000 // WAKE_HZ
    deadline = time.monotonic_ns()
    wakes, last = 0, time.monotonic()
    while True:
        deadline += period  # absolute, as nebio's scan loop
        delay = deadline - time.monotonic_ns()
        if delay > 0:
            time.sleep(delay / 1e9)
        wakes += 1
        if time.monotonic() - last >= 10:
            log("wake %.0f Hz" % (wakes / (time.monotonic() - last)))
            wakes, last = 0, time.monotonic()

sys.path.insert(0, "/home/alarm/QB_Nebulae_V2/Code/nebulae")
import nebio

LOCK_FRAMES = 64     # smallest period of the audio chip: 48000 / 64 = 750 Hz
LOCK_BUFFER = 1024   # frames; a 192-frame buffer ran dry (281 scans/s, tested)

# Rates as Nebulae: nebio_scan_hz, nebio_digital_hz, nebio_adc_hz in
# configsettings.py (defaults 1200, 400, 400). Locked:
# 750 scans/s (one per block), digital and ADC every 2nd scan (375/s).
nebio.inputs()
if "--rates" in sys.argv:
    nebio.set_input_rates(*[int(r) for r in sys.argv[sys.argv.index("--rates") + 1].split(",")])
elif "--lock" in sys.argv:
    nebio.set_input_rates(750, 375, 375)
else:
    nebio.set_input_rates(1200, 400, 400)

if "--jitter" in sys.argv:
    nebio.set_scan_jitter(float(sys.argv[sys.argv.index("--jitter") + 1]))

if "--leds" in sys.argv:
    driver = nebio.LedDriver()
    for name in ("speed_pos", "speed_neg", "pitch_pos", "pitch_neg"):
        driver.set_rgb(name, 0, 4095, 0, 0.5)
    for name in ("record", "next", "source", "reset", "freeze"):
        driver.set_button_led(name, 0.5)
    driver.update()

def snapshots():
    last = time.time()
    while True:
        nebio.snapshot()  # waits for new ADC data, so ~400 passes per second
        if time.time() - last >= 10:  # scan/snapshot rates, to check the step
            last = time.time()
            log(nebio.stats())


if "--nosnap" in sys.argv:  # only nebio's input thread; its rates logged
    while True:
        time.sleep(10)
        log(nebio.stats())

if "--lock" not in sys.argv:
    snapshots()

# Locked: the audio chip's clock paces the writes. ALSA directly (not aplay
# through a pipe: a pipe lets the writer go on only when a whole 4096-byte
# page is read, so 16 blocks went at once and the triggers came in bursts,
# 282 scans/s, tested). The period is one block, so snd_pcm_writei returns
# once per audio interrupt, when the chip has taken one more block.
threading.Thread(target=snapshots, daemon=True).start()
asound = ctypes.CDLL("libasound.so.2")
pcm = ctypes.c_void_p()
hw = ctypes.c_void_p()
SND_PCM_STREAM_PLAYBACK, SND_PCM_ACCESS_RW_INTERLEAVED, SND_PCM_FORMAT_S16_LE = 0, 3, 2


def check(err, what):
    if err < 0:
        sys.exit("ALSA %s failed: %s" % (what, asound.snd_strerror(err)))


asound.snd_strerror.restype = ctypes.c_char_p
check(asound.snd_pcm_open(ctypes.byref(pcm), b"hw:0,0", SND_PCM_STREAM_PLAYBACK, 0), "open")
check(asound.snd_pcm_hw_params_malloc(ctypes.byref(hw)), "hw_params_malloc")
check(asound.snd_pcm_hw_params_any(pcm, hw), "hw_params_any")
check(asound.snd_pcm_hw_params_set_access(pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED), "access")
check(asound.snd_pcm_hw_params_set_format(pcm, hw, SND_PCM_FORMAT_S16_LE), "format")
check(asound.snd_pcm_hw_params_set_channels(pcm, hw, 2), "channels")
rate = ctypes.c_uint(48000)
check(asound.snd_pcm_hw_params_set_rate_near(pcm, hw, ctypes.byref(rate), None), "rate")
period = ctypes.c_ulong(LOCK_FRAMES)
check(asound.snd_pcm_hw_params_set_period_size_near(pcm, hw, ctypes.byref(period), None), "period")
bufsize = ctypes.c_ulong(LOCK_BUFFER)
check(asound.snd_pcm_hw_params_set_buffer_size_near(pcm, hw, ctypes.byref(bufsize)), "buffer")
check(asound.snd_pcm_hw_params(pcm, hw), "hw_params")
with open("/tmp/noise_test_load.log", "a") as f:
    f.write("lock: rate %d, period %d, buffer %d frames\n" % (rate.value, period.value, bufsize.value))

nebio.set_scan_trigger(True)
frames = period.value
block = ctypes.create_string_buffer(frames * 4)  # stereo, 16-bit zeros
asound.snd_pcm_writei.restype = ctypes.c_long
while True:
    n = asound.snd_pcm_writei(pcm, block, ctypes.c_ulong(frames))
    if n < 0:
        asound.snd_pcm_recover(pcm, int(n), 1)  # underrun: go on
        continue
    nebio.scan_trigger()
