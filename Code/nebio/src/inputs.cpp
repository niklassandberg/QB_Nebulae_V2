#include "inputs.h"

#include <time.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <vector>

#include "log.h"

namespace nebio {

namespace {

// BCM pin numbers, same as the Python modules.
constexpr unsigned kSrData = 5;    // shiftregister.py
constexpr unsigned kSrLatch = 15;
constexpr unsigned kSrClock = 14;
constexpr unsigned kEolPin = 16;   // control.py EOL_OUT_PIN
constexpr unsigned kClickPitch = 22;  // ui.py
constexpr unsigned kClickSpeed = 26;
const std::vector<unsigned> kGates = {4, 25, 23, 24};  // freeze, reset, next, record
// NOTE: GPIO 7/8 (POT/CV select in control.py) are the SPI chip selects and
// are owned by the spidev driver, so they are deliberately not touched here.

// Scan/ADC rates: default 1000/500 Hz (inputs.h), Python can change them at
// run time (nebio_set_input_rates).
constexpr int kMinScanHz = 100;
constexpr int kMaxScanHz = 2000;
constexpr int kButtonDebounceUs = 8000;  // buttons/clicks, kept at 8 ms for any scan rate
constexpr int kSrGateBit = 6;        // source gate arrives through the shift register
constexpr uint32_t kSpiHz = 1000000;  // MCP3208.py

int64_t nowNs() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}

// encoder.py VALID_SEQ_3
int seqDirection(int a, int b, int c) {
    static const int fwd[4][3] = {{0, 1, 3}, {1, 3, 2}, {3, 2, 0}, {2, 0, 1}};
    static const int rev[4][3] = {{0, 2, 3}, {2, 3, 1}, {3, 1, 0}, {1, 0, 2}};
    for (int i = 0; i < 4; ++i) {
        if (fwd[i][0] == a && fwd[i][1] == b && fwd[i][2] == c) return 1;
        if (rev[i][0] == a && rev[i][1] == b && rev[i][2] == c) return -1;
    }
    return 0;
}

}  // namespace

// ---- small helpers -------------------------------------------------------

int Debounce::feed(int v) {
    if (v == raw) {
        if (count < need) ++count;
    } else {
        raw = v;
        count = 0;
    }
    if (count >= need) stable = raw;
    return stable;
}

void StretchBit::reset(int v) {
    current = reported = v;
    pending = 0;
}

void StretchBit::transition(int v) {
    if (v == current) return;
    current = v;
    ++pending;
    if (pending > 2) pending -= 2;  // drop a whole pulse, keep the parity
}

int StretchBit::consume() {
    if (pending > 0) {
        reported ^= 1;
        --pending;
    } else {
        reported = current;
    }
    return reported;
}

void Encoder::reset(int state) {
    hist[0] = state;
    histLen = 1;
}

void Encoder::update(int state) {
    if (hist[histLen - 1] == state) return;
    hist[histLen++] = state;
    if (histLen != 3) return;
    steps += seqDirection(hist[0], hist[1], hist[2]);
    hist[0] = hist[1];
    hist[1] = hist[2];
    histLen = 2;
}

// ---- Inputs --------------------------------------------------------------

Inputs &Inputs::instance() {
    static Inputs *inputs = new Inputs();  // never destroyed, see GpioChip
    return *inputs;
}

int Inputs::setRates(int scanHz, int digitalHz, int adcHz) {
    if (scanHz < kMinScanHz || scanHz > kMaxScanHz || digitalHz < 1 || digitalHz > scanHz ||
        adcHz < 1 || adcHz > scanHz) {
        logError("invalid input rates: scan %d Hz (allowed %d-%d), digital %d Hz and adc %d Hz "
                 "(allowed 1-scan)", scanHz, kMinScanHz, kMaxScanHz, digitalHz, adcHz);
        return -1;
    }
    int periodUs = 1000000 / scanHz;
    // Digital inputs and ADC run every nth scan, rounded.
    int digitalNth = (scanHz + digitalHz / 2) / digitalHz;
    int adcNth = (scanHz + adcHz / 2) / adcHz;
    if (digitalNth < 1) digitalNth = 1;
    if (adcNth < 1) adcNth = 1;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        scanPeriodUs_.store(periodUs, std::memory_order_relaxed);
        digitalEveryNth_.store(digitalNth, std::memory_order_relaxed);
        adcEveryNth_.store(adcNth, std::memory_order_relaxed);
        applyDebounce();
    }
    logInfo("input rates: scan (encoders) %d Hz, digital %d Hz, adc %d Hz", this->scanHz(),
            this->digitalHz(), this->adcHz());
    return 0;
}

int Inputs::scanHz() const { return 1000000 / scanPeriodUs_.load(std::memory_order_relaxed); }

int Inputs::digitalHz() const {
    return 1000000 / scanPeriodUs_.load(std::memory_order_relaxed) /
           digitalEveryNth_.load(std::memory_order_relaxed);
}

int Inputs::adcHz() const {
    return 1000000 / scanPeriodUs_.load(std::memory_order_relaxed) /
           adcEveryNth_.load(std::memory_order_relaxed);
}

// Debounce counts are in digital reads; keep the button debounce time at
// kButtonDebounceUs whatever the rates are. Caller holds mutex_.
void Inputs::applyDebounce() {
    const int periodUs = scanPeriodUs_.load(std::memory_order_relaxed) *
                         digitalEveryNth_.load(std::memory_order_relaxed);
    int need = (kButtonDebounceUs + periodUs / 2) / periodUs;
    if (need < 1) need = 1;
    for (int i = 0; i < 8; ++i) srDebounce_[i].need = i == kSrGateBit ? 0 : need;
    for (int s = 0; s < slotCount_; ++s)
        if (pinDebounce_[s].need > 0) pinDebounce_[s].need = need;
}

int Inputs::pinSlot(int pin) const {
    if (pin < 0 || pin >= 64) return -1;
    return slotOfPin_[pin];
}

int Inputs::init() {
    if (running_) return 0;
    if (!GpioChip::instance().get()) return -1;

    for (int &s : slotOfPin_) s = -1;
    slotCount_ = 0;

    srOut_.requestOutputs({kSrLatch, kSrClock}, 0);
    srIn_.requestInputs({kSrData}, Bias::Off, false);
    eolOut_.requestOutputs({kEolPin}, 0);

    gatesPolled_ = !edges_.requestInputs(kGates, Bias::PullUp, true);
    std::vector<unsigned> polledPins = {kClickPitch, kClickSpeed};
    // encoder.Worker(17, 27) and (6, 13): encoder.py swaps the pins,
    // so state = level(27) | level(17) << 1 and level(13) | level(6) << 1.
    enc_[0].pinA = 27;
    enc_[0].pinB = 17;
    enc_[1].pinA = 13;
    enc_[1].pinB = 6;
    for (const Encoder &e : enc_) {
        polledPins.push_back(e.pinA);
        polledPins.push_back(e.pinB);
    }
    if (gatesPolled_) {
        logInfo("edge events not available, polling the gate inputs instead");
        polledPins.insert(polledPins.end(), kGates.begin(), kGates.end());
    }
    polled_.requestInputs(polledPins, Bias::PullUp, false);

    adc_[0].open("/dev/spidev0.0", kSpiHz);
    adc_[1].open("/dev/spidev0.1", kSpiHz);

    // Slots for the pins Python reads through switch.py.
    auto addSlot = [&](unsigned pin, int debounce) {
        int s = slotCount_++;
        slotOfPin_[pin] = s;
        slotPin_[s] = static_cast<int>(pin);
        pinDebounce_[s] = Debounce();
        pinDebounce_[s].need = debounce;
    };
    addSlot(kClickPitch, 1);  // debounced; applyDebounce() sets the scan count
    addSlot(kClickSpeed, 1);
    for (unsigned g : kGates) addSlot(g, 0);  // gates: no debounce
    for (int i = 0; i < 8; ++i) srDebounce_[i] = Debounce();
    {
        std::lock_guard<std::mutex> lock(mutex_);
        applyDebounce();
    }

    // Start from the real levels, so a button held at boot is seen at once
    // (check_wifi.py / check_calibration.py read a single value).
    for (int s = 0; s < slotCount_; ++s) {
        unsigned pin = static_cast<unsigned>(slotPin_[s]);
        int level = polled_.get(pin);
        if (level < 0) level = edges_.get(pin);
        if (level < 0) level = 1;  // pulled up = released
        pinDebounce_[s].raw = pinDebounce_[s].stable = level;
        pinDebounce_[s].count = pinDebounce_[s].need;
        pinBits_[s].reset(level);
        snapPin_[s] = level;
    }
    // Shift register starts at 0 and needs a stable read, like shiftregister.py.
    for (int i = 0; i < 8; ++i) srBits_[i].reset(0);
    snapSr_ = 0;

    for (Encoder &e : enc_) {
        int a = polled_.get(e.pinA), b = polled_.get(e.pinB);
        e.reset((a > 0 ? 1 : 0) | ((b > 0 ? 1 : 0) << 1));
        e.steps = 0;
    }

    stop_ = false;
    running_ = true;
    lastStatNs_ = nowNs();
    thread_ = std::thread(&Inputs::run, this);
    if (!gatesPolled_) edgeThread_ = std::thread(&Inputs::runEdges, this);
    logInfo("inputs running (sr=%d clicks/enc=%d gates=%s adc cv=%d pot=%d)", srIn_.ok(),
            polled_.ok(), gatesPolled_ ? "polled" : "events", adc_[0].ok(), adc_[1].ok());
    return 0;
}

void Inputs::shutdown() {
    if (!running_) return;
    stop_ = true;
    adcCv_.notify_all();
    if (thread_.joinable()) thread_.join();
    if (edgeThread_.joinable()) edgeThread_.join();
    srOut_.release();
    srIn_.release();
    polled_.release();
    edges_.release();
    eolOut_.release();
    adc_[0].close();
    adc_[1].close();
    running_ = false;
}

bool Inputs::readShiftRegister(uint8_t &bits) {
    if (!srOut_.ok() || !srIn_.ok()) return false;
    // Same sequence as shiftregister.py: pulse latch, then clock out 8 bits.
    srOut_.set(kSrLatch, 1);
    srOut_.set(kSrLatch, 0);
    bits = 0;
    for (int i = 0; i < 8; ++i) {
        srOut_.set(kSrClock, 0);
        if (srIn_.get(kSrData) == 1) bits |= static_cast<uint8_t>(1 << i);
        srOut_.set(kSrClock, 1);
    }
    return true;
}

void Inputs::run() {
    std::vector<int> levels;
    const std::vector<unsigned> &polledPins = polled_.pins();
    uint64_t tick = 0;
    int64_t next = nowNs();
    while (!stop_) {
        int64_t start = nowNs();

        // Rates can be changed from Python at any time; read them once per scan.
        // Relaxed: compiles to a plain load (no barrier); one scan with a mixed
        // old/new set after a change is harmless.
        const int periodUs = scanPeriodUs_.load(std::memory_order_relaxed);
        const int digitalNth = digitalEveryNth_.load(std::memory_order_relaxed);
        const int adcNth = adcEveryNth_.load(std::memory_order_relaxed);
        // Encoders every scan; shift register + clicks (+ polled gates) every
        // digitalNth scan; ADCs every adcNth scan.
        bool digitalScan = (tick % static_cast<uint64_t>(digitalNth)) == 0;
        bool adcScan = (tick % static_cast<uint64_t>(adcNth)) == 0;

        uint8_t sr = 0;
        bool srOk = digitalScan && readShiftRegister(sr);
        // One read for all polled pins (encoders and clicks share the request).
        bool polledOk = polled_.getAll(levels);
        uint16_t codes[2][8];
        bool adcOk[2] = {false, false};
        if (adcScan) {
            adcOk[0] = adc_[0].readAll(codes[0]);
            adcOk[1] = adc_[1].readAll(codes[1]);
        }

        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (srOk) {
                for (int i = 0; i < 8; ++i) srBits_[i].transition(srDebounce_[i].feed((sr >> i) & 1));
            }
            if (polledOk && digitalScan) {
                for (size_t i = 0; i < polledPins.size(); ++i) {
                    int s = pinSlot(static_cast<int>(polledPins[i]));
                    if (s >= 0) pinBits_[s].transition(pinDebounce_[s].feed(levels[i]));
                }
            }
            if (adcScan) {
                for (int d = 0; d < 2; ++d) {
                    if (adcOk[d]) std::memcpy(adcLive_[d], codes[d], sizeof(codes[d]));
                }
                ++adcGen_;
            }
        }
        if (adcScan) adcCv_.notify_all();

        if (polledOk) {
            for (Encoder &e : enc_) {
                int a = 0, b = 0;
                for (size_t i = 0; i < polledPins.size(); ++i) {
                    if (polledPins[i] == e.pinA) a = levels[i];
                    if (polledPins[i] == e.pinB) b = levels[i];
                }
                e.update(a | (b << 1));
            }
        }

        ++tick;
        ++scans_;
        int64_t took = (nowNs() - start) / 1000;
        if (took > worstScanUs_) worstScanUs_ = took;

        next += periodUs * 1000LL;
        int64_t now = nowNs();
        if (next < now - 10LL * periodUs * 1000LL) next = now;  // fell behind, don't burst
        timespec ts;
        ts.tv_sec = next / 1000000000LL;
        ts.tv_nsec = next % 1000000000LL;
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, nullptr);
    }
}

void Inputs::runEdges() {
    std::vector<GpioLines::Edge> events;
    while (!stop_) {
        int n = edges_.waitEdges(100000000LL, events);  // 100 ms, to notice stop_
        if (n < 0) {
            logError("gate edge events failed, gates stop updating");
            return;
        }
        if (n == 0) continue;
        std::lock_guard<std::mutex> lock(mutex_);
        for (const GpioLines::Edge &e : events) {
            int s = pinSlot(static_cast<int>(e.pin));
            if (s >= 0) pinBits_[s].transition(e.level);
        }
    }
}

long long Inputs::snapshot() {
    if (!running_) return -1;
    std::unique_lock<std::mutex> lock(mutex_);
    adcCv_.wait_for(lock, std::chrono::milliseconds(10),
                    [&] { return adcGen_ != snapAdcGen_ || stop_; });
    int sr = 0;
    for (int i = 0; i < 8; ++i) sr |= srBits_[i].consume() << i;
    snapSr_ = sr;
    for (int s = 0; s < slotCount_; ++s) snapPin_[s] = pinBits_[s].consume();
    std::memcpy(snapAdc_, adcLive_, sizeof(snapAdc_));
    snapAdcGen_ = adcGen_;
    ++snapshots_;
    return ++snapCount_;
}

int Inputs::srBits() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return snapSr_;
}

int Inputs::gpioLevel(int pin) const {
    std::lock_guard<std::mutex> lock(mutex_);
    int s = pinSlot(pin);
    return s < 0 ? -1 : snapPin_[s];
}

int Inputs::adcCode(int device, int channel) const {
    if (device < 0 || device > 1 || channel < 0 || channel > 7) return 0;
    std::lock_guard<std::mutex> lock(mutex_);
    return snapAdc_[device][channel];
}

int Inputs::encoderId(int pinA, int pinB) const {
    if (pinA == 17 && pinB == 27) return 0;  // pitch, ui.py
    if (pinA == 6 && pinB == 13) return 1;   // speed, ui.py
    return -1;
}

int Inputs::encoderSteps(int id) {
    if (id < 0 || id > 1) return 0;
    return enc_[id].steps.exchange(0);
}

void Inputs::setEol(int high) { eolOut_.set(kEolPin, high ? 1 : 0); }

void Inputs::stats(char *buf, size_t len) {
    int64_t now = nowNs();
    double secs = (now - lastStatNs_) / 1e9;
    uint64_t scans = scans_, snaps = snapshots_;
    if (secs <= 0) secs = 1;
    std::snprintf(buf, len, "scan %.0f Hz, snapshot %.0f Hz, worst scan %lld us",
                  (scans - lastStatScans_) / secs, (snaps - lastStatSnaps_) / secs,
                  static_cast<long long>(worstScanUs_.exchange(0)));
    lastStatScans_ = scans;
    lastStatSnaps_ = snaps;
    lastStatNs_ = now;
}

}  // namespace nebio
