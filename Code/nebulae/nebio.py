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
_leds_ready = False
_last_snapshot = 0.0

# Python switch.Switch objects normally read the snapshot taken once per
# updateAll(). Scripts without a ControlHandler (check_wifi.py,
# check_calibration.py) never take one, so a stale snapshot is refreshed.
SNAPSHOT_MAX_AGE = 0.25

BUTTON_LEDS = {"record": 0, "next": 1, "source": 2, "freeze": 3, "reset": 4}
RGB_LEDS = {"pitch_pos": 0, "pitch_neg": 1, "speed_pos": 2, "speed_neg": 3}

ADC_CV = 0
ADC_POT = 1


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
        "nebio_encoder_id": (c_int, [c_int, c_int]),
        "nebio_encoder_steps": (c_int, [c_int]),
        "nebio_set_eol": (None, [c_int]),
        "nebio_led_set_button": (None, [c_int, c_double]),
        "nebio_led_set_rgb": (None, [c_int, c_double, c_double, c_double, c_double]),
        "nebio_led_commit": (None, []),
        "nebio_led_animation": (None, [c_char_p, c_char_p]),
        "nebio_led_animation_stop": (None, []),
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
    global _inputs_ready
    if not _inputs_ready:
        if lib().nebio_inputs_init() != 0:
            _log.error("nebio inputs init failed: %s", last_error())
        _inputs_ready = True
    return lib()


def snapshot():
    """One consistent picture of all inputs. Called once per updateAll()."""
    global _last_snapshot
    n = inputs().nebio_snapshot()
    _last_snapshot = time.time()
    return n


def sr_bits():
    return inputs().nebio_sr_bits()


def gpio_level(pin):
    if time.time() - _last_snapshot > SNAPSHOT_MAX_AGE:
        snapshot()
    level = inputs().nebio_gpio_level(pin)
    if level < 0:
        _log.error("nebio: GPIO %d is not an input handled by nebio", pin)
        return 1
    return level


def adc_code(device, channel):
    return inputs().nebio_adc_code(device, channel)


def encoder_id(pin_a, pin_b):
    return inputs().nebio_encoder_id(pin_a, pin_b)


def encoder_steps(enc_id):
    return inputs().nebio_encoder_steps(enc_id)


def set_eol(high):
    inputs().nebio_set_eol(1 if high else 0)


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
        os.system("sudo pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py")
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


class LedDriver(object):
    """Same interface as leddriver.LedDriver. Values are staged and become
    visible on update(), which ui.py calls once per loop."""

    def __init__(self):
        self.lib = leds()

    def update(self):
        self.lib.nebio_led_commit()

    def set_button_led(self, name, value):
        if name in BUTTON_LEDS:
            self.lib.nebio_led_set_button(BUTTON_LEDS[name], value)

    def set_rgb(self, name, r, g, b, bright):
        if name in RGB_LEDS:
            self.lib.nebio_led_set_rgb(RGB_LEDS[name], r, g, b, bright)

    def cleanup(self):
        pass


# ---------------------------------------------------------------------------
# SuperCollider / Pure Data
# ---------------------------------------------------------------------------

def sc_send(name, value):
    l = lib()
    if isinstance(value, bool):
        l.nebio_sc_send_bool(_b(name), 1 if value else 0)
    elif isinstance(value, numbers.Integral):
        l.nebio_sc_send_int(_b(name), int(value))
    elif isinstance(value, numbers.Real):
        l.nebio_sc_send_float(_b(name), float(value))
    else:
        l.nebio_sc_send_string(_b(name), _b(str(value)))
