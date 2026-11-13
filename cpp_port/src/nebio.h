// nebio.py without the LED part (ui.py's): the inputs snapshot and the SC,
// OSC and gate settings over nebio's C functions (NebioC).
#pragma once

#include <map>
#include <string>
#include <tuple>

#include "nebio_api.h"
#include "pyvalue.h"

namespace neb::nebio {

constexpr int ADC_CV = 0;
constexpr int ADC_POT = 1;
constexpr double SNAPSHOT_MAX_AGE = 0.25;
constexpr int GPIO_PINS = 64;

NebioC &inputs();
long long snapshot();
int sr_bits();
int gpio_level(int pin);
int adc_code(int device, int channel);
const int *adc_codes();  // filled in place by every snapshot()
int encoder_id(int pin_a, int pin_b);
int encoder_steps(int id);
void encoder_set_raw(const std::string &name, bool on);  // PyError KeyError: unknown name
bool encoder_raw(const std::string &name);
void encoder_set_click(const std::string &name, bool on);
void set_eol(bool high);
std::tuple<int, int, int> set_input_rates(const Value &scan, const Value &digital, const Value &adc);
std::tuple<int, int, int> input_rates();
void set_scan_jitter(double fraction);
void set_scan_trigger(bool external);
void scan_trigger();
bool set_fast_gpio(bool on);
bool fast_gpio();
bool set_gate_interrupts(bool on, double holdoff_ms);
std::string stats();
void led_clear_sc();
void sc_send_path_float(const std::string &path, double value);
bool osc_open(int port);
void osc_close();
void osc_send(const std::string &path, double value);
int card_clip_count();
void sc_forget_sent();
void sc_send(const std::string &name, const Value &value);
std::string last_error();

void resetForTests();  // the module state as after import

}  // namespace neb::nebio
