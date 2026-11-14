#include "controlhandlerPD.h"

namespace neb {

PDControlHandler::PDControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                                   std::string instr, std::string bank, HandlerEnv env)
    : ControlHandler(csound, numberFiles, configData, std::move(instr), std::move(bank), std::move(env)) {}

void PDControlHandler::closeSockets() {
    ControlHandler::closeSockets();
    if (pdSock.is_connected()) pdSock.close();
}

void PDControlHandler::enterPureDataMode() {
    prev_control_mode = control_mode;
    if (control_mode == "secondary controls") resistSecondarySettings();
    for (auto *chn : channels) chn->muteCSound(true);
    if (!pdSock.is_connected()) {
        NLOG(log_, INFO, "enterPureDataMode: connecting to PD socket");
        pdSock.connect();
    }
    control_mode = "puredata";
    saveInstrument();
}

void PDControlHandler::enterSecondaryMode() {
    if (!pdSock.is_connected() && control_mode == "puredata") {
        NLOG(log_, INFO, "enterSecondaryMode: connecting to PD socket");
        pdSock.connect();
    }
    ControlHandler::enterSecondaryMode();
}

void PDControlHandler::sendPdMessages(const std::vector<ControlChannel *> &chans) {
    if (!pd_ready && pdSock.takeReady()) {
        NLOG(log_, INFO, "pd: the patch is ready");
        pd_ready = true;
        pd_sent.clear();
    }
    bool full = !pd_ready && now - pd_resend_time >= PD_RESEND_MS;
    std::vector<Value> msgs;
    std::map<std::string, Value> changed;
    for (auto *chn : chans) {
        Value value = chn->getValue();
        auto it = pd_sent.find(chn->name);
        if (full || it == pd_sent.end() || it->second != value) {
            msgs.push_back(Value::str(chn->name + " " + pyStr(value)));
            changed[chn->name] = value;
        }
    }
    if (full) msgs.push_back(Value::str("nebready"));
    if (msgs.empty()) return;
    try {
        if (pdSock.send(msgs)) {
            for (auto &[name, value] : changed) pd_sent[name] = value;
            if (full) pd_resend_time = now;
        } else {
            pd_sent.clear();
            pd_ready = false;
        }
    } catch (const std::exception &e) {
        pd_sent.clear();
        pd_ready = false;
        NLOG(log_, ERROR, "pd: could not send messages to PD (%s): %s",
             pdSock.is_connected() ? "connected" : "no connection", e.what());
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
