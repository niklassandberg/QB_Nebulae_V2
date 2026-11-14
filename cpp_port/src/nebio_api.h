// What the port needs from outside: nebio's C functions (Code/nebio/include/
// nebio.h), Csound's channels, the clock and random numbers. Production code
// passes the real ones (nebio_c_real.cpp); tests pass fakes.
#pragma once

#include <string>
#include <vector>

#include "pyvalue.h"

namespace neb {

class NebioC {
public:
    virtual ~NebioC() = default;
    virtual int inputs_init() = 0;
    virtual std::string last_error() = 0;
    virtual long long snapshot() = 0;
    virtual int sr_bits() = 0;
    virtual int adc_codes(int *out, int n) = 0;
    virtual int gpio_levels(int *out, int n) = 0;
    virtual int encoder_id(int pin_a, int pin_b) = 0;
    virtual int encoder_steps(int id) = 0;
    virtual void encoder_set_raw(int id, int on) = 0;
    virtual int encoder_raw(int id) = 0;
    virtual void encoder_set_click(int id, int on) = 0;
    virtual void set_eol(int high) = 0;
    virtual int set_input_rates(int scan, int digital, int adc) = 0;
    virtual int input_scan_hz() = 0;
    virtual int input_digital_hz() = 0;
    virtual int input_adc_hz() = 0;
    virtual void set_scan_jitter(double fraction) = 0;
    virtual void set_scan_trigger(int external) = 0;
    virtual void scan_trigger() = 0;
    virtual int set_fast_gpio(int on) = 0;
    virtual int fast_gpio() = 0;
    virtual int set_gate_interrupts(int on) = 0;
    virtual int gate_interrupts() = 0;
    virtual void set_gate_holdoff_us(int us) = 0;
    virtual std::string stats() = 0;
    virtual void led_clear_sc() = 0;
    virtual void shutdown() = 0;
    virtual int sc_open_sender() = 0;
    virtual void sc_close_sender() = 0;
    virtual int sc_sender_open() = 0;
    virtual int sc_start_listener() = 0;
    virtual void sc_stop_listener() = 0;
    virtual int sc_listener_running() = 0;
    virtual void sc_send_int(const std::string &name, int value) = 0;
    virtual void sc_send_float(const std::string &name, double value) = 0;
    virtual void sc_send_bool(const std::string &name, int value) = 0;
    virtual void sc_send_string(const std::string &name, const std::string &value) = 0;
    virtual void sc_send_path_int(const std::string &path, int value) = 0;
    virtual void sc_send_path_float(const std::string &path, double value) = 0;
    virtual void sc_clear_cache() = 0;
    virtual int sc_synth_is_up() = 0;
    virtual void sc_set_synth_down() = 0;
    virtual int sc_handshake() = 0;
    virtual void sc_zero_handshake() = 0;
    virtual int card_clip_count() = 0;
    virtual int osc_open(int port) = 0;
    virtual void osc_close() = 0;
    virtual void osc_send_float(const std::string &path, double value) = 0;
};

// time.time() and time.sleep().
class Clock {
public:
    virtual ~Clock() = default;
    virtual double time() = 0;
    virtual void sleep(double seconds) = 0;
};

// random.randint(a, b).
class Random {
public:
    virtual ~Random() = default;
    virtual int randint(int a, int b) = 0;
};

// Csound's control channels (ctcsound channelPtr / setControlChannel) and
// function tables (table).
class Csound {
public:
    virtual ~Csound() = default;
    virtual double *channelPtr(const std::string &name, int flags) = 0;
    virtual void setControlChannel(const std::string &name, const Value &value) = 0;
    virtual std::vector<double> table(int number) = 0;
};

constexpr int CSOUND_CONTROL_CHANNEL = 1;
constexpr int CSOUND_INPUT_CHANNEL = 16;
constexpr int CSOUND_OUTPUT_CHANNEL = 32;

// The process-wide ones, as the Python modules share theirs.
NebioC &nebioC();
Clock &clock();
Random &random();
void setNebioC(NebioC *c);
void setClock(Clock *c);
void setRandom(Random *r);

}  // namespace neb
