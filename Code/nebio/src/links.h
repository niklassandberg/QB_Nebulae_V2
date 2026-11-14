// links.h - OSC over UDP (liblo): to sclang (ScLink), and to the engine of
// the Pd or programs bank (OscLink).
#pragma once

#include <lo/lo.h>

#include <atomic>
#include <map>
#include <mutex>
#include <string>

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
    void sendPathFloat(const char *path, double value);
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
    static int onLed(const char *, const char *, lo_arg **, int, lo_message, void *);
    static int onOther(const char *, const char *, lo_arg **, int, lo_message, void *);
    static void onError(int num, const char *msg, const char *where);

    std::mutex mutex_;
    lo_address target_ = nullptr;
    lo_server_thread server_ = nullptr;
    std::map<std::string, Last> last_;
};

// The engine of the Pd or programs bank: OSC to 127.0.0.1 (Pd on 3000, a
// program on its .prog's oscport), a float to any path. No change check
// here: Python sends only what changed.
class OscLink {
public:
    static OscLink &instance();

    bool open(int port);
    void close();
    bool isOpen() const { return target_ != nullptr; }
    void sendFloat(const char *path, double value);

private:
    OscLink() = default;

    std::mutex mutex_;
    lo_address target_ = nullptr;
};

}  // namespace nebio
