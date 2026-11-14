// scsender.py: the ScSend interface the SC handler uses, over nebio's SC
// (OSC) link.
#pragma once

#include <string>
#include <vector>

#include "classlogger.h"
#include "pyvalue.h"

namespace neb {

class ScSend {
public:
    static constexpr int rPort = 3010;  // SC server port
    static constexpr int sPort = 3011;  // this server port

    bool synthIsUpStatus();
    bool waitSynthIsUp(double timeout);  // true as soon as sclang sent /sc/up
    void setSynthIsDown();
    void pingLoaded();
    bool sclangHandshakeStatus();
    void zeroSclangHandshake();
    void connectSender();
    void clear();
    void send(const std::string &what, const Value &value);  // only changed values go out
    bool startListener();
    void addResiver(const std::string &address);  // only /sc/up and /neb/ready are handled
    void close();
    bool is_connected();
    void close_client();
    void close_server();

private:
    Logger log_{"ScSend"};
};

}  // namespace neb
