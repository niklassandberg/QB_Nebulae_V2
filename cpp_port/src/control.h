// control.py: the knob/CV (AdcData), encoder+CV (HybridData), fixed
// (StaticData) and digital inputs behind one ControlChannel, and CommChannel
// for values Csound sends back. Values keep Python's int/float type: an int
// minimum comes back as an int, which decides what SC receives.
#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "inputs.h"
#include "nebio_api.h"
#include "pyvalue.h"

namespace neb {

class DigitalData;

constexpr int BUTTON_GATE_GPIO = 0;
constexpr int BUTTON_SR_GATE_GPIO = 1;
constexpr int BUTTON_GATE_SR = 2;
constexpr int BUTTON_GPIO_GATE_SR = 3;
constexpr int BUTTON_GPIO_GATE_NONE = 4;
constexpr int BUTTON_SR_GATE_NONE = 5;

// Filter coefficients from ./nebulae.opt [filterCoeff], read once like the
// module-level code of control.py; reloadDefaults() reads them again.
struct ControlDefaults {
    double smooth = 0.33, hybrid = 0.43, pitch = 0.95, start = 0.95;
};
const ControlDefaults &controlDefaults();
void reloadControlDefaults(const std::string &optPath = "./nebulae.opt");

// Where ControlChannel.gatherOffset() reads the CV offsets.
extern std::string calibrationPath;

Value addHysteresis(const Value &cur, const Value &newVal, const Value &distance);

class InputData {
public:
    virtual ~InputData() = default;
    virtual Value getValue() = 0;
    virtual void setValue(const Value &v) = 0;
};

class AdcData : public InputData {
public:
    AdcData(int pot_channel, int cv_channel, std::string name, Value minimum, Value maximum,
            Value init_val = F(0.0));
    void setIgnoreHID(bool state) { ignoring_pot = state; }
    static double convertRawCV(double cv_in) { return ((4095 - cv_in) - 2047) / 2047.0; }
    void setResistVal(const Value &value) { resisting_change = true; resist_val = value; }
    void clearResistVal() { resisting_change = false; }
    bool isResisting() const { return resisting_change; }
    Value getRawPotValue() const { return raw_pot; }
    Value getRawCVValue() const { return raw_cv; }
    Value getPotValue() const { return filtPotVal; }
    Value getCVValue() const { return sub(raw_cv, F(cv_offset)); }
    Value getValue() override;
    Value getCV();
    Value getPot();
    Value clipControl(Value val) const;
    void setCVOffset(double value) { cv_offset = value; }
    void setValue(const Value &val) override { static_pot = val; setResistVal(val); }

    std::string name;
    Value minimum, maximum, range, curVal;
    double cv_offset = 0.011;
    int pot_channel, cv_channel;
    Value raw_pot, raw_cv, static_pot, resist_val = I(0);
    bool resisting_change = false, ignoring_pot = false;
    Value filtPotVal = I(0), filtCVVal = I(0);
    double smoothCoeff, hyst_amt = 0.002;
    bool stablized = true;
    double stable_delta = 0.0;
    Value last_in = F(0.0);

private:
    const int *codes_ = nullptr;  // nebio::adc_codes(), filled by every snapshot
    int potIndex_ = 0, cvIndex_ = 0;
};

class StaticData : public InputData {
public:
    explicit StaticData(Value init) : curVal(std::move(init)) {}
    Value getValue() override { return curVal; }
    void setValue(const Value &v) override { curVal = v; }
    Value curVal;
};

class HybridData : public InputData {
public:
    HybridData(int channel, std::string name, Value minimum, Value maximum, Value init_val);
    Value getValue() override;
    void setCVOffset(double value) { offset = value; }
    void setIgnoreHID(bool state) { ignore_enc = state; }
    void setValue(const Value &value) override {
        if (!ignore_enc) staticVal = value;
    }
    Value getStaticVal() const { return staticVal; }
    Value getRawCVValue() const { return raw_cv; }
    Value getCVValue() const { return sub(raw_cv, F(offset)); }

    std::string name;
    Value init, curVal, hystVal, minimum, maximum, range;
    double offset, scaling, filtCoeff;
    int channel;
    double analogVal = 0.0, filtVal = 0.0;
    Value raw_cv = I(0);
    double stable_delta = 0.0;
    bool stablized = true;
    Value last_in = F(0.0);
    Value staticVal;
    bool ignore_enc = false;

private:
    const int *codes_ = nullptr;
    int cvIndex_ = 0;
};

// rawencoder: sclang owns the value and LEDs; this only switches the routing.
class RawEncoderData : public InputData {
public:
    explicit RawEncoderData(std::string name) : name(std::move(name)) {}
    void setActive(bool state);
    Value getValue() override { return F(0.0); }
    void setValue(const Value &) override {}
    void setIgnoreHID(bool) {}
    std::string name;
};

// One value Csound sends back.
class CommChannel {
public:
    CommChannel(Csound *csound, std::string name);
    void update();
    Value getState() const { return state; }
    bool risingEdge() const { return state == I(1) && prev_state == I(0); }
    bool fallingEdge() const { return state == I(0) && prev_state == I(1); }
    void clearState();

    Value prev_state = I(0), state = I(0);
    bool rising_edge_flag = false;

private:
    Csound *csound_;
    std::string name_;
    double *channel_ = nullptr;
};

// ControlChannel's keyword arguments.
struct ControlOptions {
    int data_channel = -1;
    ShiftRegister *sr = nullptr;
    int gate_pin = -1, button_pin = -1;
    std::optional<std::vector<std::string>> config;  // {mode, edge}; none: latching, falling
    Value minimum = I(0), maximum = I(1);
    int cvchn = -2;
    std::function<void()> longtouch_cb;
};

// One control: its input and the Csound channel it writes.
class ControlChannel {
public:
    using Options = ControlOptions;
    ControlChannel(Csound *csound, std::string name, Value init = I(0), std::string source = "static",
                   Options opt = Options());
    ~ControlChannel();

    void setValue(const Value &val);
    Value getValue() const { return curVal; }
    Value getPrevValue() const { return prevVal; }
    Value getPotValue();
    Value getRawCVValue();
    Value getCVValue();
    Value getStaticVal();
    void setCVOffset(double value);
    void setIgnoreNextButton();
    void setOutputPeriod(const Value &ms);
    void setMode(const std::string &mode, const std::string &edge);
    void setModeChangeValue(const Value &value_to_resist);
    void clearResistVal();
    bool isResisting();
    bool hasChanged() const { return curVal != prevVal; }
    void setIgnoreHID(bool state);
    void setIgnoreGate(bool state);
    std::string getTrigSource();
    void muteCSound(bool state) { mute_csound = state; }
    bool isCSoundMuted() const { return mute_csound; }
    Value getLEDValue();
    double gatherOffset(const std::string &name);
    void update();
    Value channelValue() const;  // channel[0]

    std::string name, source;
    Value curVal, prevVal;
    bool mute_csound = false;

    AdcData *adc() const { return dynamic_cast<AdcData *>(input_.get()); }
    HybridData *hybrid() const { return dynamic_cast<HybridData *>(input_.get()); }
    DigitalData *digital() const;
    RawEncoderData *raw() const { return dynamic_cast<RawEncoderData *>(input_.get()); }

private:
    InputData &input();  // PyError AttributeError: no input for this source
    void writeChannel();

    Csound *csound_;
    double *channel_ = nullptr;
    Value dummy_;  // channel[0] without Csound
    std::unique_ptr<InputData> input_;
};

}  // namespace neb
