# nebio.py
# Python side of the nebio C++ library (Code/nebio). Everything that touches
# hardware (buttons, gates, knobs, encoders, LEDs) or talks to SuperCollider/PD
# goes through here. The library runs its own threads; Python only asks.

import atexit
import ctypes
import numbers
import os
import time

from classlogger import ClassLogger

_here = os.path.dirname(os.path.abspath(__file__))
_lib_path = os.environ.get(
    "NEBIO_LIB", os.path.join(_here, "..", "nebio", "build", "libnebio.so"))

class Nebio(object):
    pass


_log = ClassLogger.loggerSetup(Nebio())
_lib = None
_inputs_ready = False
_inputs_lib = None   # lib() once the inputs run: the per-loop calls skip inputs()
_leds_ready = False
_last_snapshot = 0.0
# ADC codes of the last snapshot, out[device * 8 + channel]: fetched in one
# call per snapshot instead of one call per adc_code().
_adc = (ctypes.c_int * 16)()
# Same for the GPIO levels, out[bcm_pin] (-1 = not an input handled by nebio).
_GPIO_PINS = 64
_gpio = (ctypes.c_int * _GPIO_PINS)()

# Python switch.Switch objects normally read the snapshot taken once per
# updateAll(). Scripts without a ControlHandler (check_wifi.py,
# check_calibration.py) never take one, so a stale snapshot is refreshed.
SNAPSHOT_MAX_AGE = 0.25

BUTTON_LEDS = {"record": 0, "next": 1, "source": 2, "freeze": 3, "reset": 4}
RGB_LEDS = {"pitch_pos": 0, "pitch_neg": 1, "speed_pos": 2, "speed_neg": 3}

ADC_CV = 0
ADC_POT = 1

# Encoder ids, as nebio_encoder_id() returns them for ui.py's pins.
ENCODERS = {"pitch": 0, "speed": 1}


def lib():
    global _lib
    if _lib is not None:
        return _lib
    l = ctypes.CDLL(os.path.normpath(_lib_path))
    c_int, c_double, c_char_p, c_ll = ctypes.c_int, ctypes.c_double, ctypes.c_char_p, ctypes.c_longlong
    sigs = {
        "nebio_inputs_init": (c_int, []),
        "nebio_leds_init": (c_int, []),
        "nebio_shutdown": (None, []),
        "nebio_last_error": (c_char_p, []),
        "nebio_snapshot": (c_ll, []),
        "nebio_sr_bits": (c_int, []),
        "nebio_gpio_level": (c_int, [c_int]),
        "nebio_adc_code": (c_int, [c_int, c_int]),
        "nebio_adc_codes": (c_int, [ctypes.POINTER(c_int), c_int]),
        "nebio_gpio_levels": (c_int, [ctypes.POINTER(c_int), c_int]),
        "nebio_encoder_id": (c_int, [c_int, c_int]),
        "nebio_encoder_steps": (c_int, [c_int]),
        "nebio_encoder_set_raw": (None, [c_int, c_int]),
        "nebio_encoder_raw": (c_int, [c_int]),
        "nebio_encoder_set_click": (None, [c_int, c_int]),
        "nebio_set_eol": (None, [c_int]),
        "nebio_set_input_rates": (c_int, [c_int, c_int, c_int]),
        "nebio_input_scan_hz": (c_int, []),
        "nebio_input_digital_hz": (c_int, []),
        "nebio_set_fast_gpio": (c_int, [c_int]),
        "nebio_fast_gpio": (c_int, []),
        "nebio_input_adc_hz": (c_int, []),
        "nebio_set_scan_jitter": (None, [c_double]),
        "nebio_set_scan_trigger": (None, [c_int]),
        "nebio_scan_trigger": (None, []),
        "nebio_led_set_button": (None, [c_int, c_double]),
        "nebio_led_set_rgb": (None, [c_int, c_double, c_double, c_double, c_double]),
        "nebio_led_commit": (None, []),
        "nebio_led_animation": (None, [c_char_p, c_char_p]),
        "nebio_led_animation_stop": (None, []),
        "nebio_led_clear_sc": (None, []),
        "nebio_led_set_dim": (None, [c_double]),
        "nebio_led_set_no_pwm": (None, [c_int]),
        "nebio_led_set_stagger": (None, [c_int]),
        "nebio_sc_open_sender": (c_int, []),
        "nebio_sc_close_sender": (None, []),
        "nebio_sc_sender_open": (c_int, []),
        "nebio_sc_start_listener": (c_int, []),
        "nebio_sc_stop_listener": (None, []),
        "nebio_sc_listener_running": (c_int, []),
        "nebio_sc_send_int": (None, [c_char_p, c_int]),
        "nebio_sc_send_float": (None, [c_char_p, c_double]),
        "nebio_sc_send_bool": (None, [c_char_p, c_int]),
        "nebio_sc_send_string": (None, [c_char_p, c_char_p]),
        "nebio_sc_send_path_int": (None, [c_char_p, c_int]),
        "nebio_sc_clear_cache": (None, []),
        "nebio_sc_synth_is_up": (c_int, []),
        "nebio_sc_set_synth_down": (None, []),
        "nebio_sc_handshake": (c_int, []),
        "nebio_sc_zero_handshake": (None, []),
        "nebio_sc_clip_count": (c_int, []),
        "nebio_pd_connect": (None, []),
        "nebio_pd_close": (None, []),
        "nebio_pd_is_connected": (c_int, []),
        "nebio_pd_send": (c_int, [c_char_p, c_int]),
        "nebio_stats": (c_char_p, []),
    }
    for name, (restype, argtypes) in sigs.items():
        fn = getattr(l, name)
        fn.restype = restype
        fn.argtypes = argtypes
    _lib = l
    atexit.register(shutdown)
    return _lib


def _b(text):
    return text.encode("utf-8") if isinstance(text, str) else text


def last_error():
    err = lib().nebio_last_error()
    return err.decode("utf-8", "replace") if err else ""


def shutdown():
    if _lib is not None:
        _lib.nebio_shutdown()


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def inputs():
    """Starts the input thread once (GPIO, shift register, ADCs, encoders)."""
    global _inputs_ready, _inputs_lib
    if not _inputs_ready:
        if lib().nebio_inputs_init() != 0:
            _log.error("nebio inputs init failed: %s", last_error())
        _inputs_ready = True
        _inputs_lib = lib()
    return lib()


def snapshot():
    """One consistent picture of all inputs. Called once per updateAll()."""
    global _last_snapshot
    l = _inputs_lib or inputs()
    n = l.nebio_snapshot()
    l.nebio_adc_codes(_adc, 16)
    l.nebio_gpio_levels(_gpio, _GPIO_PINS)
    _last_snapshot = time.time()
    return n


def sr_bits():
    return (_inputs_lib or inputs()).nebio_sr_bits()


def gpio_level(pin):
    if time.time() - _last_snapshot > SNAPSHOT_MAX_AGE:
        snapshot()
    level = _gpio[pin] if 0 <= pin < _GPIO_PINS else -1
    if level < 0:
        _log.error("nebio: GPIO %d is not an input handled by nebio", pin)
        return 1
    return level


def adc_code(device, channel):
    """12-bit code from the last snapshot (as nebio_adc_code)."""
    if not _inputs_ready:
        inputs()
    return _adc[device * 8 + channel]


def adc_codes():
    """The array snapshot() fills in place, out[device * 8 + channel]. A
    reference to it always holds the codes of the last snapshot (MCP3208
    reads it directly, one Python call less per ADC read)."""
    if not _inputs_ready:
        inputs()
    return _adc


def encoder_id(pin_a, pin_b):
    return inputs().nebio_encoder_id(pin_a, pin_b)


def encoder_steps(enc_id):
    return inputs().nebio_encoder_steps(enc_id)


def encoder_set_raw(name, on):
    """rawencoder: nebio sends the steps and clicks of encoder `name`
    ("speed"/"pitch") straight to sclang, and sclang drives its two LEDs.
    Off: back to Python (encoder_steps(), ui.py LEDs)."""
    inputs().nebio_encoder_set_raw(ENCODERS[name], 1 if on else 0)
    # nebio shows sclang's colours on those LEDs meanwhile: Python's last
    # values are no longer what is staged, so they must be sent again.
    _rgb_last.clear()


def encoder_raw(name):
    return bool(inputs().nebio_encoder_raw(ENCODERS[name]))


def encoder_set_click(name, on):
    """Click only: nebio sends the press/release of encoder `name` to sclang
    (/neb/enc/<name>/click 1/0), the steps and LEDs stay with Python.
    A raw encoder always sends its click."""
    inputs().nebio_encoder_set_click(ENCODERS[name], 1 if on else 0)


def set_eol(high):
    inputs().nebio_set_eol(1 if high else 0)


def set_input_rates(scan_hz, digital_hz, adc_hz):
    """Rates of the nebio input thread, changeable at any time.
    scan_hz (100-2000, default 1000): encoders, read every scan.
    digital_hz (1..scan_hz, default 1000): shift register (buttons, source
    gate), encoder clicks.
    adc_hz (1..scan_hz, default 500): knobs and CV; also the highest rate
    updateAll() can run at, since each snapshot waits for new ADC data.
    digital_hz and adc_hz are rounded to every nth scan.
    Returns the rates in use (scan_hz, digital_hz, adc_hz)."""
    if lib().nebio_set_input_rates(int(scan_hz), int(digital_hz), int(adc_hz)) != 0:
        _log.error("nebio: %s", last_error())
    return input_rates()


def set_scan_jitter(fraction):
    """Each scan interval varies randomly by up to +-fraction (0 = off, max
    0.9); the mean rate stays the same, so the scans' tone becomes noise."""
    lib().nebio_set_scan_jitter(float(fraction))


def set_scan_trigger(external):
    """True: one scan per scan_trigger() instead of the timer (locking)."""
    lib().nebio_set_scan_trigger(1 if external else 0)


def scan_trigger():
    lib().nebio_scan_trigger()


def input_rates():
    l = lib()
    return l.nebio_input_scan_hz(), l.nebio_input_digital_hz(), l.nebio_input_adc_hz()


def set_fast_gpio(on):
    """Shift register and encoder/click pins through /dev/gpiomem instead of
    libgpiod (no syscall per access). Pi 1-4 only. Switching on checks the
    board and pin functions and runs a self-check; if anything is wrong nebio
    stays on libgpiod. Call after the inputs are running. Returns True when
    fast GPIO is in use."""
    if inputs().nebio_set_fast_gpio(1 if on else 0) != 0:
        _log.error("nebio: %s", last_error())
    return fast_gpio()


def fast_gpio():
    return bool(lib().nebio_fast_gpio())


def stats():
    return lib().nebio_stats().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# LEDs
# ---------------------------------------------------------------------------

def leds():
    """Starts the LED threads once. Stops a running bootleds.py first so two
    processes never write to the LED driver at the same time."""
    global _leds_ready
    if not _leds_ready:
        os.system("pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py")
        time.sleep(0.05)
        if lib().nebio_leds_init() != 0:
            _log.error("nebio LED init failed: %s", last_error())
        _leds_ready = True
    return lib()


def led_animation(color, behavior="cycle"):
    """Boot/loading animation, same look as bootleds.py <color> <behavior>."""
    leds().nebio_led_animation(_b(color), _b(behavior))


def led_animation_stop():
    leds().nebio_led_animation_stop()


def led_clear_sc():
    """Forgets the encoder LED colours sclang sent (new patch). Does not
    start the LED threads (no bootleds.py kill)."""
    lib().nebio_led_clear_sc()


def led_set_dim(dim):
    """Dims every LED: 0 = off .. 1 = full (LED dim script, ui.py)."""
    leds().nebio_led_set_dim(float(dim))


def led_set_no_pwm(on):
    """Quiet mode: file and freeze LEDs only fully on/off (PWM heard in the audio)."""
    leds().nebio_led_set_no_pwm(1 if on else 0)


def led_set_stagger(on):
    """Quiet mode: LED channels start their PWM pulses at different times."""
    leds().nebio_led_set_stagger(1 if on else 0)


class Color(object):
    def __init__(self, r=4095, g=4095, b=4095):
        self.r = r
        self.g = g
        self.b = b

    def red(self):
        return self.r

    def green(self):
        return self.g

    def blue(self):
        return self.b


# Last values sent to nebio, so the per-loop calls with the same value are
# skipped. The RGB one is cleared by encoder_set_raw() (sclang's colours).
_button_last = {}
_rgb_last = {}


class LedDriver(object):
    """Same interface as leddriver.LedDriver. Values are staged and become
    visible on update(), which ui.py calls once per loop. Only values that
    changed reach nebio, and update() commits only when something was staged."""

    def __init__(self):
        self.lib = leds()
        self.staged = True   # commit once at start

    def update(self):
        if self.staged:
            self.staged = False
            self.lib.nebio_led_commit()

    def set_button_led(self, name, value):
        if name in BUTTON_LEDS and _button_last.get(name) != value:
            _button_last[name] = value
            self.staged = True
            self.lib.nebio_led_set_button(BUTTON_LEDS[name], value)

    def set_rgb(self, name, r, g, b, bright):
        if name in RGB_LEDS:
            v = (r, g, b, bright)
            if _rgb_last.get(name) != v:
                _rgb_last[name] = v
                self.staged = True
                self.lib.nebio_led_set_rgb(RGB_LEDS[name], r, g, b, bright)

    def cleanup(self):
        pass


# ---------------------------------------------------------------------------
# SuperCollider / Pure Data
# ---------------------------------------------------------------------------

def sc_clip_count():
    """Number of times sclang reported that the audio input clipped
    (/sc/clip). Only changes matter."""
    return lib().nebio_sc_clip_count()


# Last value sent per name: nebio skips unchanged values too, but checking
# here first saves the ctypes call. Same rule as nebio (==, 1 == 1.0).
# Cleared with nebio's cache (sc_forget_sent).
_sc_last = {}
_sc_names = {}


def sc_forget_sent():
    """Everything is sent again (with nebio_sc_clear_cache/set_synth_down)."""
    _sc_last.clear()


def sc_send(name, value):
    if name in _sc_last and _sc_last[name] == value:
        return
    _sc_last[name] = value
    bname = _sc_names.get(name)
    if bname is None:
        bname = _sc_names[name] = _b(name)
    l = lib()
    t = type(value)
    if t is float:
        l.nebio_sc_send_float(bname, value)
    elif t is int:
        l.nebio_sc_send_int(bname, value)
    elif t is bool:
        l.nebio_sc_send_bool(bname, 1 if value else 0)
    elif isinstance(value, numbers.Integral):   # e.g. numpy ints
        l.nebio_sc_send_int(bname, int(value))
    elif isinstance(value, numbers.Real):
        l.nebio_sc_send_float(bname, float(value))
    else:
        l.nebio_sc_send_string(bname, _b(str(value)))
