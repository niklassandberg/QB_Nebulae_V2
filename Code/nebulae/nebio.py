# Python side of the nebio C++ library (Code/nebio): hardware and OSC.

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
_inputs_lib = None
_leds_ready = False
_last_snapshot = 0.0
_adc = (ctypes.c_int * 16)()  # [device * 8 + channel]
_GPIO_PINS = 64
_gpio = (ctypes.c_int * _GPIO_PINS)()  # [bcm_pin], -1 = not a nebio input

# Scripts without a ControlHandler never take a snapshot themselves.
SNAPSHOT_MAX_AGE = 0.25

BUTTON_LEDS = {"record": 0, "next": 1, "source": 2, "freeze": 3, "reset": 4}
RGB_LEDS = {"pitch_pos": 0, "pitch_neg": 1, "speed_pos": 2, "speed_neg": 3}

ADC_CV = 0
ADC_POT = 1

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
        "nebio_set_gate_interrupts": (c_int, [c_int]),
        "nebio_gate_interrupts": (c_int, []),
        "nebio_set_gate_holdoff_us": (None, [c_int]),
        "nebio_gate_holdoff_us": (c_int, []),
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
        "nebio_sc_send_path_float": (None, [c_char_p, c_double]),
        "nebio_sc_clear_cache": (None, []),
        "nebio_sc_synth_is_up": (c_int, []),
        "nebio_sc_set_synth_down": (None, []),
        "nebio_sc_handshake": (c_int, []),
        "nebio_sc_zero_handshake": (None, []),
        "nebio_card_clip_count": (c_int, []),
        "nebio_osc_open": (c_int, [c_int]),
        "nebio_osc_close": (None, []),
        "nebio_osc_send_float": (None, [c_char_p, c_double]),
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


def inputs():
    global _inputs_ready, _inputs_lib
    if not _inputs_ready:
        if lib().nebio_inputs_init() != 0:
            _log.error("nebio inputs init failed: %s", last_error())
        _inputs_ready = True
        _inputs_lib = lib()
    return lib()


def snapshot():
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
    if not _inputs_ready:
        inputs()
    return _adc[device * 8 + channel]


# Filled in place by snapshot(): a reference stays current.
def adc_codes():
    if not _inputs_ready:
        inputs()
    return _adc


def encoder_id(pin_a, pin_b):
    return inputs().nebio_encoder_id(pin_a, pin_b)


def encoder_steps(enc_id):
    return inputs().nebio_encoder_steps(enc_id)


# On: steps, clicks and the two LEDs belong to sclang.
def encoder_set_raw(name, on):
    inputs().nebio_encoder_set_raw(ENCODERS[name], 1 if on else 0)
    _rgb_last.clear()  # nebio showed sclang's colours meanwhile


def encoder_raw(name):
    return bool(inputs().nebio_encoder_raw(ENCODERS[name]))


# The click only goes to sclang (/neb/enc/<name>/click).
def encoder_set_click(name, on):
    inputs().nebio_encoder_set_click(ENCODERS[name], 1 if on else 0)


def set_eol(high):
    inputs().nebio_set_eol(1 if high else 0)


# scan_hz: encoders. digital_hz: buttons and clicks. adc_hz: knobs and CV,
# also the highest updateAll() rate. Both rounded to every nth scan.
def set_input_rates(scan_hz, digital_hz, adc_hz):
    if lib().nebio_set_input_rates(int(scan_hz), int(digital_hz), int(adc_hz)) != 0:
        _log.error("nebio: %s", last_error())
    return input_rates()


# Random scan intervals: the scans' tone becomes noise.
def set_scan_jitter(fraction):
    lib().nebio_set_scan_jitter(float(fraction))


def set_scan_trigger(external):
    lib().nebio_set_scan_trigger(1 if external else 0)


def scan_trigger():
    lib().nebio_scan_trigger()


def input_rates():
    l = lib()
    return l.nebio_input_scan_hz(), l.nebio_input_digital_hz(), l.nebio_input_adc_hz()


# /dev/gpiomem instead of libgpiod, Pi 1-4 only. Returns whether it is used.
def set_fast_gpio(on):
    if inputs().nebio_set_fast_gpio(1 if on else 0) != 0:
        _log.error("nebio: %s", last_error())
    return fast_gpio()


def fast_gpio():
    return bool(lib().nebio_fast_gpio())


# Gate inputs: interrupts (lowest latency) or polled with a Schmitt trigger
# hold-off (no CPU load from slow or noisy gates). Returns whether interrupts
# are used.
def set_gate_interrupts(on, holdoff_ms):
    l = inputs()
    l.nebio_set_gate_holdoff_us(int(round(holdoff_ms * 1000)))
    if l.nebio_set_gate_interrupts(1 if on else 0) != 0:
        _log.error("nebio: %s", last_error())
    return bool(l.nebio_gate_interrupts())


def stats():
    return lib().nebio_stats().decode("utf-8", "replace")


def leds():
    global _leds_ready
    if not _leds_ready:
        os.system("pkill -1 -f /home/alarm/QB_Nebulae_V2/Code/nebulae/bootleds.py")
        time.sleep(0.05)
        if lib().nebio_leds_init() != 0:
            _log.error("nebio LED init failed: %s", last_error())
        _leds_ready = True
    return lib()


def led_animation(color, behavior="cycle"):
    leds().nebio_led_animation(_b(color), _b(behavior))


def led_animation_stop():
    leds().nebio_led_animation_stop()


def led_clear_sc():
    lib().nebio_led_clear_sc()


def led_set_dim(dim):
    leds().nebio_led_set_dim(float(dim))


def led_set_no_pwm(on):
    leds().nebio_led_set_no_pwm(1 if on else 0)


def led_set_stagger(on):
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


_button_last = {}
_rgb_last = {}


# Staged values become visible on update().
class LedDriver(object):

    def __init__(self):
        self.lib = leds()
        self.staged = True

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


_osc_paths = {}


def sc_send_path_float(path, value):
    bpath = _osc_paths.get(path)
    if bpath is None:
        bpath = _osc_paths[path] = _b(path)
    lib().nebio_sc_send_path_float(bpath, float(value))


def osc_open(port):
    if lib().nebio_osc_open(int(port)) != 0:
        _log.error("nebio: %s", last_error())
        return False
    return True


def osc_close():
    lib().nebio_osc_close()


def osc_send(path, value):
    bpath = _osc_paths.get(path)
    if bpath is None:
        bpath = _osc_paths[path] = _b(path)
    lib().nebio_osc_send_float(bpath, float(value))


# -1: the card driver has no counter.
def card_clip_count():
    return lib().nebio_card_clip_count()


# Checked here too: saves the ctypes call.
_sc_last = {}
_sc_names = {}


def sc_forget_sent():
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
    elif isinstance(value, numbers.Integral):
        l.nebio_sc_send_int(bname, int(value))
    elif isinstance(value, numbers.Real):
        l.nebio_sc_send_float(bname, float(value))
    else:
        l.nebio_sc_send_string(bname, _b(str(value)))
