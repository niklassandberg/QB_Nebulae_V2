// nebconfig.py: the nebconfig block of an instrument, one
// "key,value[,value...]" per line. The parts the control handlers use; the
// .pd comment boxes (_pdEntries) and the JACK/kernel/run keys are not
// ported yet.
#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "settings.h"

namespace neb {

// One page: or hold: line: (name, path, min, max, curve, default, step).
struct PageSpec {
    std::string name, path;
    double lo, hi;
    std::string curve;
    double value, step;
};

using PageList = std::vector<PageSpec>;

// One osc: line: the control's value scaled to min..max, sent to path.
struct OscBinding {
    std::string control, path;
    double lo, hi;
    std::string curve;
};

constexpr int DEFAULT_OSC_PORT = 3020;

// In the order the encoders first appear in the block.
using EncoderPageSpecs = std::vector<std::pair<std::string, PageList>>;
// Layer ("record", "record+file") -> its encoders, in block order.
using HoldPageSpecs = std::vector<std::pair<std::string, EncoderPageSpecs>>;

class NebConfig {
public:
    // A key given twice keeps its first place and the last values.
    explicit NebConfig(const std::vector<std::string> &entries, std::string body = "");
    static NebConfig readFile(const std::string &path);  // PyError of textfile::read

    const std::vector<std::string> *entry(const std::string &name) const;  // nullptr: no such key
    std::optional<std::string> value(const std::string &name) const;
    std::string value(const std::string &name, const std::string &fallback) const;
    OrderedDict asDict() const;  // key -> list of str, as the handlers' configData

    std::string encoderType(const std::string &name) const;  // rawencoder, pages or hybrid
    double outputPeriod() const;                              // PyError ValueError: ksmps/sr not an int
    // "playback": speed's osc: value is a playback speed, shown on the speed LEDs.
    std::optional<std::string> speedLeds() const;
    int oscPort() const;  // PyError ValueError: not 1024..65535
    std::pair<std::vector<OscBinding>, std::vector<std::string>> oscBindings() const;
    std::pair<EncoderPageSpecs, std::vector<std::string>> encoderPages() const;
    std::pair<HoldPageSpecs, std::vector<std::string>> holdPages() const;
    // Encoder -> its CV page; nullopt inside: "none". Only the encoders with a cv: line.
    std::vector<std::pair<std::string, std::optional<std::string>>> cvTargets() const;

    std::string body;

private:
    std::vector<std::pair<std::string, std::vector<std::string>>> entries_;
};

}  // namespace neb
