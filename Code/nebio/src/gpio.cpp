#include "gpio.h"

#include <cstdlib>

#include "log.h"

namespace nebio {

GpioChip &GpioChip::instance() {
    // Never destroyed: threads may still use it while the process exits.
    static GpioChip *chip = new GpioChip();
    return *chip;
}

GpioChip::~GpioChip() {
    if (chip_) gpiod_chip_close(chip_);
}

gpiod_chip *GpioChip::get() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (chip_) return chip_;
    const char *path = std::getenv("NEBIO_GPIOCHIP");
    if (!path) path = "/dev/gpiochip0";
    chip_ = gpiod_chip_open(path);
    if (!chip_) logError("could not open %s", path);
    return chip_;
}

GpioLines::~GpioLines() { release(); }

void GpioLines::release() {
    if (events_) {
        gpiod_edge_event_buffer_free(events_);
        events_ = nullptr;
    }
    if (req_) {
        gpiod_line_request_release(req_);
        req_ = nullptr;
    }
    pins_.clear();
}

bool GpioLines::request(const std::vector<unsigned> &pins, gpiod_line_settings *settings) {
    gpiod_chip *chip = GpioChip::instance().get();
    if (!chip || !settings) return false;

    gpiod_line_config *lineCfg = gpiod_line_config_new();
    gpiod_request_config *reqCfg = gpiod_request_config_new();
    bool ok = false;
    if (lineCfg && reqCfg &&
        gpiod_line_config_add_line_settings(lineCfg, pins.data(), pins.size(), settings) == 0) {
        gpiod_request_config_set_consumer(reqCfg, "nebio");
        req_ = gpiod_chip_request_lines(chip, reqCfg, lineCfg);
        ok = req_ != nullptr;
    }
    if (ok) {
        pins_ = pins;
    } else {
        logError("could not request %zu GPIO line(s) starting at %u", pins.size(),
                 pins.empty() ? 0u : pins[0]);
    }
    if (reqCfg) gpiod_request_config_free(reqCfg);
    if (lineCfg) gpiod_line_config_free(lineCfg);
    return ok;
}

bool GpioLines::requestInputs(const std::vector<unsigned> &pins, Bias bias, bool edgeEvents) {
    release();
    gpiod_line_settings *s = gpiod_line_settings_new();
    if (!s) return false;
    gpiod_line_settings_set_direction(s, GPIOD_LINE_DIRECTION_INPUT);
    gpiod_line_settings_set_bias(s, bias == Bias::PullUp ? GPIOD_LINE_BIAS_PULL_UP
                                                         : GPIOD_LINE_BIAS_DISABLED);
    if (edgeEvents) gpiod_line_settings_set_edge_detection(s, GPIOD_LINE_EDGE_BOTH);
    bool ok = request(pins, s);
    gpiod_line_settings_free(s);
    if (ok && edgeEvents) {
        events_ = gpiod_edge_event_buffer_new(64);
        if (!events_) {
            release();
            return false;
        }
    }
    return ok;
}

bool GpioLines::requestOutputs(const std::vector<unsigned> &pins, int initialValue) {
    release();
    gpiod_line_settings *s = gpiod_line_settings_new();
    if (!s) return false;
    gpiod_line_settings_set_direction(s, GPIOD_LINE_DIRECTION_OUTPUT);
    gpiod_line_settings_set_output_value(
        s, initialValue ? GPIOD_LINE_VALUE_ACTIVE : GPIOD_LINE_VALUE_INACTIVE);
    bool ok = request(pins, s);
    gpiod_line_settings_free(s);
    return ok;
}

int GpioLines::get(unsigned pin) const {
    if (!req_) return -1;
    gpiod_line_value v = gpiod_line_request_get_value(req_, pin);
    if (v == GPIOD_LINE_VALUE_ERROR) return -1;
    return v == GPIOD_LINE_VALUE_ACTIVE ? 1 : 0;
}

bool GpioLines::getAll(std::vector<int> &values) {
    if (!req_) return false;
    std::vector<gpiod_line_value> raw(pins_.size());
    if (gpiod_line_request_get_values(req_, raw.data()) != 0) return false;
    values.resize(raw.size());
    for (size_t i = 0; i < raw.size(); ++i) values[i] = raw[i] == GPIOD_LINE_VALUE_ACTIVE ? 1 : 0;
    return true;
}

void GpioLines::set(unsigned pin, int value) {
    if (!req_) return;
    gpiod_line_request_set_value(req_, pin,
                                 value ? GPIOD_LINE_VALUE_ACTIVE : GPIOD_LINE_VALUE_INACTIVE);
}

int GpioLines::waitEdges(int64_t timeoutNs, std::vector<Edge> &out) {
    out.clear();
    if (!req_ || !events_) return -1;
    int r = gpiod_line_request_wait_edge_events(req_, timeoutNs);
    if (r <= 0) return r;
    int n = gpiod_line_request_read_edge_events(req_, events_, 64);
    if (n < 0) return -1;
    for (int i = 0; i < n; ++i) {
        gpiod_edge_event *ev = gpiod_edge_event_buffer_get_event(events_, i);
        Edge e;
        e.pin = gpiod_edge_event_get_line_offset(ev);
        e.level = gpiod_edge_event_get_event_type(ev) == GPIOD_EDGE_EVENT_RISING_EDGE ? 1 : 0;
        out.push_back(e);
    }
    return n;
}

}  // namespace nebio
