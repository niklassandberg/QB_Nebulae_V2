#include "digitaldata.h"

#include "classlogger.h"

namespace neb {

static double nowMs() { return clock().time() * 1000.0; }

DigitalData::DigitalData(std::string name_, int button_gate_mode, int gate_pin_, int button_pin_, ShiftRegister *sr,
                         std::string mode_, std::string edge_, Value maximum_, std::function<void()> longtouch_cb_,
                         int inc_order_, Value init_val)
    : gate_pin(gate_pin_), button_pin(button_pin_), edge(std::move(edge_)), mode(std::move(mode_)),
      maximum(std::move(maximum_)), name(std::move(name_)), longtouch_cb(std::move(longtouch_cb_)),
      inc_order(inc_order_), sr_(sr) {
    prev_state = state = led_state = I(toInt(init_val));
    gate_pulse_time = button_pulse_time = led_pulse_time = nowMs();
    if (gt(state, maximum)) state = I(0);  // out of range selection at init time
    ignore_next_btrig = edge == "falling";
    is_alt = name.find("_alt") != std::string::npos;  // alt channels ignore the gate
    if (name == "file") led_state = I(0);  // LED stays low when file is >0 at bootup
    switch (button_gate_mode) {
    case BUTTON_GATE_GPIO:
        gate_src = button_src = "GPIO";
        gateSwitch_ = std::make_unique<Switch>(gate_pin);
        buttonSwitch_ = std::make_unique<Switch>(button_pin);
        break;
    case BUTTON_SR_GATE_GPIO:
        gate_src = "GPIO";
        button_src = "SR";
        gateSwitch_ = std::make_unique<Switch>(gate_pin);
        break;
    case BUTTON_GPIO_GATE_SR:
        gate_src = "SR";
        button_src = "GPIO";
        buttonSwitch_ = std::make_unique<Switch>(button_pin);
        break;
    case BUTTON_GATE_SR:
        gate_src = button_src = "SR";
        break;
    case BUTTON_GPIO_GATE_NONE:
        gate_src = "NONE";
        button_src = "GPIO";
        buttonSwitch_ = std::make_unique<Switch>(button_pin);
        break;
    case BUTTON_SR_GATE_NONE:
        gate_src = "NONE";
        button_src = "SR";
        break;
    }
}

// A new mode starts from 0, as the old state means something else in it.
void DigitalData::setMode(const std::string &mode_, const std::string &edge_) {
    if (mode_ != mode) {
        mode = mode_;
        state = prev_state = led_state = I(0);
        b_state = g_state = 0;
    }
    edge = edge_;
    ignore_next_btrig = edge == "falling";
}

int DigitalData::getAction(int st, int prev, const std::string &source) const {
    if (edge == "rising" || source == "gate") return (prev == 0 && st == 1) ? 1 : 0;
    if (edge == "falling") return (prev == 1 && st == 0) ? 1 : 0;
    return 0;
}

void DigitalData::updateLongPress(int raw_button) {
    if (edge != "falling") return;
    if (raw_button == 1) {
        button_pressed = true;
        time_held = 0;
    }
    if (button_pressed) time_held += 1;
    if (time_held > long_press_time) {
        if (longtouch_cb) longtouch_cb();
        time_held = 0;
    }
}

std::pair<int, int> DigitalData::getRawValues(const std::string &controltype, bool skip_update) {
    bool gate = controltype == "gate";
    const std::string &src = gate ? gate_src : button_src;
    if (src.empty()) throw PyError("AttributeError", "'DigitalData' object has no attribute 'gate_src'");
    if (src == "GPIO") {
        Switch &sw = gate ? *gateSwitch_ : *buttonSwitch_;
        if (!skip_update) sw.update();
        return {sw.state() ? 1 : 0, sw.prevState() ? 1 : 0};
    }
    if (src == "SR") {
        if (!sr_) throw PyError("AttributeError", "'NoneType' object has no attribute 'state'");
        int pin = gate ? gate_pin : button_pin;
        int st = sr_->state(pin) ? 1 : 0;
        int prev = sr_->prevState(pin) ? 1 : 0;
        if (gate) {  // flip for hardware
            st = 1 - st;
            prev = 1 - prev;
        }
        return {st, prev};
    }
    return {0, 0};
}

void DigitalData::handle_button() {
    if (ignore_button) return;
    auto [raw_button, raw_prev_button] = getRawValues("button");
    int action = getAction(raw_button, raw_prev_button, "button");
    if (edge == "falling") updateLongPress(raw_button);
    if (ignore_next_btrig) {
        if (action == 1) {
            action = 0;
            ignore_next_btrig = false;
            time_held = 0;
            button_pressed = false;
        } else if (raw_button == 0) {
            // Only the press going on right now is ignored. Up and nothing
            // ignored: drop it, or it eats the next real press.
            ignore_next_btrig = false;
        }
    }
    if (mode == "triggered") {
        if (action == 1) {
            button_pulse_time = nowMs();
            b_state = 1;
        }
        if (b_state == 1 && nowMs() - button_pulse_time > output_period.number()) b_state = 0;
    } else if (mode == "latching") {
        b_state = action == 1 ? 1 : 0;
    } else if (mode == "momentary") {
        b_state = raw_button == 1 ? 1 : 0;
    } else if (mode == "incremental") {
        if (action == 1) b_state = 1;
    }
}

void DigitalData::handle_gate() {
    if (is_alt) ignore_gate = true;
    if (ignore_gate) return;
    auto [raw_gate, raw_prev_gate] = getRawValues("gate");
    int action = getAction(raw_gate, raw_prev_gate, "gate");
    if (mode == "triggered") {
        if (action == 1) {
            gate_pulse_time = nowMs();
            g_state = 1;
        }
        if (g_state == 1 && nowMs() - gate_pulse_time > output_period.number()) g_state = 0;
    } else if (mode == "latching") {
        g_state = action == 1 ? 1 : 0;
    } else if (mode == "momentary") {
        g_state = raw_gate == 1 ? 1 : 0;
    } else if (mode == "incremental") {
        if (action == 1) g_state = 1;
    }
}

void DigitalData::handle_incremental_value() {
    int g = g_state, b = b_state;
    g_state = b_state = 0;
    if (g == 1 || b == 1) {
        if (inc_order == 0) {
            state = add(state, I(1));
            if (!lt(state, maximum)) state = I(0);
        } else if (inc_order == 1) {
            state = sub(state, I(1));
            if (lt(state, I(0))) state = sub(maximum, I(1));
        } else if (inc_order == 2) {
            Value top = sub(maximum, I(1));
            if (top.type == Value::Float)  // randint() takes no float (Python 3.12+)
                throw PyError("TypeError", "'float' object cannot be interpreted as an integer");
            state = I(random().randint(0, static_cast<int>(toInt(top))));
        }
    }
    if (gt(state, maximum)) state = I(0);
}

Value DigitalData::getValue() {
    prev_state = state;
    handle_button();
    handle_gate();
    if (g_state == 1)
        trig_source = "gate";
    else if (b_state == 1)
        trig_source = "button";
    if (mode == "incremental") {
        handle_incremental_value();
    } else if (mode == "momentary" || mode == "triggered") {
        state = I((g_state == 1 || b_state == 1) ? 1 : 0);
    } else if (mode == "latching") {
        if (g_state == 1 || b_state == 1) {
            g_state = b_state = 0;
            state = I(state == I(1) ? 0 : 1);
        }
    }
    return state;
}

Value DigitalData::getLEDValue() {
    if (mode == "latching" || mode == "momentary") led_state = state;
    if (mode == "triggered") {
        if (state == I(1) && prev_state == I(0)) {
            led_pulse_time = nowMs();
            led_state = I(1);
        }
        if (led_state == I(1) && nowMs() - led_pulse_time > led_period) led_state = I(0);
    }
    if (mode == "incremental") {
        auto [raw_gate, raw_prev_gate] = getRawValues("gate", true);
        auto [raw_button, raw_prev_button] = getRawValues("button", true);
        int baction = getAction(raw_button, raw_prev_button, "button");
        int gaction = getAction(raw_gate, raw_prev_gate, "gate");
        if (baction == 1 || gaction == 1) {
            led_pulse_time = nowMs();
            led_state = I(1);
        }
        if (led_state == I(1) && nowMs() - led_pulse_time > led_period) led_state = I(0);
    }
    return led_state;
}

}  // namespace neb
