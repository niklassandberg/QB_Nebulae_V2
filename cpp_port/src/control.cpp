#include "control.h"

#include <cmath>
#include <fstream>

#include "classlogger.h"
#include "digitaldata.h"
#include "nconfig.h"
#include "nebio.h"
#include "textfile.h"

namespace neb {

namespace {
ControlDefaults g_defaults;
bool g_defaultsRead = false;

// SPEED_SNAP / PITCH_SNAP: HybridData snaps speed to these factors and pitch
// to whole octaves (within a tolerance). Speed as (positive, negative) pairs.
const double kSpeedFactors[] = {0.0, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0};
const double kPitchSnap[] = {0.0, 0.2, 0.4, 0.6, 0.8, 1.0};

Logger &controlLog() {
    static Logger log("ControlChannel");
    return log;
}
}  // namespace

std::string calibrationPath = "/home/alarm/QB_Nebulae_V2/Code/misc/calibration_data.txt";

void reloadControlDefaults(const std::string &optPath) {
    NConfig config(optPath);
    auto coeff = [&](const char *var, double def) {
        return toFloat(config.getValue("filterCoeff", var, F(def)));
    };
    ControlDefaults d;
    d.smooth = coeff("analog", 0.33);
    d.hybrid = coeff("hybrid", 0.43);
    d.pitch = coeff("pitch", 0.95);
    d.start = coeff("start", 0.95);
    g_defaults = d;
    g_defaultsRead = true;
}

const ControlDefaults &controlDefaults() {
    if (!g_defaultsRead) reloadControlDefaults();
    return g_defaults;
}

Value addHysteresis(const Value &cur, const Value &newVal, const Value &distance) {
    if (lt(add(cur, distance), newVal)) return newVal;
    if (gt(sub(cur, distance), newVal)) return newVal;
    return cur;
}

// ---- AdcData ---------------------------------------------------------------

// Where a chip's channel is in nebio::adc_codes().
static int adcIndex(int device, int channel) {
    if (!(0 <= channel && channel <= 7)) throw PyError("AssertionError", "ADC number must be a value of 0-7!");
    return device * 8 + channel;
}

AdcData::AdcData(int pot, int cv, std::string name_, Value minimum_, Value maximum_, Value init_val)
    : name(std::move(name_)), minimum(std::move(minimum_)), maximum(std::move(maximum_)),
      pot_channel(pot), cv_channel(cv) {
    range = sub(maximum, minimum);
    curVal = minimum;
    raw_pot = raw_cv = static_pot = init_val;
    if (!raw_pot.isNumber()) throw PyError("TypeError", "raw_pot / 4095");  // curminpot
    smoothCoeff = controlDefaults().smooth;
    if (pot_channel >= 0) {
        nebio::inputs();
        codes_ = nebio::adc_codes();
        potIndex_ = adcIndex(nebio::ADC_POT, pot_channel);
    }
    if (cv_channel >= 0) {
        nebio::inputs();
        codes_ = nebio::adc_codes();
        cvIndex_ = adcIndex(nebio::ADC_CV, cv_channel);
    }
    if (name == "start") smoothCoeff = controlDefaults().start;
}

Value AdcData::getValue() {
    Value cv = getCV();
    Value pot = getPot();
    Value temp_rnd = roundTo(add(cv, pot), 4);
    Value temp_hyst = addHysteresis(curVal, temp_rnd, F(hyst_amt));
    if (stablized) {
        if (std::fabs(sub(temp_hyst, curVal).number()) > 0.01) stablized = false;
    } else {
        if (std::fabs(stable_delta) < 0.005)
            stablized = true;
        else
            curVal = clipControl(temp_hyst);
    }
    stable_delta = sub(temp_rnd, last_in).number() + (0.99 * stable_delta);
    last_in = temp_rnd;
    return curVal;
}

Value AdcData::getCV() {
    double temp_cv;
    if (cv_channel >= 0) {
        int code = codes_[cvIndex_];
        temp_cv = ((4095.0 - code) - 2047.0) / 2047.0;
        raw_cv = F(temp_cv);
        temp_cv -= cv_offset;
    } else {
        temp_cv = 0.0;
    }
    double f = filtCVVal.number();
    filtCVVal = F(f + smoothCoeff * (temp_cv - f));
    return filtCVVal;
}

Value AdcData::getPot() {
    if (pot_channel < 0) return F(0.0);
    int code = codes_[potIndex_];
    double temp_pot = (code >> 3) / 511.0;
    raw_pot = F(temp_pot);
    double f = filtPotVal.number();
    filtPotVal = F(f + smoothCoeff * (temp_pot - f));
    Value pot;
    if (resisting_change) {
        Value temp_hyst = addHysteresis(resist_val, raw_pot, F(0.1));
        if (temp_hyst != resist_val) {
            resisting_change = false;
            resist_val = raw_pot;
        }
        pot = static_pot;
    } else if (!ignoring_pot) {
        pot = filtPotVal;
        static_pot = pot;
    } else {
        pot = static_pot;
    }
    return pot;
}

Value AdcData::clipControl(Value val) const {
    if (lt(val, add(minimum, F(hyst_amt * 4)))) val = minimum;
    if (gt(val, sub(maximum, F(hyst_amt * 4)))) val = maximum;
    return val;
}

// ---- HybridData ------------------------------------------------------------

HybridData::HybridData(int channel_, std::string name_, Value minimum_, Value maximum_, Value init_val)
    : name(std::move(name_)), init(init_val), curVal(init_val), hystVal(init_val), channel(channel_),
      staticVal(init_val) {
    if (name == "pitch") {
        minimum = F(-0.30);
        maximum = F(1.30);
        offset = 0.0270;  // Rev 9 post cap
        scaling = 0.8685; // Rev13
        filtCoeff = controlDefaults().pitch;
    } else {
        minimum = minimum_;
        maximum = maximum_;
        scaling = 1.0;
        offset = -0.0049;
        filtCoeff = controlDefaults().hybrid;
    }
    range = sub(maximum, minimum);
    if (channel >= 0) {
        nebio::inputs();
        codes_ = nebio::adc_codes();
        cvIndex_ = adcIndex(nebio::ADC_CV, channel);
    }
}

Value HybridData::getValue() {
    const double hyst_amt = 0.001;
    double temp_analog;
    if (channel >= 0) {
        int code = codes_[cvIndex_];
        temp_analog = ((1.0 - (code / 4095.0)) * range.number()) + minimum.number();
        temp_analog *= scaling;
        raw_cv = F(temp_analog);
    } else {
        temp_analog = 0.0;
        filtVal = 0.0;
    }
    if (name == "speed") {
        temp_analog = (temp_analog * 2.0) - 1.0;
        raw_cv = F(temp_analog);
    }
    if (channel >= 0) {
        filtVal += filtCoeff * (temp_analog - filtVal);
        analogVal = filtVal - offset;
        hystVal = addHysteresis(hystVal, F(analogVal), F(hyst_amt));
        Value temp_rnd = roundTo(add(hystVal, staticVal), 4);
        const double tolerance = 0.00208;
        if (name == "speed") {
            for (double f : kSpeedFactors) {
                double pos = (f + 4.0) / 8.0, neg = ((-1.0 * f) + 4.0) / 8.0;
                if (temp_rnd.number() < pos + tolerance && temp_rnd.number() > pos - tolerance) temp_rnd = F(pos);
                if (temp_rnd.number() < neg + tolerance && temp_rnd.number() > neg - tolerance) temp_rnd = F(neg);
            }
        } else if (name == "pitch") {
            for (double octave : kPitchSnap)
                if (temp_rnd.number() < octave + tolerance && temp_rnd.number() > octave - tolerance)
                    temp_rnd = F(octave);
        }
        if (stablized) {
            if (std::fabs(sub(temp_rnd, curVal).number()) > 0.005) stablized = false;
        } else {
            if (std::fabs(stable_delta) < 0.005) stablized = true;
            curVal = temp_rnd;
        }
        stable_delta = sub(temp_rnd, last_in).number() + (0.99 * stable_delta);
        last_in = temp_rnd;
    } else {
        curVal = staticVal;
    }
    if (gt(curVal, maximum))
        curVal = maximum;
    else if (lt(curVal, minimum))
        curVal = minimum;
    return curVal;
}

void RawEncoderData::setActive(bool state) { nebio::encoder_set_raw(name, state); }

// ---- CommChannel -----------------------------------------------------------

CommChannel::CommChannel(Csound *csound, std::string name) : csound_(csound), name_(std::move(name)) {
    if (csound_) channel_ = csound_->channelPtr(name_, CSOUND_CONTROL_CHANNEL | CSOUND_OUTPUT_CHANNEL);
}

void CommChannel::update() {
    if (!channel_) return;
    prev_state = state;
    state = F(channel_[0]);
    rising_edge_flag = state.number() > 0.0 && prev_state.number() < 1.0;
}

void CommChannel::clearState() {
    if (channel_ && state == I(1)) {
        state = I(0);
        csound_->setControlChannel(name_, state);
    }
}

// ---- ControlChannel --------------------------------------------------------

ControlChannel::ControlChannel(Csound *csound, std::string name_, Value init, std::string source_, Options opt)
    : name(std::move(name_)), source(std::move(source_)), csound_(csound) {
    nebio::inputs();
    if (csound_) channel_ = csound_->channelPtr(name, CSOUND_CONTROL_CHANNEL | CSOUND_INPUT_CHANNEL);
    curVal = prevVal = init;
    writeChannel();
    std::string mode = "latching", edge = "falling";
    if (opt.config) {
        mode = opt.config->at(0);
        edge = opt.config->at(1);
    }
    int cvchn = opt.cvchn == -2 ? opt.data_channel : opt.cvchn;
    if (source == "analog") {
        input_ = std::make_unique<AdcData>(opt.data_channel, cvchn, name, opt.minimum, opt.maximum, init);
    } else if (source == "static") {
        input_ = std::make_unique<StaticData>(curVal);
    } else if (source == "digital") {
        if (opt.sr)
            input_ = std::make_unique<DigitalData>(name, opt.data_channel, opt.gate_pin, opt.button_pin, opt.sr,
                                                   mode, edge, opt.maximum, opt.longtouch_cb, 0, init);
    } else if (source == "hybrid") {
        input_ = std::make_unique<HybridData>(opt.data_channel, name, opt.minimum, opt.maximum, curVal);
    } else if (source == "rawencoder") {
        input_ = std::make_unique<RawEncoderData>(name);
    }
    if (source == "analog" || source == "hybrid") setCVOffset(gatherOffset(name));
}

ControlChannel::~ControlChannel() = default;

DigitalData *ControlChannel::digital() const { return dynamic_cast<DigitalData *>(input_.get()); }

InputData &ControlChannel::input() {
    if (!input_) throw PyError("AttributeError", "'ControlChannel' object has no attribute 'input'");
    return *input_;
}

void ControlChannel::writeChannel() {
    if (csound_) {
        if (!curVal.isNumber()) throw PyError("TypeError", "channel[0] needs a number");
        channel_[0] = curVal.number();
    } else {
        dummy_ = curVal;
    }
}

Value ControlChannel::channelValue() const { return csound_ ? F(channel_[0]) : dummy_; }

void ControlChannel::setValue(const Value &val) {
    input().setValue(val);
    curVal = input().getValue();
    if (!mute_csound) writeChannel();
}

Value ControlChannel::getPotValue() {
    if (source == "analog") return static_cast<AdcData &>(input()).getPotValue();
    return Value::none();
}

Value ControlChannel::getRawCVValue() {
    if (source == "analog") return static_cast<AdcData &>(input()).getRawCVValue();
    if (source == "hybrid") return static_cast<HybridData &>(input()).getRawCVValue();
    return Value::none();
}

Value ControlChannel::getCVValue() {
    if (source == "analog") return static_cast<AdcData &>(input()).getCVValue();
    if (source == "hybrid") return static_cast<HybridData &>(input()).getCVValue();
    return Value::none();
}

Value ControlChannel::getStaticVal() {
    if (source == "hybrid") return static_cast<HybridData &>(input()).getStaticVal();
    return Value::none();
}

void ControlChannel::setCVOffset(double value) {
    if (source == "hybrid") static_cast<HybridData &>(input()).setCVOffset(value);
    else if (source == "analog") static_cast<AdcData &>(input()).setCVOffset(value);
}

void ControlChannel::setIgnoreNextButton() {
    if (source == "digital") static_cast<DigitalData &>(input()).setIgnoreNextButton();
}

void ControlChannel::setOutputPeriod(const Value &ms) {
    if (source == "digital") static_cast<DigitalData &>(input()).setOutputPeriod(ms);
}

void ControlChannel::setMode(const std::string &mode, const std::string &edge) {
    if (source == "digital") static_cast<DigitalData &>(input()).setMode(mode, edge);
}

void ControlChannel::setModeChangeValue(const Value &v) {
    if (source == "analog") static_cast<AdcData &>(input()).setResistVal(v);
}

void ControlChannel::clearResistVal() {
    if (source == "analog") static_cast<AdcData &>(input()).clearResistVal();
}

bool ControlChannel::isResisting() {
    if (source == "analog") return static_cast<AdcData &>(input()).isResisting();
    return false;
}

void ControlChannel::setIgnoreHID(bool state) {
    if (source == "analog") static_cast<AdcData &>(input()).setIgnoreHID(state);
    else if (source == "digital") static_cast<DigitalData &>(input()).setIgnoreHID(state);
    else if (source == "hybrid") static_cast<HybridData &>(input()).setIgnoreHID(state);
}

void ControlChannel::setIgnoreGate(bool state) {
    if (source == "digital") static_cast<DigitalData &>(input()).setIgnoreGate(state);
}

std::string ControlChannel::getTrigSource() {
    if (source == "digital") return static_cast<DigitalData &>(input()).getTrigSource();
    return "none";
}

Value ControlChannel::getLEDValue() {
    if (source == "digital") return static_cast<DigitalData &>(input()).getLEDValue();
    return curVal;
}

// Lines "<name>,<offset>"; every line starting with name counts (so "speed"
// also reads "speed_alt,..."), the last one wins. A line without a comma ends
// the reading, as the IndexError does in the original.
double ControlChannel::gatherOffset(const std::string &name_) {
    double val = 0.0;
    std::vector<std::string> lines;
    try {
        lines = textfile::lines(calibrationPath);
    } catch (const PyError &) {
        NLOG(controlLog(), ERROR, "No file: %s", calibrationPath.c_str());
        return val;
    }
    for (std::string line : lines) {
        if (!line.empty() && line.back() == '\n') line.pop_back();
        if (line.compare(0, name_.size(), name_) != 0) continue;
        size_t comma = line.find(',');
        if (comma == std::string::npos) {
            NLOG(controlLog(), ERROR, "No file: %s", calibrationPath.c_str());
            return val;
        }
        size_t next = line.find(',', comma + 1);
        std::string field = line.substr(comma + 1, next == std::string::npos ? std::string::npos : next - comma - 1);
        auto v = pyFloat(field);
        if (v)
            val = *v;
        else
            NLOG(controlLog(), ERROR, "list value is not a floating point number:%s", field.c_str());
    }
    return val;
}

void ControlChannel::update() {
    Value val = input().getValue();
    prevVal = curVal;
    curVal = val;
    if (!mute_csound) writeChannel();
}

}  // namespace neb
