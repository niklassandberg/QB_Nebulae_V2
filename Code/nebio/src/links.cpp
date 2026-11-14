#include "links.h"

#include <errno.h>

#include <cstdint>
#include <cstring>

#include "leds.h"
#include "log.h"

namespace nebio {

namespace {
constexpr const char *kScHost = "127.0.0.1";
constexpr const char *kScSendPort = "3010";    // scsender.py rPort
constexpr const char *kScListenPort = "3011";  // scsender.py sPort

// Index = NEBIO_RGB_* id
constexpr const char *kLedPath[4] = {"/sc/led/pitch_pos", "/sc/led/pitch_neg",
                                     "/sc/led/speed_pos", "/sc/led/speed_neg"};

// OSC number argument as double (sclang sends f, i or d), false if it is not a number.
bool argNumber(const char *types, lo_arg **argv, int argc, int i, double &out) {
    if (i >= argc || !types) return false;
    switch (types[i]) {
        case 'f': out = argv[i]->f; return true;
        case 'i': out = argv[i]->i; return true;
        case 'd': out = argv[i]->d; return true;
        case 'h': out = static_cast<double>(argv[i]->h); return true;
        default: return false;
    }
}
}  // namespace

// ---- SuperCollider -------------------------------------------------------

ScLink &ScLink::instance() {
    static ScLink *link = new ScLink();  // never destroyed, see GpioChip
    return *link;
}

bool ScLink::openSender() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (target_) return true;
    target_ = lo_address_new(kScHost, kScSendPort);
    if (!target_) logError("could not create OSC address %s:%s", kScHost, kScSendPort);
    return target_ != nullptr;
}

void ScLink::closeSender() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (target_) lo_address_free(target_);
    target_ = nullptr;
}

void ScLink::onError(int num, const char *msg, const char *where) {
    logError("OSC server error %d in %s: %s", num, where ? where : "?", msg ? msg : "?");
}

int ScLink::onSynthUp(const char *, const char *, lo_arg **, int, lo_message, void *) {
    instance().synthIsUp = true;
    return 0;
}

int ScLink::onReady(const char *, const char *, lo_arg **, int, lo_message, void *) {
    instance().handshake = true;
    return 0;
}

int ScLink::onLed(const char *path, const char *types, lo_arg **argv, int argc, lo_message,
                  void *user) {
    int id = static_cast<int>(reinterpret_cast<intptr_t>(user));
    double rgb[3];
    for (int k = 0; k < 3; ++k) {
        if (!argNumber(types, argv, argc, k, rgb[k])) {
            logError("%s: expected r g b (0-4095)", path);
            return 0;
        }
    }
    Leds::instance().setScRgb(id, rgb[0], rgb[1], rgb[2]);
    return 0;
}

int ScLink::onOther(const char *path, const char *, lo_arg **, int, lo_message, void *) {
    logError("OSC message not handled: %s", path ? path : "?");
    return 0;
}

bool ScLink::startListener() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (server_) return true;
    server_ = lo_server_thread_new(kScListenPort, &ScLink::onError);
    if (!server_) {
        logError("could not listen for OSC on port %s", kScListenPort);
        return false;
    }
    lo_server_thread_add_method(server_, "/sc/up", nullptr, &ScLink::onSynthUp, nullptr);
    lo_server_thread_add_method(server_, "/neb/ready", nullptr, &ScLink::onReady, nullptr);
    for (intptr_t id = 0; id < 4; ++id)
        lo_server_thread_add_method(server_, kLedPath[id], nullptr, &ScLink::onLed,
                                    reinterpret_cast<void *>(id));
    lo_server_thread_add_method(server_, nullptr, nullptr, &ScLink::onOther, nullptr);
    if (lo_server_thread_start(server_) != 0) {
        logError("could not start OSC listener thread");
        lo_server_thread_free(server_);
        server_ = nullptr;
        return false;
    }
    return true;
}

void ScLink::stopListener() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!server_) return;
    lo_server_thread_stop(server_);
    lo_server_thread_free(server_);
    server_ = nullptr;
}

bool ScLink::changed(const char *name, const Last &value) {
    auto it = last_.find(name);
    if (it != last_.end()) {
        const Last &old = it->second;
        // Same rule as Python's ==: 1 == 1.0, numbers never equal strings.
        if (old.isString == value.isString &&
            (value.isString ? old.text == value.text : old.number == value.number))
            return false;
    }
    last_[name] = value;
    return true;
}

void ScLink::send(const char *name, lo_message msg) {
    std::string path = std::string("/neb/") + name;
    if (target_ && lo_send_message(target_, path.c_str(), msg) < 0)
        logError("could not send %s: %s", path.c_str(), lo_address_errstr(target_));
    lo_message_free(msg);
}

void ScLink::sendInt(const char *name, int value) {
    std::lock_guard<std::mutex> lock(mutex_);
    Last v;
    v.number = value;
    if (!changed(name, v)) return;
    lo_message m = lo_message_new();
    lo_message_add_int32(m, value);
    send(name, m);
}

void ScLink::sendFloat(const char *name, double value) {
    std::lock_guard<std::mutex> lock(mutex_);
    Last v;
    v.number = value;
    if (!changed(name, v)) return;
    lo_message m = lo_message_new();
    lo_message_add_float(m, static_cast<float>(value));
    send(name, m);
}

void ScLink::sendBool(const char *name, bool value) {
    std::lock_guard<std::mutex> lock(mutex_);
    Last v;
    v.number = value ? 1 : 0;
    if (!changed(name, v)) return;
    lo_message m = lo_message_new();
    if (value)
        lo_message_add_true(m);
    else
        lo_message_add_false(m);
    send(name, m);
}

void ScLink::sendString(const char *name, const char *value) {
    std::lock_guard<std::mutex> lock(mutex_);
    Last v;
    v.isString = true;
    v.text = value ? value : "";
    if (!changed(name, v)) return;
    lo_message m = lo_message_new();
    lo_message_add_string(m, v.text.c_str());
    send(name, m);
}

void ScLink::sendPathInt(const char *path, int value) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!target_) return;
    if (lo_send(target_, path, "i", value) < 0)
        logError("could not send %s: %s", path, lo_address_errstr(target_));
}

void ScLink::sendPathFloat(const char *path, double value) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!target_) return;
    if (lo_send(target_, path, "f", static_cast<float>(value)) < 0)
        logError("could not send %s: %s", path, lo_address_errstr(target_));
}

void ScLink::clearCache() {
    std::lock_guard<std::mutex> lock(mutex_);
    last_.clear();
}

// ---- Programs bank -------------------------------------------------------

OscLink &OscLink::instance() {
    static OscLink *link = new OscLink();  // never destroyed, see GpioChip
    return *link;
}

bool OscLink::open(int port) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (target_) lo_address_free(target_);
    std::string p = std::to_string(port);
    target_ = lo_address_new(kScHost, p.c_str());
    if (!target_) logError("could not create OSC address %s:%s", kScHost, p.c_str());
    return target_ != nullptr;
}

void OscLink::close() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (target_) lo_address_free(target_);
    target_ = nullptr;
}

void OscLink::sendFloat(const char *path, double value) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!target_) return;
    if (lo_send(target_, path, "f", static_cast<float>(value)) < 0)
        logError("could not send %s: %s", path, lo_address_errstr(target_));
}

}  // namespace nebio
