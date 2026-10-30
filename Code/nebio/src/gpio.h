// gpio.h - thin RAII wrapper around libgpiod v2 line requests.
#pragma once

#include <gpiod.h>

#include <cstdint>
#include <mutex>
#include <vector>

namespace nebio {

// One open /dev/gpiochipN, shared by inputs and LEDs.
class GpioChip {
public:
    static GpioChip &instance();
    gpiod_chip *get();  // opens lazily, nullptr on failure

private:
    GpioChip() = default;
    ~GpioChip();
    std::mutex mutex_;
    gpiod_chip *chip_ = nullptr;
};

enum class Bias { Off, PullUp };  // Off = pull disabled, like RPi.GPIO PUD_OFF

// A set of lines requested together with the same settings.
class GpioLines {
public:
    GpioLines() = default;
    ~GpioLines();
    GpioLines(const GpioLines &) = delete;
    GpioLines &operator=(const GpioLines &) = delete;

    bool requestInputs(const std::vector<unsigned> &pins, Bias bias, bool edgeEvents);
    bool requestOutputs(const std::vector<unsigned> &pins, int initialValue);
    void release();

    bool ok() const { return req_ != nullptr; }
    int get(unsigned pin) const;            // 0/1, -1 on error
    bool getAll(std::vector<int> &values);  // in request order
    void set(unsigned pin, int value);

    // Edge events (only for requestInputs(..., edgeEvents=true)).
    // Waits up to timeoutNs; returns number of events read, 0 on timeout, -1 on error.
    struct Edge {
        unsigned pin;
        int level;
    };
    int waitEdges(int64_t timeoutNs, std::vector<Edge> &out);

    const std::vector<unsigned> &pins() const { return pins_; }

private:
    bool request(const std::vector<unsigned> &pins, gpiod_line_settings *settings);
    gpiod_line_request *req_ = nullptr;
    gpiod_edge_event_buffer *events_ = nullptr;
    std::vector<unsigned> pins_;
};

}  // namespace nebio
