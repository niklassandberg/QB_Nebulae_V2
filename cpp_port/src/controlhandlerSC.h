// controlhandlerSC.py: the SuperCollider bank. Every channel goes to sclang
// as /neb/<name>; encoder pages go straight to their scsynth bus paths.
#pragma once

#include <string>
#include <vector>

#include "controlhandlerEncoders.h"
#include "senders.h"

namespace neb {

class SCControlHandler : public EncoderControlHandler {
public:
    SCControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                     std::string instr = "a_granularlooper", std::string bank = "instr",
                     HandlerEnv env = HandlerEnv());

    void closeSockets() override;
    // sclang writes the patch's own values (<patch>.state) 1 s after a change:
    // /neb/save writes them now.
    void saveInstrument() override;
    void sendControl(const std::string &name, const Value &value) override { scSock.send(name, value); }
    void sendPath(const std::string &path, double value) override;
    std::vector<ControlChannel *> rawChannels() const;
    void setConfig(const NebConfig &config, const std::string &pages_path) override;
    bool isRaw(const std::string &name) override;
    void setRawActive(bool state);  // also routes the clicks of both encoders to sclang
    void startRawEncoders();
    void enterSuperColliderMode();
    void enterNormalMode() override { enterSuperColliderMode(); }
    void enterSecondaryMode() override;
    void enterInstrSelMode() override;
    void updateAll() override;
    void startScOscServer();
    void waitOnScLang();
    void synthIsUpStatus();
    // A loadScFile sent before sclang listens is lost: the bank stays silent.
    bool waitForSclangPort(double timeout = 30.0);
    void loadScSynth(const Value &patch);
    void closeScSynthProcess();
    void sendScOscMessages();

    ScSend scSock;
    bool rawReady = false;
    // Where waitForSclangPort() looks for sclang's UDP port.
    std::vector<std::string> udpTables = {"/proc/net/udp", "/proc/net/udp6"};

private:
    std::vector<std::unique_ptr<ControlChannel>> rawOwned_;
};

}  // namespace neb
