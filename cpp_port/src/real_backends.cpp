// The production backends: nebio's C functions and libasound. Not used by
// the tests (they pass fakes), compiled to check they match the interfaces.
#include <alsa/asoundlib.h>

#include "nebio_api.h"
#include "nebmixer.h"
#include "../../Code/nebio/include/nebio.h"

namespace neb {

class RealNebioC : public NebioC {
public:
    int inputs_init() override { return nebio_inputs_init(); }
    std::string last_error() override {
        const char *e = nebio_last_error();
        return e ? e : "";
    }
    long long snapshot() override { return nebio_snapshot(); }
    int sr_bits() override { return nebio_sr_bits(); }
    int adc_codes(int *out, int n) override { return nebio_adc_codes(out, n); }
    int gpio_levels(int *out, int n) override { return nebio_gpio_levels(out, n); }
    int encoder_id(int a, int b) override { return nebio_encoder_id(a, b); }
    int encoder_steps(int id) override { return nebio_encoder_steps(id); }
    void encoder_set_raw(int id, int on) override { nebio_encoder_set_raw(id, on); }
    int encoder_raw(int id) override { return nebio_encoder_raw(id); }
    void encoder_set_click(int id, int on) override { nebio_encoder_set_click(id, on); }
    void set_eol(int high) override { nebio_set_eol(high); }
    int set_input_rates(int s, int d, int a) override { return nebio_set_input_rates(s, d, a); }
    int input_scan_hz() override { return nebio_input_scan_hz(); }
    int input_digital_hz() override { return nebio_input_digital_hz(); }
    int input_adc_hz() override { return nebio_input_adc_hz(); }
    void set_scan_jitter(double f) override { nebio_set_scan_jitter(f); }
    void set_scan_trigger(int e) override { nebio_set_scan_trigger(e); }
    void scan_trigger() override { nebio_scan_trigger(); }
    int set_fast_gpio(int on) override { return nebio_set_fast_gpio(on); }
    int fast_gpio() override { return nebio_fast_gpio(); }
    int set_gate_interrupts(int on) override { return nebio_set_gate_interrupts(on); }
    int gate_interrupts() override { return nebio_gate_interrupts(); }
    void set_gate_holdoff_us(int us) override { nebio_set_gate_holdoff_us(us); }
    std::string stats() override {
        const char *s = nebio_stats();
        return s ? s : "";
    }
    void led_clear_sc() override { nebio_led_clear_sc(); }
    void shutdown() override { nebio_shutdown(); }
    int sc_open_sender() override { return nebio_sc_open_sender(); }
    void sc_close_sender() override { nebio_sc_close_sender(); }
    int sc_sender_open() override { return nebio_sc_sender_open(); }
    int sc_start_listener() override { return nebio_sc_start_listener(); }
    void sc_stop_listener() override { nebio_sc_stop_listener(); }
    int sc_listener_running() override { return nebio_sc_listener_running(); }
    void sc_send_int(const std::string &n, int v) override { nebio_sc_send_int(n.c_str(), v); }
    void sc_send_float(const std::string &n, double v) override { nebio_sc_send_float(n.c_str(), v); }
    void sc_send_bool(const std::string &n, int v) override { nebio_sc_send_bool(n.c_str(), v); }
    void sc_send_string(const std::string &n, const std::string &v) override {
        nebio_sc_send_string(n.c_str(), v.c_str());
    }
    void sc_send_path_int(const std::string &p, int v) override { nebio_sc_send_path_int(p.c_str(), v); }
    void sc_send_path_float(const std::string &p, double v) override { nebio_sc_send_path_float(p.c_str(), v); }
    void sc_clear_cache() override { nebio_sc_clear_cache(); }
    int sc_synth_is_up() override { return nebio_sc_synth_is_up(); }
    void sc_set_synth_down() override { nebio_sc_set_synth_down(); }
    int sc_handshake() override { return nebio_sc_handshake(); }
    void sc_zero_handshake() override { nebio_sc_zero_handshake(); }
    int card_clip_count() override { return nebio_card_clip_count(); }
    int osc_open(int port) override { return nebio_osc_open(port); }
    void osc_close() override { nebio_osc_close(); }
    void osc_send_float(const std::string &p, double v) override { nebio_osc_send_float(p.c_str(), v); }
};

class AlsaAsound : public Asound {
public:
    int mixer_open(void **m, int mode) override {
        return snd_mixer_open(reinterpret_cast<snd_mixer_t **>(m), mode);
    }
    int mixer_attach(void *m, const std::string &d) override { return snd_mixer_attach(mx(m), d.c_str()); }
    int mixer_detach(void *m, const std::string &d) override { return snd_mixer_detach(mx(m), d.c_str()); }
    int mixer_selem_register(void *m) override { return snd_mixer_selem_register(mx(m), nullptr, nullptr); }
    int mixer_load(void *m) override { return snd_mixer_load(mx(m)); }
    int mixer_close(void *m) override { return snd_mixer_close(mx(m)); }
    void *mixer_find_selem_name(void *m, const std::string &name) override {
        snd_mixer_selem_id_t *sid;
        snd_mixer_selem_id_alloca(&sid);
        snd_mixer_selem_id_set_name(sid, name.c_str());
        snd_mixer_selem_id_set_index(sid, 0);
        return snd_mixer_find_selem(mx(m), sid);
    }
    int selem_id_malloc(void **sid) override {
        return snd_mixer_selem_id_malloc(reinterpret_cast<snd_mixer_selem_id_t **>(sid));
    }
    void selem_id_set_name(void *sid, const std::string &n) override {
        snd_mixer_selem_id_set_name(static_cast<snd_mixer_selem_id_t *>(sid), n.c_str());
    }
    void selem_id_set_index(void *sid, unsigned i) override {
        snd_mixer_selem_id_set_index(static_cast<snd_mixer_selem_id_t *>(sid), i);
    }
    void *mixer_find_selem(void *m, void *sid) override {
        return snd_mixer_find_selem(mx(m), static_cast<snd_mixer_selem_id_t *>(sid));
    }
    int selem_set_capture_volume(void *e, int ch, long v) override {
        return snd_mixer_selem_set_capture_volume(el(e), static_cast<snd_mixer_selem_channel_id_t>(ch), v);
    }
    int selem_set_playback_switch_all(void *e, int v) override {
        return snd_mixer_selem_set_playback_switch_all(el(e), v);
    }

private:
    static snd_mixer_t *mx(void *m) { return static_cast<snd_mixer_t *>(m); }
    static snd_mixer_elem_t *el(void *e) { return static_cast<snd_mixer_elem_t *>(e); }
};

NebioC &realNebioC() {
    static RealNebioC c;
    return c;
}

Asound &alsaAsound() {
    static AlsaAsound a;
    return a;
}

}  // namespace neb
