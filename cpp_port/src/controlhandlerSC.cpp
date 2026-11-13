#include "controlhandlerSC.h"

#include <cstdio>
#include <fstream>
#include <sstream>

#include "nebio.h"

namespace neb {

SCControlHandler::SCControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                                   std::string instr, std::string bank, HandlerEnv env)
    : EncoderControlHandler(csound, numberFiles, configData, std::move(instr), std::move(bank), std::move(env)) {
    for (auto &name : ENCODERS) {
        rawOwned_.push_back(std::make_unique<ControlChannel>(nullptr, name, I(0), "rawencoder"));
        encoders[name]["rawencoder"] = rawOwned_.back().get();
    }
}

void SCControlHandler::closeSockets() {
    setRawActive(false);
    saveInstrument();
    EncoderControlHandler::closeSockets();
    if (scSock.is_connected()) scSock.close();
}

void SCControlHandler::saveInstrument() {
    EncoderControlHandler::saveInstrument();
    if (scSock.is_connected()) scSock.send("save", I(1));
}

void SCControlHandler::sendPath(const std::string &path, double value) { nebio::sc_send_path_float(path, value); }

std::vector<ControlChannel *> SCControlHandler::rawChannels() const {
    std::vector<ControlChannel *> out;
    for (auto *chn : channels)
        if (chn->source == "rawencoder") out.push_back(chn);
    return out;
}

void SCControlHandler::setConfig(const NebConfig &config, const std::string &pages_path) {
    setRawActive(false);
    rawReady = false;
    nebio::led_clear_sc();  // the old patch's LED colours
    EncoderControlHandler::setConfig(config, pages_path);
}

bool SCControlHandler::isRaw(const std::string &name) {
    auto it = channeldict.find(name);
    return it != channeldict.end() && it->second->source == "rawencoder";
}

void SCControlHandler::setRawActive(bool state) {
    for (auto *chn : rawChannels()) chn->raw()->setActive(state);
    for (auto &name : ENCODERS) nebio::encoder_set_click(name, state);
}

void SCControlHandler::startRawEncoders() {
    rawReady = true;
    page_sent.clear();  // the patch's NebPage buses exist now
    if (control_mode == "supercollider") setRawActive(true);
}

void SCControlHandler::enterSuperColliderMode() {
    prev_control_mode = control_mode;
    for (auto *chn : channels) chn->muteCSound(true);
    if (control_mode == "secondary controls") resistSecondarySettings();
    control_mode = "supercollider";
    saveInstrument();
    altChannel("source_alt").setValue(I(0));
    if (!scSock.is_connected()) {
        NLOG(log_, INFO, "enterSuperColliderMode: connecting to SC socket");
        scSock.connectSender();
    }
    for (auto *chn : channels)
        NLOG(log_, INFO, "enterSuperColliderMode: %s value %s", chn->name.c_str(), pyStr(chn->getValue()).c_str());
    if (rawReady) setRawActive(true);
}

void SCControlHandler::enterSecondaryMode() {
    if (!scSock.is_connected() && control_mode == "supercollider") {
        NLOG(log_, INFO, "enterSecondaryMode: connecting to SC socket");
        scSock.connectSender();
    }
    setRawActive(false);
    EncoderControlHandler::enterSecondaryMode();
}

void SCControlHandler::enterInstrSelMode() {
    setRawActive(false);
    EncoderControlHandler::enterInstrSelMode();
}

void SCControlHandler::updateAll() {
    countUpdateAll();
    shiftReg_.update();
    handleSourceHold();

    if (control_mode == "secondary controls") {
        sendScOscMessages();  // all channels and alt channels
        setInputLevel(getAltValue("speed_alt"));
    } else if (control_mode == "instr selector") {
        updateInstrSelector();
    } else {
        updateCvAssign();
        updateHolds();
        for (auto *chn : channels) {
            if (chn->source == "rawencoder") continue;  // nebio and sclang handle it
            if (chn->name != "sourcegate") chn->setIgnoreHID(buttonBlocked(chn->name));
            chn->update();
            if (sendsControl(chn->name)) scSock.send(chn->name, chn->getValue());
        }
        sendPages();
    }
}

void SCControlHandler::startScOscServer() {
    NLOG(log_, INFO, "startScOscServer");
    scSock.connectSender();
    scSock.addResiver("/sc/up");
    scSock.addResiver("/neb/ready");
    scSock.startListener();
}

void SCControlHandler::waitOnScLang() {
    NLOG(log_, INFO, "waitOnScLang");
    scSock.zeroSclangHandshake();
    int retries = 0;
    while (!scSock.sclangHandshakeStatus()) {
        NLOG(log_, INFO, "sclang is not ready yet, waiting...");
        scSock.send("ready", I(0));
        ++retries;
        if (retries > 50) {
            NLOG(log_, INFO, "Timeout waiting for sclang to be ready!");
            break;
        }
        clock().sleep(0.1);
    }
    if (retries >= 50) NLOG(log_, INFO, "sclang is not ready after 50 retries!");
}

void SCControlHandler::synthIsUpStatus() {
    try {
        int retries = 0;
        NLOG(log_, INFO, "Waiting for synth handshake...");
        while (!scSock.waitSynthIsUp(0.5)) {
            NLOG(log_, INFO, "synth is not up yet, pinging SC...");
            scSock.pingLoaded();
            ++retries;
            if (retries > 50) {
                NLOG(log_, ERROR, "Synth did not respond after 50 pings, giving up!");
                return;
            }
        }
        NLOG(log_, INFO, "Synth is up!");
    } catch (const std::exception &e) {
        NLOG(log_, ERROR, "Error in synthIsUpStatus(): %s", e.what());
    }
}

namespace {

// A row's local address (second field) ends in the port; a row with fewer
// fields ends the table, as Python's IndexError leaves its loop.
bool tableHasPort(const std::string &table, const std::string &port) {
    std::ifstream f(table);
    if (!f) return false;
    std::string line;
    if (!std::getline(f, line)) return false;  // header
    while (std::getline(f, line)) {
        std::istringstream fields(line);
        std::string first, local;
        if (!(fields >> first >> local)) return false;
        if (local.size() >= port.size() && local.compare(local.size() - port.size(), port.size(), port) == 0)
            return true;
    }
    return false;
}

}  // namespace

bool SCControlHandler::waitForSclangPort(double timeout) {
    NLOG(log_, INFO, "wait until sclang listens on port %d", ScSend::rPort);
    char port[16];
    std::snprintf(port, sizeof port, ":%04X", ScSend::rPort);
    double start = clock().time();
    while (clock().time() - start < timeout) {
        for (auto &table : udpTables)
            if (tableHasPort(table, port)) return true;
        clock().sleep(0.1);
    }
    NLOG(log_, WARNING, "sclang does not listen on %d after %.0f s, loading anyway", ScSend::rPort, timeout);
    return false;
}

void SCControlHandler::loadScSynth(const Value &patch) {
    scSock.setSynthIsDown();
    waitForSclangPort();
    scSock.send("loadScFile", patch);
    synthIsUpStatus();
}

void SCControlHandler::closeScSynthProcess() {
    try {
        scSock.send("quit", I(0));
    } catch (const std::exception &e) {
        NLOG(log_, ERROR, "Error in closeScSynthProcess(): %s", e.what());
    }
}

void SCControlHandler::sendScOscMessages() {
    for (auto *chn : channels) {
        if (chn->source == "rawencoder") continue;  // nebio and sclang handle it
        chn->update();
        if (sendsControl(chn->name)) scSock.send(chn->name, chn->getValue());
    }
    for (auto *chn : altchannels) {
        chn->update();
        scSock.send(chn->name, chn->getValue());
    }
    sendPages();
}

}  // namespace neb
