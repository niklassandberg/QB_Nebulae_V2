#include "senders.h"

#include "nebio.h"

namespace neb {

bool ScSend::synthIsUpStatus() {
    bool status = nebioC().sc_synth_is_up() != 0;
    NLOG(log_, DEBUG, "synthIsUpStatus=%s", status ? "True" : "False");
    return status;
}

bool ScSend::waitSynthIsUp(double timeout) {
    double end = clock().time() + timeout;
    while (true) {
        if (nebioC().sc_synth_is_up()) return true;
        if (clock().time() >= end) return false;
        clock().sleep(0.01);
    }
}

void ScSend::setSynthIsDown() {
    NLOG(log_, DEBUG, "SET SYNTH TO DOWN!!!");
    nebioC().sc_set_synth_down();
    nebio::sc_forget_sent();
}

void ScSend::pingLoaded() {
    if (nebioC().sc_sender_open()) {
        NLOG(log_, DEBUG, "sending /neb/hasbeenloaded ping");
        nebioC().sc_send_path_int("/neb/hasbeenloaded", 0);
    }
}

bool ScSend::sclangHandshakeStatus() {
    bool status = nebioC().sc_handshake() != 0;
    NLOG(log_, DEBUG, "sclangHandshakeStatus=%s", status ? "True" : "False");
    return status;
}

void ScSend::zeroSclangHandshake() {
    NLOG(log_, DEBUG, "sclang handshake zero!");
    nebioC().sc_zero_handshake();
}

void ScSend::connectSender() {
    if (nebioC().sc_sender_open()) {
        NLOG(log_, INFO, "No need to connect, is connected");
        return;
    }
    NLOG(log_, INFO, "Connecting");
    if (nebioC().sc_open_sender() == 0)
        NLOG(log_, INFO, "Sending to 127.0.0.1:%d", rPort);
    else
        NLOG(log_, ERROR, "Connection failed: %s", nebio::last_error().c_str());
}

void ScSend::clear() {
    nebioC().sc_clear_cache();
    nebio::sc_forget_sent();
}

void ScSend::send(const std::string &what, const Value &value) { nebio::sc_send(what, value); }

bool ScSend::startListener() {
    if (nebioC().sc_listener_running()) return true;
    if (nebioC().sc_start_listener() == 0) {
        NLOG(log_, INFO, "Listening for OSC on port %d", sPort);
        return true;
    }
    NLOG(log_, ERROR, "Failed to start OSC listener: %s", nebio::last_error().c_str());
    return false;
}

void ScSend::addResiver(const std::string &address) {
    if (address != "/sc/up" && address != "/neb/ready")
        NLOG(log_, ERROR, "OSC address %s is not handled by nebio", address.c_str());
}

void ScSend::close() {
    NLOG(log_, INFO, "Closing OSC server and client!!!!");
    close_client();
    close_server();
}

bool ScSend::is_connected() { return nebioC().sc_sender_open() || nebioC().sc_listener_running(); }

void ScSend::close_client() {
    if (nebioC().sc_sender_open()) {
        NLOG(log_, INFO, "Closing OSCclient");
        nebioC().sc_close_sender();
    } else {
        NLOG(log_, INFO, "OSC client is None!!!");
    }
}

void ScSend::close_server() {
    if (nebioC().sc_listener_running()) {
        NLOG(log_, INFO, "Closing OSC server");
        nebioC().sc_stop_listener();
    } else {
        NLOG(log_, INFO, "OSC server is None!!!");
    }
}

}  // namespace neb
