// controlhandlerPD.py: the Pure Data bank. Every channel goes to Pd as OSC on
// UDP port 3000 ("/start 0.5", read by [netreceive -u -b 3000] -> [oscparse]
// -> [list trim]).
#pragma once

#include <map>
#include <string>
#include <vector>

#include "controlhandler.h"

namespace neb {

constexpr int PD_PORT = 3000;

class PDControlHandler : public ControlHandler {
public:
    PDControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                     std::string instr = "a_granularlooper", std::string bank = "instr",
                     HandlerEnv env = HandlerEnv());

    void closeSockets() override;
    void enterPureDataMode();
    void enterNormalMode() override { enterPureDataMode(); }
    // nebulae.py starts the handler once Pd listens: everything goes on the
    // first pass, then only changes.
    void sendPdMessages(const std::vector<ControlChannel *> &chans);
    void updateAll() override;

    std::map<std::string, Value> pd_sent;  // a change is as Python sees it: 1 == 1.0
};

}  // namespace neb
