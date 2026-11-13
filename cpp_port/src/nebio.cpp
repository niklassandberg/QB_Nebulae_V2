#include "nebio.h"

#include <cmath>

#include "classlogger.h"

namespace neb::nebio {

namespace {
Logger log_("Nebio");
bool inputsReady = false;
double lastSnapshot = 0.0;
int adc[16] = {};
int gpio[GPIO_PINS] = {};
std::map<std::string, Value> scLast;

int encoderIndex(const std::string &name) {
    if (name == "pitch") return 0;
    if (name == "speed") return 1;
    throw PyError("KeyError", name);
}

}  // namespace

NebioC &inputs() {
    if (!inputsReady) {
        if (nebioC().inputs_init() != 0)
            NLOG(log_, ERROR, "nebio inputs init failed: %s", last_error().c_str());
        inputsReady = true;
    }
    return nebioC();
}

long long snapshot() {
    NebioC &l = inputsReady ? nebioC() : inputs();
    long long n = l.snapshot();
    l.adc_codes(adc, 16);
    l.gpio_levels(gpio, GPIO_PINS);
    lastSnapshot = clock().time();
    return n;
}

int sr_bits() { return (inputsReady ? nebioC() : inputs()).sr_bits(); }

int gpio_level(int pin) {
    if (clock().time() - lastSnapshot > SNAPSHOT_MAX_AGE) snapshot();
    int level = (0 <= pin && pin < GPIO_PINS) ? gpio[pin] : -1;
    if (level < 0) {
        NLOG(log_, ERROR, "nebio: GPIO %d is not an input handled by nebio", pin);
        return 1;
    }
    return level;
}

int adc_code(int device, int channel) {
    if (!inputsReady) inputs();
    int k = device * 8 + channel;
    if (k < 0) k += 16;
    if (k < 0 || k >= 16) throw PyError("IndexError", "invalid index");
    return adc[k];
}

const int *adc_codes() {
    if (!inputsReady) inputs();
    return adc;
}

int encoder_id(int pin_a, int pin_b) { return inputs().encoder_id(pin_a, pin_b); }
int encoder_steps(int id) { return inputs().encoder_steps(id); }

void encoder_set_raw(const std::string &name, bool on) {
    NebioC &l = inputs();
    l.encoder_set_raw(encoderIndex(name), on ? 1 : 0);
}

bool encoder_raw(const std::string &name) {
    NebioC &l = inputs();
    return l.encoder_raw(encoderIndex(name)) != 0;
}

void encoder_set_click(const std::string &name, bool on) {
    NebioC &l = inputs();
    l.encoder_set_click(encoderIndex(name), on ? 1 : 0);
}

void set_eol(bool high) { inputs().set_eol(high ? 1 : 0); }

std::tuple<int, int, int> set_input_rates(const Value &scan, const Value &digital, const Value &adcHz) {
    int s = static_cast<int>(toInt(scan)), d = static_cast<int>(toInt(digital)), a = static_cast<int>(toInt(adcHz));
    if (nebioC().set_input_rates(s, d, a) != 0)
        NLOG(log_, ERROR, "nebio: %s", last_error().c_str());
    return input_rates();
}

std::tuple<int, int, int> input_rates() {
    NebioC &l = nebioC();
    int s = l.input_scan_hz();
    int d = l.input_digital_hz();
    int a = l.input_adc_hz();
    return {s, d, a};
}

void set_scan_jitter(double fraction) { nebioC().set_scan_jitter(fraction); }
void set_scan_trigger(bool external) { nebioC().set_scan_trigger(external ? 1 : 0); }
void scan_trigger() { nebioC().scan_trigger(); }

bool set_fast_gpio(bool on) {
    if (inputs().set_fast_gpio(on ? 1 : 0) != 0)
        NLOG(log_, ERROR, "nebio: %s", last_error().c_str());
    return fast_gpio();
}

bool fast_gpio() { return nebioC().fast_gpio() != 0; }

bool set_gate_interrupts(bool on, double holdoff_ms) {
    NebioC &l = inputs();
    l.set_gate_holdoff_us(static_cast<int>(pyRound0(holdoff_ms * 1000)));
    if (l.set_gate_interrupts(on ? 1 : 0) != 0)
        NLOG(log_, ERROR, "nebio: %s", last_error().c_str());
    return l.gate_interrupts() != 0;
}

std::string stats() { return nebioC().stats(); }
void led_clear_sc() { nebioC().led_clear_sc(); }
void sc_send_path_float(const std::string &path, double value) { nebioC().sc_send_path_float(path, value); }

bool osc_open(int port) {
    if (nebioC().osc_open(port) != 0) {
        NLOG(log_, ERROR, "nebio: %s", last_error().c_str());
        return false;
    }
    return true;
}

void osc_close() { nebioC().osc_close(); }
void osc_send(const std::string &path, double value) { nebioC().osc_send_float(path, value); }
int card_clip_count() { return nebioC().card_clip_count(); }
void sc_forget_sent() { scLast.clear(); }

void sc_send(const std::string &name, const Value &value) {
    auto it = scLast.find(name);
    if (it != scLast.end() && it->second == value) return;
    scLast[name] = value;
    NebioC &l = nebioC();
    switch (value.type) {
    case Value::Float: l.sc_send_float(name, value.f); break;
    case Value::Int: l.sc_send_int(name, static_cast<int>(value.i)); break;
    case Value::Bool: l.sc_send_bool(name, value.b ? 1 : 0); break;
    default: l.sc_send_string(name, pyStr(value)); break;
    }
}

std::string last_error() { return nebioC().last_error(); }

void resetForTests() {
    inputsReady = false;
    lastSnapshot = 0.0;
    for (int &v : adc) v = 0;
    for (int &v : gpio) v = 0;
    scLast.clear();
}

}  // namespace neb::nebio
