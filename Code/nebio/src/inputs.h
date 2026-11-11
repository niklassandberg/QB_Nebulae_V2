// Input thread: shift register, gate/click GPIOs, encoders, ADCs. A change
// between two snapshots is stretched so Python sees it at least once.
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

// Accepted after `need` identical reads; 0 = no debounce.
struct Debounce {
    int need = 0;
    int raw = -1;
    int count = 0;
    int stable = 0;
    int feed(int v);
};

// A polled gate as a Schmitt trigger: a change counts at once, then the pin
// is ignored for the hold-off, so a slow or noisy edge is one edge.
struct GateHoldoff {
    int stable = 1;
    int64_t untilNs = 0;
    int feed(int v, int64_t nowNs, int64_t holdNs);
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

// Rotary encoder with a 3-state sequence check.
struct Encoder {
    unsigned pinA = 0;  // bit 0 of the state
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
    int adcCodes(int *out, int n) const;
    int gpioLevels(int *out, int n) const;
    int encoderId(int pinA, int pinB) const;
    int encoderSteps(int id);
    // See nebio_encoder_set_raw / nebio_encoder_set_click.
    void setEncoderRaw(int id, bool on);
    bool encoderRaw(int id) const;
    void setEncoderClick(int id, bool on);
    void setEol(int high);
    void stats(char *buf, size_t len);

    // See nebio_set_input_rates.
    int setRates(int scanHz, int digitalHz, int adcHz);
    int scanHz() const;
    int digitalHz() const;
    int adcHz() const;

    // See nebio_set_fast_gpio.
    int setFastGpio(bool on);
    bool fastGpio() const { return fastGpio_.load(std::memory_order_relaxed); }

    // See nebio_set_gate_interrupts / nebio_set_gate_holdoff_us.
    int setGateInterrupts(bool on);
    bool gateInterrupts() const { return !gatesPolled_ && gateIrq_.load(std::memory_order_relaxed); }
    void setGateHoldoffUs(int us);
    int gateHoldoffUs() const { return gateHoldoffUs_.load(std::memory_order_relaxed); }

    // See nebio_set_scan_jitter / nebio_set_scan_trigger.
    void setScanJitter(double fraction);
    void setScanTrigger(bool external);
    void scanTrigger();

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
    bool clickPressed(int id) const;
    void sendRawEncoders(const int clickLevel[2]);
    void routeChanged(int id, bool clickBefore);
    bool readGates(const std::vector<unsigned> &polledPins, const std::vector<int> &levels,
                   int out[]);

    // Hardware
    GpioLines srOut_;    // clock, latch
    GpioLines srIn_;     // data (no pull)
    GpioLines polled_;   // clicks, encoders (+ gates if no edge events)
    GpioLines edges_;    // gates with edge events
    GpioLines eolOut_;
    Mcp3208 adc_[2];     // 0 = CV, 1 = POT

    std::thread thread_;
    std::thread edgeThread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_{false};
    bool gatesPolled_ = false;  // no edge events at all: gates always polled
    std::atomic<bool> gateIrq_{true};     // edge events, else polled with hold-off
    std::atomic<int> gateHoldoffUs_{5000};
    std::mutex gateSwitchMutex_;

    std::atomic<int> scanPeriodUs_{1000};
    std::atomic<int> digitalEveryNth_{1};
    std::atomic<int> adcEveryNth_{2};

    std::atomic<double> scanJitter_{0.0};
    std::atomic<bool> externalTrigger_{false};
    std::mutex triggerMutex_;
    std::condition_variable triggerCv_;
    int triggers_ = 0;  // pending, guarded by triggerMutex_
    uint64_t rng_ = 88172645463325252ULL;  // input thread only (xorshift)

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
    GateHoldoff gateHold_[4];  // per kGates entry
    uint16_t adcLive_[2][8] = {};
    uint64_t adcGen_ = 0;

    // Last snapshot, guarded by mutex_
    int snapSr_ = 0;
    int snapPin_[kMaxPins] = {};
    uint16_t snapAdc_[2][8] = {};
    uint64_t snapAdcGen_ = 0;
    long long snapCount_ = 0;

    Encoder enc_[2];  // 0 = pitch, 1 = speed (encoderId)

    // Raw encoders, guarded by rawMutex_ (taken before mutex_, never after).
    struct RawState {
        std::atomic<bool> on{false};     // steps and click to sclang
        std::atomic<bool> click{false};  // click only to sclang
        bool pressed = false;      // press sent to sclang, release not yet
        bool waitRelease = false;  // held when the click was routed: skip until released
        int lastDir = 0;
        bool sendsClick() const { return on || click; }
    };
    std::mutex rawMutex_;
    RawState raw_[2];
    std::atomic<bool> anyRaw_{false};  // any steps or clicks routed to sclang

    // Stats
    std::atomic<uint64_t> scans_{0};
    std::atomic<uint64_t> snapshots_{0};
    std::atomic<int64_t> worstScanUs_{0};
    uint64_t lastStatScans_ = 0;
    uint64_t lastStatSnaps_ = 0;
    int64_t lastStatNs_ = 0;
};

}  // namespace nebio
