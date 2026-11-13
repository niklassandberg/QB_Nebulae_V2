#include "controlhandlerProg.h"

#include "nebio.h"

namespace neb {

ProgControlHandler::ProgControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                                       std::string instr, std::string bank, int oscPort_,
                                       const std::vector<OscBinding> &oscBindings, HandlerEnv env)
    : EncoderControlHandler(csound, numberFiles, configData, std::move(instr), std::move(bank), std::move(env)),
      oscPort(oscPort_) {
    for (auto &b : oscBindings) bindings[b.control].push_back(Target{b.path, b.lo, b.hi, b.curve});
}

void ProgControlHandler::setConfig(const NebConfig &config, const std::string &pages_path) {
    EncoderControlHandler::setConfig(config, pages_path);
    speed_leds = config.speedLeds() == std::optional<std::string>("playback") && bindings.count("speed");
}

std::optional<double> ProgControlHandler::playbackSpeed() {
    if (!speed_leds) return std::nullopt;
    for (auto &kv : pages)
        if (kv.first == "speed") return std::nullopt;
    const Target &t = bindings.at("speed").front();
    return scale(channel("speed").getValue(), F(t.lo), F(t.hi), t.curve);
}

void ProgControlHandler::closeSockets() {
    saveInstrument();
    EncoderControlHandler::closeSockets();
    nebio::osc_close();
}

void ProgControlHandler::saveInstrument() {
    EncoderControlHandler::saveInstrument();
    nebio::osc_send("/neb/save", 1);
}

void ProgControlHandler::sendControl(const std::string &name, const Value &value) {
    auto it = bindings.find(name);
    if (it == bindings.end()) return;
    for (auto &t : it->second) {
        double out = scale(value, F(t.lo), F(t.hi), t.curve);
        nebio::osc_send(t.path, out);
        prog_sent[t.path] = out;
    }
}

void ProgControlHandler::sendPath(const std::string &path, double value) { nebio::osc_send(path, value); }

void ProgControlHandler::enterProgramsMode() {
    prev_control_mode = control_mode;
    if (control_mode == "secondary controls") resistSecondarySettings();
    for (auto *chn : channels) chn->muteCSound(true);
    nebio::osc_open(oscPort);
    control_mode = "programs";
    saveInstrument();
}

void ProgControlHandler::sendProgMessages(const std::vector<ControlChannel *> &chans) {
    bool full = now - prog_resend_time >= PROG_RESEND_MS;
    if (full) prog_resend_time = now;
    for (auto *chn : chans) {
        if (!sendsControl(chn->name)) continue;
        auto it = bindings.find(chn->name);
        if (it == bindings.end()) continue;
        Value value = chn->getValue();
        for (auto &t : it->second) {
            double out = scale(value, F(t.lo), F(t.hi), t.curve);
            auto sent = prog_sent.find(t.path);
            if (full || sent == prog_sent.end() || sent->second != out) {
                nebio::osc_send(t.path, out);
                prog_sent[t.path] = out;
            }
        }
    }
    sendPages(full);
}

void ProgControlHandler::updateAll() {
    countUpdateAll();
    shiftReg_.update();
    handleSourceHold();

    if (control_mode == "secondary controls") {
        std::vector<ControlChannel *> all(channels);
        all.insert(all.end(), altchannels.begin(), altchannels.end());
        for (auto *chn : all) chn->update();
        sendProgMessages(all);
        setInputLevel(getAltValue("speed_alt"));
    } else if (control_mode == "instr selector") {
        updateInstrSelector();
    } else {
        updateCvAssign();
        updateHolds();
        for (auto *chn : channels) {
            if (chn->name != "sourcegate") chn->setIgnoreHID(buttonBlocked(chn->name));
            chn->update();
        }
        sendProgMessages(channels);
    }
}

}  // namespace neb
