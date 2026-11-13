// controlhandlerProg.py: the programs bank. Controls go to the program as
// OSC, by the .prog's osc: lines; encoder pages go to their own paths.
#pragma once

#include <map>
#include <optional>
#include <string>
#include <vector>

#include "controlhandlerEncoders.h"

namespace neb {

// Everything is resent this often, so a program that starts late gets all values.
constexpr int PROG_RESEND_MS = 1000;

class ProgControlHandler : public EncoderControlHandler {
public:
    ProgControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData, std::string instr,
                       std::string bank, int oscPort, const std::vector<OscBinding> &bindings,
                       HandlerEnv env = HandlerEnv());

    void setConfig(const NebConfig &config, const std::string &pages_path) override;
    // The playback speed sent for speed (speedleds,playback), else none.
    std::optional<double> playbackSpeed();
    void closeSockets() override;
    // Nebulae saves what it sends; /neb/save is for a program's own values.
    void saveInstrument() override;
    void sendControl(const std::string &name, const Value &value) override;
    void sendPath(const std::string &path, double value) override;
    void enterProgramsMode();
    void enterNormalMode() override { enterProgramsMode(); }
    void sendProgMessages(const std::vector<ControlChannel *> &chans);
    void updateAll() override;

    struct Target {
        std::string path;
        double lo, hi;
        std::string curve;
    };
    int oscPort;
    std::map<std::string, std::vector<Target>> bindings;  // control -> its osc: lines
    std::map<std::string, double> prog_sent;
    long long prog_resend_time = 0;
    bool speed_leds = false;
};

}  // namespace neb
