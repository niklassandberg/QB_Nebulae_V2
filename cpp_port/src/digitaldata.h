// digitaldata.py: a button and/or gate input as latching, triggered,
// momentary or incremental control, with long press and ignore rules.
#pragma once

#include <functional>
#include <memory>
#include <string>

#include "control.h"
#include "inputs.h"

namespace neb {

constexpr int DEFAULT_OUTPUT_PERIOD = 10;  // output to csound pulse in ms

class DigitalData : public InputData {
public:
    DigitalData(std::string name, int button_gate_mode, int gate_pin, int button_pin, ShiftRegister *sr,
                std::string mode = "latching", std::string edge = "falling", Value maximum = I(1),
                std::function<void()> longtouch_cb = nullptr, int inc_order = 0, Value init_val = I(0));

    void setIgnoreHID(bool state) { ignore_button = state; }
    void setIgnoreGate(bool state) { ignore_gate = state; }
    void setValue(const Value &val) override { state = val; }
    void setIncOrder(int val) { inc_order = val; }
    void setIgnoreNextButton() { ignore_next_btrig = true; }
    void setOutputPeriod(const Value &ms) { output_period = ms; }
    void setMode(const std::string &mode, const std::string &edge);
    std::string getTrigSource() const { return trig_source; }
    int getAction(int state, int prev_state, const std::string &source) const;
    void updateLongPress(int raw_button);
    std::pair<int, int> getRawValues(const std::string &controltype, bool skip_update = false);
    void handle_button();
    void handle_gate();
    void handle_incremental_value();
    Value getValue() override;
    Value getLEDValue();

    int b_state = 0, g_state = 0;
    int gate_pin, button_pin;
    Value prev_state, state, led_state;
    std::string edge, mode;
    double gate_pulse_time, button_pulse_time, led_pulse_time;
    Value maximum;
    int time_held = 0;
    bool button_pressed = false;
    int long_press_time = 300;
    Value output_period = I(DEFAULT_OUTPUT_PERIOD);
    int led_period = 40;
    bool ignore_next_btrig;
    std::string name;
    bool is_alt;
    std::function<void()> longtouch_cb;
    int inc_order;
    bool ignore_button = false, ignore_gate = false;
    std::string trig_source = "button";
    std::string gate_src, button_src;  // "GPIO", "SR", "NONE"; empty: unknown mode

private:
    ShiftRegister *sr_;
    std::unique_ptr<Switch> gateSwitch_, buttonSwitch_;
};

}  // namespace neb
