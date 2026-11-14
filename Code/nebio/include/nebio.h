/*
 * nebio - hardware and communication layer for QB Nebulae V2, loaded by
 * Python with ctypes. Its threads never call into Python. All functions are
 * thread-safe.
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

/* One consistent picture of all inputs. Waits (max ~10 ms) for a fresh ADC
 * scan; presses shorter than a snapshot are stretched. Returns the snapshot
 * number, -1 on error. */
NEBIO_API long long nebio_snapshot(void);
/* Shift register bits (bit i = CD4021 input i) from the last snapshot. */
NEBIO_API int nebio_sr_bits(void);
/* Raw level (0/1) of a BCM pin from the last snapshot, -1 if not an input. */
NEBIO_API int nebio_gpio_level(int bcm_pin);
/* device 0 = CV, 1 = POT. */
NEBIO_API int nebio_adc_code(int device, int channel);
/* out[device * 8 + channel]; returns how many were copied. */
NEBIO_API int nebio_adc_codes(int *out, int n);
/* out[pin] as nebio_gpio_level, n <= 64. */
NEBIO_API int nebio_gpio_levels(int *out, int n);
/* -1 if unknown. */
NEBIO_API int nebio_encoder_id(int pin_a, int pin_b);
/* Steps since the last call (then reset to 0). Always 0 while the encoder is raw. */
NEBIO_API int nebio_encoder_steps(int id);
/* rawencoder. On: steps ("/neb/enc/<name> i") and clicks
 * ("/neb/enc/<name>/click i") go to sclang, which owns the encoder's LEDs
 * ("/sc/led/<name>_pos|_neg r g b"). Off: a held click gets its release. */
NEBIO_API void nebio_encoder_set_raw(int id, int on);
NEBIO_API int  nebio_encoder_raw(int id);
/* Only the clicks go to sclang (hybrid encoders in a patch). */
NEBIO_API void nebio_encoder_set_click(int id, int on);
/* End-of-loop gate output (GPIO 16). */
NEBIO_API void nebio_set_eol(int high);
/* scan_hz 100-2000: encoders. digital_hz: buttons, clicks, gates. adc_hz:
 * MCP3208, also the maximum snapshot rate. Both 1..scan_hz, rounded to every
 * nth scan. -1 for invalid values. */
NEBIO_API int nebio_set_input_rates(int scan_hz, int digital_hz, int adc_hz);
NEBIO_API int nebio_input_scan_hz(void);
NEBIO_API int nebio_input_digital_hz(void);
NEBIO_API int nebio_input_adc_hz(void);
/* Against the scans' tone in the audio. Jitter: +-fraction per interval (max
 * 0.9). Trigger: one scan per nebio_scan_trigger() instead of the timer. */
NEBIO_API void nebio_set_scan_jitter(double fraction);
NEBIO_API void nebio_set_scan_trigger(int external);
NEBIO_API void nebio_scan_trigger(void);
/* /dev/gpiomem instead of libgpiod, Pi 1-4 only. -1: the self-check failed
 * and libgpiod stays. After nebio_inputs_init(). */
NEBIO_API int nebio_set_fast_gpio(int on);
NEBIO_API int nebio_fast_gpio(void);
/* Gate inputs (Nebulae sets it from configsettings, default off). On (the
 * library's default until set): edge events, each edge a kernel interrupt, the
 * lowest latency; a slow or noisy gate gives hundreds per edge. Off: read on
 * every scan with no interrupts, as a Schmitt trigger: a change counts at
 * once, then the pin is ignored for the hold-off (0-100000 us, default 5000).
 * -1 when the system has no edge events (the gates are always polled). */
NEBIO_API int nebio_set_gate_interrupts(int on);
NEBIO_API int nebio_gate_interrupts(void);
NEBIO_API void nebio_set_gate_holdoff_us(int us);
NEBIO_API int nebio_gate_holdoff_us(void);

/* ---- LEDs -------------------------------------------------------------- */

#define NEBIO_LED_RECORD 0
#define NEBIO_LED_NEXT   1
#define NEBIO_LED_SOURCE 2
#define NEBIO_LED_FREEZE 3
#define NEBIO_LED_RESET  4
#define NEBIO_RGB_PITCH_POS 0
#define NEBIO_RGB_PITCH_NEG 1
#define NEBIO_RGB_SPEED_POS 2
#define NEBIO_RGB_SPEED_NEG 3

/* Staged until nebio_led_commit(); the reset LED is immediate. */
NEBIO_API void nebio_led_set_button(int id, double brightness);
NEBIO_API void nebio_led_set_rgb(int id, double r, double g, double b, double brightness);
NEBIO_API void nebio_led_commit(void);

/* Drawn over everything until stopped. color: "booting", "loading",
 * "loadingusb", "updating", "error", "calibration", "wifi".
 * behavior: "cycle", "pulse", "rainbow". */
NEBIO_API void nebio_led_animation(const char *color, const char *behavior);
NEBIO_API void nebio_led_animation_stop(void);
NEBIO_API void nebio_led_clear_sc(void);
/* 0 = off .. 1 = full, every LED. */
NEBIO_API void nebio_led_set_dim(double dim);
/* File and freeze LEDs fully on or off: their PWM is heard in the audio. */
NEBIO_API void nebio_led_set_no_pwm(int on);
/* The LED channels start their PWM pulses at different points. */
NEBIO_API void nebio_led_set_stagger(int on);

/* ---- SuperCollider (OSC) ----------------------------------------------- */

NEBIO_API int  nebio_sc_open_sender(void);      /* to 127.0.0.1:3010 */
NEBIO_API void nebio_sc_close_sender(void);
NEBIO_API int  nebio_sc_sender_open(void);
NEBIO_API int  nebio_sc_start_listener(void);   /* on :3011 */
NEBIO_API void nebio_sc_stop_listener(void);
NEBIO_API int  nebio_sc_listener_running(void);

/* "/neb/<name> value", only when changed. */
NEBIO_API void nebio_sc_send_int(const char *name, int value);
NEBIO_API void nebio_sc_send_float(const char *name, double value);
NEBIO_API void nebio_sc_send_bool(const char *name, int value);
NEBIO_API void nebio_sc_send_string(const char *name, const char *value);
/* Always sent. */
NEBIO_API void nebio_sc_send_path_int(const char *path, int value);
NEBIO_API void nebio_sc_send_path_float(const char *path, double value);
NEBIO_API void nebio_sc_clear_cache(void);

/* Set by "/sc/up" from sclang. */
NEBIO_API int  nebio_sc_synth_is_up(void);
NEBIO_API void nebio_sc_set_synth_down(void);   /* also clears the cache */
/* Set by "/neb/ready" from sclang. */
NEBIO_API int  nebio_sc_handshake(void);
NEBIO_API void nebio_sc_zero_handshake(void);

/* ---- Programs bank (OSC to a program's port) ----------------------------- */

/* To 127.0.0.1:<port>; opening again changes the port. */
NEBIO_API int  nebio_osc_open(int port);
NEBIO_API void nebio_osc_close(void);
/* Always sent. */
NEBIO_API void nebio_osc_send_float(const char *path, double value);

/* ---- Codec card ---------------------------------------------------------- */

/* Clipped input samples counted by the card driver; only changes matter.
 * -1: the driver has no counter. */
NEBIO_API int  nebio_card_clip_count(void);

/* ---- Pure Data (TCP text) ---------------------------------------------- */

/* Connects in the background, retrying. */
NEBIO_API void nebio_pd_connect(void);
NEBIO_API void nebio_pd_close(void);
NEBIO_API int  nebio_pd_is_connected(void);
/* "name value;name value;". Never blocks. 0 = sent. */
NEBIO_API int  nebio_pd_send(const char *data, int len);
/* 1 when the patch sent "ready;" back since the last call. Never blocks. */
NEBIO_API int  nebio_pd_take_ready(void);

/* ---- diagnostics ------------------------------------------------------- */

/* One line with scan rate, snapshot rate and worst scan time. */
NEBIO_API const char *nebio_stats(void);

#ifdef __cplusplus
}
#endif

#endif
