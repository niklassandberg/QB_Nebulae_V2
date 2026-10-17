// nebio.cpp - the C API that Python loads with ctypes.
#include "nebio.h"

#include <mutex>
#include <string>

#include "inputs.h"
#include "leds.h"
#include "links.h"
#include "log.h"

namespace nebio {

namespace {
std::mutex errorMutex;
char errorText[512] = "";
}  // namespace

void setLastError(const std::string &msg) {
    std::lock_guard<std::mutex> lock(errorMutex);
    std::snprintf(errorText, sizeof(errorText), "%s", msg.c_str());
}

const char *lastError() { return errorText; }

}  // namespace nebio

using nebio::Inputs;
using nebio::Leds;
using nebio::PdLink;
using nebio::ScLink;

extern "C" {

// ---- lifetime --------------------------------------------------------------

int nebio_inputs_init(void) { return Inputs::instance().init(); }
int nebio_leds_init(void) { return Leds::instance().init(); }

void nebio_shutdown(void) {
    PdLink::instance().close();
    ScLink::instance().stopListener();
    ScLink::instance().closeSender();
    Leds::instance().shutdown();
    Inputs::instance().shutdown();
}

const char *nebio_last_error(void) { return nebio::lastError(); }

// ---- inputs ----------------------------------------------------------------

long long nebio_snapshot(void) { return Inputs::instance().snapshot(); }
int nebio_sr_bits(void) { return Inputs::instance().srBits(); }
int nebio_gpio_level(int bcm_pin) { return Inputs::instance().gpioLevel(bcm_pin); }
int nebio_adc_code(int device, int channel) { return Inputs::instance().adcCode(device, channel); }
int nebio_encoder_id(int pin_a, int pin_b) { return Inputs::instance().encoderId(pin_a, pin_b); }
int nebio_encoder_steps(int id) { return Inputs::instance().encoderSteps(id); }
void nebio_set_eol(int high) { Inputs::instance().setEol(high); }
int nebio_set_input_rates(int scan_hz, int digital_hz, int adc_hz) {
    return Inputs::instance().setRates(scan_hz, digital_hz, adc_hz);
}
int nebio_input_scan_hz(void) { return Inputs::instance().scanHz(); }
int nebio_input_digital_hz(void) { return Inputs::instance().digitalHz(); }
int nebio_set_fast_gpio(int on) { return Inputs::instance().setFastGpio(on != 0); }
int nebio_fast_gpio(void) { return Inputs::instance().fastGpio() ? 1 : 0; }
int nebio_input_adc_hz(void) { return Inputs::instance().adcHz(); }

// ---- LEDs ------------------------------------------------------------------

void nebio_led_set_button(int id, double brightness) { Leds::instance().setButton(id, brightness); }
void nebio_led_set_rgb(int id, double r, double g, double b, double brightness) {
    Leds::instance().setRgb(id, r, g, b, brightness);
}
void nebio_led_commit(void) { Leds::instance().commit(); }
void nebio_led_animation(const char *color, const char *behavior) {
    Leds::instance().animation(color ? color : "", behavior ? behavior : "");
}
void nebio_led_animation_stop(void) { Leds::instance().animationStop(); }

// ---- SuperCollider ---------------------------------------------------------

int nebio_sc_open_sender(void) { return ScLink::instance().openSender() ? 0 : -1; }
void nebio_sc_close_sender(void) { ScLink::instance().closeSender(); }
int nebio_sc_sender_open(void) { return ScLink::instance().senderOpen(); }
int nebio_sc_start_listener(void) { return ScLink::instance().startListener() ? 0 : -1; }
void nebio_sc_stop_listener(void) { ScLink::instance().stopListener(); }
int nebio_sc_listener_running(void) { return ScLink::instance().listenerRunning(); }

void nebio_sc_send_int(const char *name, int value) { ScLink::instance().sendInt(name, value); }
void nebio_sc_send_float(const char *name, double value) { ScLink::instance().sendFloat(name, value); }
void nebio_sc_send_bool(const char *name, int value) { ScLink::instance().sendBool(name, value != 0); }
void nebio_sc_send_string(const char *name, const char *value) {
    ScLink::instance().sendString(name, value);
}
void nebio_sc_send_path_int(const char *path, int value) { ScLink::instance().sendPathInt(path, value); }
void nebio_sc_clear_cache(void) { ScLink::instance().clearCache(); }

int nebio_sc_synth_is_up(void) { return ScLink::instance().synthIsUp; }
void nebio_sc_set_synth_down(void) {
    ScLink::instance().clearCache();
    ScLink::instance().synthIsUp = false;
}
int nebio_sc_handshake(void) { return ScLink::instance().handshake; }
void nebio_sc_zero_handshake(void) { ScLink::instance().handshake = false; }

// ---- Pure Data -------------------------------------------------------------

void nebio_pd_connect(void) { PdLink::instance().connect(); }
void nebio_pd_close(void) { PdLink::instance().close(); }
int nebio_pd_is_connected(void) { return PdLink::instance().connected(); }
int nebio_pd_send(const char *data, int len) { return PdLink::instance().send(data, len) ? 0 : -1; }

// ---- diagnostics -----------------------------------------------------------

const char *nebio_stats(void) {
    static char buf[160];
    Inputs::instance().stats(buf, sizeof(buf));
    return buf;
}

}  // extern "C"
