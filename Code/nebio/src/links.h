// links.h - communication with SuperCollider (OSC/UDP via liblo) and
// Pure Data (text over TCP). Same wire protocol as scsender.py / pdsender.py.
#pragma once

#include <lo/lo.h>

#include <atomic>
#include <map>
#include <mutex>
#include <string>
#include <thread>

namespace nebio {

class ScLink {
public:
    static ScLink &instance();

    bool openSender();
    void closeSender();
    bool senderOpen() const { return target_ != nullptr; }
    bool startListener();
    void stopListener();
    bool listenerRunning() const { return server_ != nullptr; }

    void sendInt(const char *name, int value);
    void sendFloat(const char *name, double value);
    void sendBool(const char *name, bool value);
    void sendString(const char *name, const char *value);
    void sendPathInt(const char *path, int value);
    void clearCache();

    std::atomic<bool> synthIsUp{false};
    std::atomic<bool> handshake{false};

private:
    ScLink() = default;
    struct Last {
        bool isString = false;
        double number = 0;
        std::string text;
    };
    // True if the value differs from the last one (and remembers it).
    bool changed(const char *name, const Last &value);
    void send(const char *name, lo_message msg);

    static int onSynthUp(const char *, const char *, lo_arg **, int, lo_message, void *);
    static int onReady(const char *, const char *, lo_arg **, int, lo_message, void *);
    static int onOther(const char *, const char *, lo_arg **, int, lo_message, void *);
    static void onError(int num, const char *msg, const char *where);

    std::mutex mutex_;
    lo_address target_ = nullptr;
    lo_server_thread server_ = nullptr;
    std::map<std::string, Last> last_;
};

class PdLink {
public:
    static PdLink &instance();

    void connect();  // background, retries
    void close();
    bool connected() const { return connected_; }
    bool send(const char *data, int len);

private:
    PdLink() = default;
    void runConnect(unsigned generation);

    std::mutex mutex_;
    int fd_ = -1;
    std::atomic<bool> connected_{false};
    std::atomic<bool> connecting_{false};
    std::atomic<unsigned> generation_{0};
    std::thread thread_;
};

}  // namespace nebio
