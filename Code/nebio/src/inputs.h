// inputs.h - input thread: shift register, gate/click GPIOs, encoders, ADCs.
//
// The thread scans at 1 kHz (ADC every 2nd tick) by default; both rates can be
// changed at run time with setRates(). Python takes snapshots;
// every bit that changes between two snapshots is stretched so Python sees
// the press/pulse for at least one snapshot, in order.
#pragma once

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <thread>
#include <vector>

#include "adc.h"
#include "gpio.h"

namespace nebio {

// Debounce like shiftregister.py: the value is accepted after `need`
// consecutive identical reads following a change. need = 0 -> no debounce.
struct Debounce {
    int need = 0;
    int raw = -1;
    int count = 0;
    int stable = 0;
    int feed(int v);
};

// Remembers transitions Python has not seen yet (max one full pulse queued).
struct StretchBit {
    int current = 0;
    int reported = 0;
    int pending = 0;
    void reset(int v);
    void transition(int v);
    int consume();
};

// Rotary encoder, same 3-state sequence check as encoder.py (VALID_SEQ_3).
struct Encoder {
    unsigned pinA = 0;  // bit 0 of the state (encoder.py swaps the constructor pins)
    unsigned pinB = 0;  // bit 1
    int hist[3] = {0, 0, 0};
    int histLen = 0;
    std::atomic<int> steps{0};
    void reset(int state);
    void update(int state);
};

class Inputs {
public:
    static Inputs &instance();

    int init();
    void shutdown();
    bool running() const { return running_; }

    long long snapshot();
    int srBits() const;
    int gpioLevel(int pin) const;
    int adcCode(int device, int channel) const;
    int encoderId(int pinA, int pinB) const;
    int encoderSteps(int id);
    void setEol(int high);
    void stats(char *buf, size_t len);

    // Scan rate (100-2000 Hz, encoders are read every scan), digital rate
    // (shift register, clicks, polled gates) and ADC rate, both <= scan rate
    // and rounded to every nth scan. Takes effect on the next scan.
    // 0 = ok, -1 = invalid.
    int setRates(int scanHz, int digitalHz, int adcHz);
    int scanHz() const;
    int digitalHz() const;
    int adcHz() const;

    // Fast GPIO: shift register and polled pins through /dev/gpiomem instead
    // of libgpiod (see gpiomem.h). Switching on checks the board and the pin
    // functions and runs a self-check (fast and libgpiod reads compared) in the
    // input thread; on any problem it stays on libgpiod. 0 = ok, -1 = refused.
    int setFastGpio(bool on);
    bool fastGpio() const { return fastGpio_.load(std::memory_order_relaxed); }

private:
    Inputs() = default;
    void run();
    void runEdges();
    bool readShiftRegister(uint8_t &bits);
    bool readShiftRegisterFast(uint8_t &bits);
    void readPolledFast(const std::vector<unsigned> &pins, std::vector<int> &levels);
    bool fastSelfCheck();
    int pinSlot(int pin) const;
    void applyDebounce();

    // Hardware
    GpioLines srOut_;    // clock, latch
    GpioLines srIn_;     // data (no pull, like shiftregister.py)
    GpioLines polled_;   // clicks, encoders (+ gates if no edge events)
    GpioLines edges_;    // gates with edge events
    GpioLines eolOut_;
    Mcp3208 adc_[2];     // 0 = CV, 1 = POT

    std::thread thread_;
    std::thread edgeThread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_{false};
    bool gatesPolled_ = false;

    // Rates, see setRates(). Default: scan 1000 Hz, digital every scan
    // (1000 Hz), ADC every 2nd scan (500 Hz).
    std::atomic<int> scanPeriodUs_{1000};
    std::atomic<int> digitalEveryNth_{1};
    std::atomic<int> adcEveryNth_{2};

    // Fast GPIO, see setFastGpio(). Off by default.
    std::atomic<bool> fastGpio_{false};
    std::atomic<bool> fastRequest_{false};  // Python asks the input thread to self-check
    std::atomic<int> fastResult_{0};        // 1 ok, -1 failed

    // Live state, guarded by mutex_
    mutable std::mutex mutex_;
    std::condition_variable adcCv_;
    Debounce srDebounce_[8];
    StretchBit srBits_[8];
    static constexpr int kMaxPins = 32;
    int slotOfPin_[64];
    int slotPin_[kMaxPins];
    int slotCount_ = 0;
    Debounce pinDebounce_[kMaxPins];
    StretchBit pinBits_[kMaxPins];
    uint16_t adcLive_[2][8] = {};
    uint64_t adcGen_ = 0;

    // Last snapshot, guarded by mutex_
    int snapSr_ = 0;
    int snapPin_[kMaxPins] = {};
    uint16_t snapAdc_[2][8] = {};
    uint64_t snapAdcGen_ = 0;
    long long snapCount_ = 0;

    Encoder enc_[2];

    // Stats
    std::atomic<uint64_t> scans_{0};
    std::atomic<uint64_t> snapshots_{0};
    std::atomic<int64_t> worstScanUs_{0};
    uint64_t lastStatScans_ = 0;
    uint64_t lastStatSnaps_ = 0;
    int64_t lastStatNs_ = 0;
};

}  // namespace nebio
