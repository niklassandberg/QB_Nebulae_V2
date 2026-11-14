// pdsender.py and scsender.py: the PdSend / ScSend interfaces the handlers use,
// over nebio's PD (TCP text) and SC (OSC) links.
#pragma once

#include <string>
#include <vector>

#include "classlogger.h"
#include "pyvalue.h"

namespace neb {

class PdSend {
public:
    static constexpr int sport = 3000;
    void connect();  // in the background, retries until PD answers or close()
    bool send(const std::vector<Value> &msgs);  // true when the messages went out
    // True when the patch sent "ready" back since the last call: it answers
    // "nebready" with [send ready( into its [netreceive 3000] once set up.
    bool takeReady();
    std::string format(const std::string &target, const Value &val) const { return target + " " + pyStr(val); }
    void close();
    bool is_connected();

    bool warned = false;

private:
    Logger log_{"PdSend"};
};

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
