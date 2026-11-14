// controlhandlerPD.py: the Pure Data bank. Every channel goes to Pd as a
// "name value;" text message over TCP ([netreceive 3000]).
#pragma once

#include <map>
#include <string>
#include <vector>

#include "controlhandler.h"
#include "senders.h"

namespace neb {

// Until the patch answers "nebready" with "ready", everything is resent this
// often (with "nebready"): a patch without the answer still gets all values.
constexpr int PD_RESEND_MS = 1000;

class PDControlHandler : public ControlHandler {
public:
    PDControlHandler(Csound *csound, const Value &numberFiles, const OrderedDict *configData,
                     std::string instr = "a_granularlooper", std::string bank = "instr",
                     HandlerEnv env = HandlerEnv());

    void closeSockets() override;
    void enterPureDataMode();
    void enterNormalMode() override { enterPureDataMode(); }
    void enterSecondaryMode() override;
    // The patch's "ready" gets everything once, then only changes. A failed
    // send forgets what was sent and that it was ready, so everything goes again.
    void sendPdMessages(const std::vector<ControlChannel *> &chans);
    void updateAll() override;

    PdSend pdSock;
    std::map<std::string, Value> pd_sent;  // Pd gets the value as Python prints it: int or float
    long long pd_resend_time = 0;
    bool pd_ready = false;
};

}  // namespace neb
