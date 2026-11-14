#include "controlhandlerPD.h"

#include "nebio.h"

namespace neb {

PDControlHandler::PDControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                                   std::string instr, std::string bank, HandlerEnv env)
    : ControlHandler(csound, numberFiles, configData, std::move(instr), std::move(bank), std::move(env)) {}

void PDControlHandler::closeSockets() {
    ControlHandler::closeSockets();
    nebio::osc_close();
}

void PDControlHandler::enterPureDataMode() {
    prev_control_mode = control_mode;
    if (control_mode == "secondary controls") resistSecondarySettings();
    for (auto *chn : channels) chn->muteCSound(true);
    nebio::osc_open(PD_PORT);
    control_mode = "puredata";
    saveInstrument();
}

void PDControlHandler::sendPdMessages(const std::vector<ControlChannel *> &chans) {
    for (auto *chn : chans) {
        Value value = chn->getValue();
        auto it = pd_sent.find(chn->name);
        if (it == pd_sent.end() || it->second != value) {
            nebio::osc_send("/" + chn->name, value.number());
            pd_sent[chn->name] = value;
        }
    }
}

void PDControlHandler::updateAll() {
    countUpdateAll();
    shiftReg_.update();
    handleSourceHold();

    if (control_mode == "secondary controls") {
        clock().sleep(0.001);
        std::vector<ControlChannel *> all(channels);
        all.insert(all.end(), altchannels.begin(), altchannels.end());
        for (auto *chn : all) chn->update();
        sendPdMessages(all);
        setInputLevel(getAltValue("speed_alt"));
    } else if (control_mode == "instr selector") {
        updateInstrSelector();
    } else {
        clock().sleep(0.001);
        for (auto *chn : channels) {
            if (chn->name != "sourcegate") chn->setIgnoreHID(false);
            chn->update();
        }
        sendPdMessages(channels);
    }
}

}  // namespace neb
