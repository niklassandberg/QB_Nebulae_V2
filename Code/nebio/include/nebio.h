/*
 * nebio - hardware and communication layer for QB Nebulae V2.
 *
 * Loaded into the Python process (nebulae.py) with ctypes. Owns:
 *   - inputs:  CD4021 shift register, gate/click GPIOs, encoders, 2x MCP3208
 *   - outputs: PCA9685 LEDs, reset LED (GPIO 12), end-of-loop out (GPIO 16)
 *   - comms:   OSC to/from sclang (UDP 3010/3011), text to Pure Data (TCP 3000)
 *
 * Threads inside the library never call into Python. Python asks.
 * All functions are safe to call from any Python thread.
 */
#ifndef NEBIO_H
#define NEBIO_H

#ifdef __cplusplus
extern "C" {
#endif

#define NEBIO_API __attribute__((visibility("default")))

/* ---- lifetime ---------------------------------------------------------- */

/* Opens GPIO/SPI and starts the input thread. Idempotent. 0 = ok. */
NEBIO_API int nebio_inputs_init(void);
/* Opens I2C/PCA9685 + reset LED and starts the LED threads. Idempotent. */
NEBIO_API int nebio_leds_init(void);
/* Stops all threads and releases hardware. Safe to call more than once. */
NEBIO_API void nebio_shutdown(void);
/* Text of the last error (static buffer, valid until the next error). */
NEBIO_API const char *nebio_last_error(void);

/* ---- inputs ------------------------------------------------------------ */

/* Freezes one consistent picture of all inputs. Waits (max ~10 ms) for a
 * fresh ADC scan so every call sees new hardware data. Short presses and
 * gate pulses that happened between two snapshots are stretched so they are
 * visible for at least one snapshot. Returns the snapshot number, -1 on error. */
NEBIO_API long long nebio_snapshot(void);
/* Shift register bits (bit i = CD4021 input i) from the last snapshot. */
NEBIO_API int nebio_sr_bits(void);
/* Raw level (0/1) of a BCM pin from the last snapshot, -1 if not an input. */
NEBIO_API int nebio_gpio_level(int bcm_pin);
/* 12-bit code of an MCP3208 channel from the last snapshot.
 * device 0 = CV (spidev0.0), device 1 = POT (spidev0.1). */
NEBIO_API int nebio_adc_code(int device, int channel);
/* All 16 codes of the last snapshot in one call: out[device * 8 + channel].
 * Copies min(n, 16) codes, returns how many. */
NEBIO_API int nebio_adc_codes(int *out, int n);
/* Encoder id for a (pin_a, pin_b) pair as given to encoder.Worker, -1 if unknown. */
NEBIO_API int nebio_encoder_id(int pin_a, int pin_b);
/* Steps since the last call (then reset to 0). Always 0 while the encoder is raw. */
NEBIO_API int nebio_encoder_steps(int id);
/* Raw encoder (rawencoder in a .scd), id from nebio_encoder_id (0 = pitch,
 * 1 = speed). On: the input thread sends the steps as "/neb/enc/<name> i" and
 * the click edges as "/neb/enc/<name>/click i" (1 pressed, 0 released)
 * straight to sclang, and sclang owns the encoder's two RGB LEDs
 * ("/sc/led/<name>_pos|_neg r g b"). Off: steps go back to
 * nebio_encoder_steps() and the LEDs back to Python; a click held at that
 * moment gets its release sent. */
NEBIO_API void nebio_encoder_set_raw(int id, int on);
NEBIO_API int  nebio_encoder_raw(int id);
/* Click only: the click edges go to sclang ("/neb/enc/<name>/click i") as for
 * a raw encoder, the steps and LEDs stay with Python. For hybrid encoders in a
 * SuperCollider patch. A raw encoder always sends its click. */
NEBIO_API void nebio_encoder_set_click(int id, int on);
/* End-of-loop gate output (GPIO 16). */
NEBIO_API void nebio_set_eol(int high);
/* Input thread rates, can be changed at any time (takes effect on the next
 * scan). scan_hz 100-2000 (default 1000): the encoders are read every scan.
 * digital_hz 1..scan_hz (default 1000): shift register, encoder clicks and
 * polled gates. adc_hz 1..scan_hz (default 500): both MCP3208; it is also the
 * maximum snapshot (updateAll) rate. digital_hz and adc_hz are rounded to
 * every nth scan. Button debounce stays 8 ms. Returns 0, or -1 for invalid
 * values (rates unchanged). */
NEBIO_API int nebio_set_input_rates(int scan_hz, int digital_hz, int adc_hz);
/* Rates in use (after rounding). */
NEBIO_API int nebio_input_scan_hz(void);
NEBIO_API int nebio_input_digital_hz(void);
NEBIO_API int nebio_input_adc_hz(void);
/* Fast GPIO: shift register and polled pins read through /dev/gpiomem (no
 * syscall per access) instead of libgpiod. Pi 1-4 only. Switching on checks
 * the board and pin functions and runs a self-check; on any problem it stays
 * on libgpiod and returns -1 (see nebio_last_error). Off by default.
 * Requires nebio_inputs_init() first. Returns 0 when the requested state is in use. */
NEBIO_API int nebio_set_fast_gpio(int on);
NEBIO_API int nebio_fast_gpio(void);

/* ---- LEDs -------------------------------------------------------------- */

/* Button LED ids */
#define NEBIO_LED_RECORD 0
#define NEBIO_LED_NEXT   1
#define NEBIO_LED_SOURCE 2
#define NEBIO_LED_FREEZE 3
#define NEBIO_LED_RESET  4
/* RGB LED ids */
#define NEBIO_RGB_PITCH_POS 0
#define NEBIO_RGB_PITCH_NEG 1
#define NEBIO_RGB_SPEED_POS 2
#define NEBIO_RGB_SPEED_NEG 3

/* Staged until nebio_led_commit(), except the reset LED which is immediate
 * (as the old GPIO PWM implementation was). */
NEBIO_API void nebio_led_set_button(int id, double brightness);
NEBIO_API void nebio_led_set_rgb(int id, double r, double g, double b, double brightness);
/* Makes staged LED values visible. Writes happen in the LED thread. */
NEBIO_API void nebio_led_commit(void);

/* Boot/loading animations (same look as bootleds.py), drawn on top of the
 * normal LED state until stopped. color: "booting", "loading", "loadingusb",
 * "updating", "error", "calibration", "wifi". behavior: "cycle", "pulse", "rainbow". */
NEBIO_API void nebio_led_animation(const char *color, const char *behavior);
NEBIO_API void nebio_led_animation_stop(void);
/* Forgets the colours sclang sent for the encoder LEDs (new patch). */
NEBIO_API void nebio_led_clear_sc(void);

/* ---- SuperCollider (OSC) ----------------------------------------------- */

NEBIO_API int  nebio_sc_open_sender(void);      /* to 127.0.0.1:3010 */
NEBIO_API void nebio_sc_close_sender(void);
NEBIO_API int  nebio_sc_sender_open(void);
NEBIO_API int  nebio_sc_start_listener(void);   /* on :3011 */
NEBIO_API void nebio_sc_stop_listener(void);
NEBIO_API int  nebio_sc_listener_running(void);

/* "/neb/<name> value", only sent when the value changed (as scsender did). */
NEBIO_API void nebio_sc_send_int(const char *name, int value);
NEBIO_API void nebio_sc_send_float(const char *name, double value);
NEBIO_API void nebio_sc_send_bool(const char *name, int value);
NEBIO_API void nebio_sc_send_string(const char *name, const char *value);
/* Sends to a full OSC path without the change check. */
NEBIO_API void nebio_sc_send_path_int(const char *path, int value);
/* Forgets the last sent values, so everything is sent again. */
NEBIO_API void nebio_sc_clear_cache(void);

/* Set by "/sc/up" from sclang. */
NEBIO_API int  nebio_sc_synth_is_up(void);
NEBIO_API void nebio_sc_set_synth_down(void);   /* also clears the cache */
/* Set by "/neb/ready" from sclang. */
NEBIO_API int  nebio_sc_handshake(void);
NEBIO_API void nebio_sc_zero_handshake(void);

/* ---- Pure Data (TCP text) ---------------------------------------------- */

/* Starts connecting in the background (retries until connected or closed). */
NEBIO_API void nebio_pd_connect(void);
NEBIO_API void nebio_pd_close(void);
NEBIO_API int  nebio_pd_is_connected(void);
/* Sends raw bytes ("name value;name value;"). Never blocks. 0 = sent. */
NEBIO_API int  nebio_pd_send(const char *data, int len);

/* ---- diagnostics ------------------------------------------------------- */

/* One line with scan rate, snapshot rate and worst scan time. */
NEBIO_API const char *nebio_stats(void);

#ifdef __cplusplus
}
#endif

#endif
