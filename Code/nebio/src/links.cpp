#include "links.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdint>
#include <cstring>

#include "leds.h"
#include "log.h"

namespace nebio {

namespace {
constexpr const char *kScHost = "127.0.0.1";
constexpr const char *kScSendPort = "3010";    // scsender.py rPort
constexpr const char *kScListenPort = "3011";  // scsender.py sPort
constexpr int kPdPort = 3000;                  // pdsender.py sport
constexpr int kPdConnectTimeoutMs = 200;
constexpr int kPdRetryMs = 250;

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

void ScLink::clearCache() {
    std::lock_guard<std::mutex> lock(mutex_);
    last_.clear();
}

// ---- Pure Data -----------------------------------------------------------

PdLink &PdLink::instance() {
    static PdLink *link = new PdLink();  // never destroyed, see GpioChip
    return *link;
}

void PdLink::connect() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (connected_ || connecting_) return;
    if (thread_.joinable()) thread_.join();
    connecting_ = true;
    thread_ = std::thread(&PdLink::runConnect, this, generation_.load());
}

void PdLink::runConnect(unsigned generation) {
    logInfo("connecting to PD on port %d", kPdPort);
    bool warned = false;
    while (generation_ == generation) {
        int fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) break;
        fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
        sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(kPdPort);
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        bool ok = false;
        if (::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0) {
            ok = true;
        } else if (errno == EINPROGRESS) {
            pollfd p = {fd, POLLOUT, 0};
            if (poll(&p, 1, kPdConnectTimeoutMs) == 1) {
                int err = 0;
                socklen_t len = sizeof(err);
                getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &len);
                ok = err == 0;
            }
        }
        if (ok) {
            std::lock_guard<std::mutex> lock(mutex_);
            if (generation_ != generation) {
                ::close(fd);
                break;
            }
            fd_ = fd;
            connected_ = true;
            logInfo("sending to PD on port %d", kPdPort);
            break;
        }
        ::close(fd);
        if (!warned) {
            logInfo("PD not reachable yet - open PD with [netreceive %d], retrying", kPdPort);
            warned = true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(kPdRetryMs));
    }
    connecting_ = false;
}

void PdLink::close() {
    ++generation_;  // stops a running connect loop
    std::thread t;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (fd_ >= 0) {
            logInfo("closing connection to PD");
            ::close(fd_);
        }
        fd_ = -1;
        connected_ = false;
        t = std::move(thread_);
    }
    if (t.joinable()) t.join();
}

bool PdLink::send(const char *data, int len) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (fd_ < 0) return false;
    ssize_t n = ::send(fd_, data, static_cast<size_t>(len), MSG_DONTWAIT | MSG_NOSIGNAL);
    if (n == len) return true;
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
        logError("PD is not reading, dropped %d bytes", len);
        return false;
    }
    if (n >= 0) {
        logError("PD send was cut short (%zd of %d bytes)", n, len);
        return false;
    }
    logError("could not send to PD: %s", std::strerror(errno));
    ::close(fd_);
    fd_ = -1;
    connected_ = false;
    return false;
}

}  // namespace nebio
