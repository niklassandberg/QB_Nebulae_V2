#include "leds.h"

#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <chrono>
#include <cmath>
#include <cstring>

#include "log.h"

namespace nebio {

namespace {

// PCA9685 registers
constexpr uint8_t kMode1 = 0x00;
constexpr uint8_t kMode2 = 0x01;
constexpr uint8_t kPrescale = 0xFE;
constexpr uint8_t kLed0OnL = 0x06;
constexpr uint8_t kRestart = 0x80;
constexpr uint8_t kAutoIncrement = 0x20;
constexpr uint8_t kSleep = 0x10;
constexpr uint8_t kAllCall = 0x01;
constexpr uint8_t kOutDrv = 0x04;
constexpr uint8_t kFullBit = 0x10;  // bit 4 of LEDn_ON_H / LEDn_OFF_H

constexpr int kLedOff = 4095;          // LEDs are active low
constexpr unsigned kResetLedPin = 12;  // leddriver.py RESET_LED_PIN
constexpr int kResetPwmHz = 150;       // leddriver.py GPIOLed
constexpr int kAnimFrameMs = 15;

// leddriver.py addresses
constexpr int kButtonChannel[4] = {9, 10, 11, 12};  // record, next, source, freeze
constexpr int kRgbChannel[4][3] = {
    {8, 0, 1},    // pitch_pos
    {13, 15, 14}, // pitch_neg
    {4, 3, 2},    // speed_pos
    {7, 5, 6},    // speed_neg
};
constexpr int kButtonReset = 4;
constexpr int kButtonNext = 1;    // the file LED (index in kButtonChannel)
constexpr int kButtonFreeze = 3;  // the freeze LED

void sleepMs(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

void sleepNs(int64_t ns) {
    timespec ts;
    ts.tv_sec = ns / 1000000000LL;
    ts.tv_nsec = ns % 1000000000LL;
    clock_nanosleep(CLOCK_MONOTONIC, 0, &ts, nullptr);
}

// RGBLed.post_brightness_color + update: 4095 - int(color * brightness)
int rgbOff(double color, double brightness) { return 4095 - static_cast<int>(color * brightness); }
// ButtonLed: int((1.0 - brightness) * 4095)
int buttonOff(double brightness) { return static_cast<int>((1.0 - brightness) * 4095); }
// GPIOLed: ChangeDutyCycle(int((1.0 - brightness) * 100))
int resetDuty(double brightness) {
    int d = static_cast<int>((1.0 - brightness) * 100);
    return d < 0 ? 0 : (d > 100 ? 100 : d);
}

void hsvToRgb(double h, double &r, double &g, double &b) {  // s = v = 1, colorsys
    int i = static_cast<int>(h * 6.0);
    double f = h * 6.0 - i, q = 1.0 - f, t = f;
    switch (i % 6) {
        case 0: r = 1; g = t; b = 0; break;
        case 1: r = q; g = 1; b = 0; break;
        case 2: r = 0; g = 1; b = t; break;
        case 3: r = 0; g = q; b = 1; break;
        case 4: r = t; g = 0; b = 1; break;
        default: r = 1; g = 0; b = q; break;
    }
}

}  // namespace

// ---- PCA9685 -------------------------------------------------------------

Pca9685::~Pca9685() { close(); }

void Pca9685::close() {
    if (fd_ >= 0) ::close(fd_);
    fd_ = -1;
}

bool Pca9685::writeReg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return ::write(fd_, buf, 2) == 2;
}

bool Pca9685::readReg(uint8_t reg, uint8_t &value) {
    return ::write(fd_, &reg, 1) == 1 && ::read(fd_, &value, 1) == 1;
}

bool Pca9685::open(const char *bus, int address, double pwmFreqHz) {
    close();
    fd_ = ::open(bus, O_RDWR);
    if (fd_ < 0 || ioctl(fd_, I2C_SLAVE, address) < 0) {
        logError("could not open PCA9685 at %s 0x%02x", bus, address);
        close();
        return false;
    }
    // Same init as Adafruit_PCA9685, plus register auto-increment.
    uint8_t mode1 = 0;
    bool ok = writeReg(kMode2, kOutDrv) && writeReg(kMode1, kAllCall | kAutoIncrement);
    sleepMs(5);
    ok = ok && readReg(kMode1, mode1);
    ok = ok && writeReg(kMode1, (mode1 & ~kSleep) | kAutoIncrement);
    sleepMs(5);
    int prescale = static_cast<int>(std::floor(25000000.0 / 4096.0 / pwmFreqHz - 1.0 + 0.5));
    uint8_t old = 0;
    ok = ok && readReg(kMode1, old);
    ok = ok && writeReg(kMode1, (old & 0x7F) | kSleep);
    ok = ok && writeReg(kPrescale, static_cast<uint8_t>(prescale));
    ok = ok && writeReg(kMode1, old);
    sleepMs(5);
    ok = ok && writeReg(kMode1, old | kRestart);
    if (!ok) {
        logError("PCA9685 init failed");
        close();
    }
    return ok;
}

// A fully off (4095) or fully on (0) LED uses the full ON/OFF bit: then the
// output is static. With ON = 0 / OFF = 4095 it still gets one tick of the
// other level every PWM period (250 Hz edges on every "off" LED).
// stagger (quiet mode): a dimmed LED is high for v of the 4096 ticks as
// always, but every channel starts at its own point of the period (ON =
// channel * 256; the chip wraps OFF past 4095), so the 16 channels do not
// all switch at the same moment. Otherwise all start at 0.
bool Pca9685::writeRange(const int *offValues, int first, int last, bool stagger) {
    if (fd_ < 0) return false;
    uint8_t buf[1 + 16 * 4];
    int n = 0;
    buf[n++] = static_cast<uint8_t>(kLed0OnL + 4 * first);
    for (int ch = first; ch <= last; ++ch) {
        int v = offValues[ch];
        int on = stagger ? ch * 256 : 0;
        int off = (on + v) & 0x0FFF;
        uint8_t onL = static_cast<uint8_t>(on & 0xFF), onH = static_cast<uint8_t>((on >> 8) & 0x0F);
        uint8_t offL = static_cast<uint8_t>(off & 0xFF), offH = static_cast<uint8_t>((off >> 8) & 0x0F);
        if (v >= kLedOff) { onL = 0; onH = kFullBit; offL = 0; offH = 0; }  // output always high: LED off
        else if (v <= 0) { onL = 0; onH = 0; offL = 0; offH = kFullBit; }   // output always low: LED fully on
        buf[n++] = onL;
        buf[n++] = onH;
        buf[n++] = offL;
        buf[n++] = offH;
    }
    return ::write(fd_, buf, n) == n;
}


// ---- Leds ----------------------------------------------------------------

Leds &Leds::instance() {
    static Leds *leds = new Leds();  // never destroyed, see GpioChip
    return *leds;
}

int Leds::init() {
    if (running_) return 0;
    for (int i = 0; i < 16; ++i) staged_[i] = committed_[i] = written_[i] = kLedOff;
    writtenValid_ = false;
    animating_ = false;
    uiResetDuty_ = 100;

    pca_.open("/dev/i2c-1", 0x40, 250.0);  // leddriver.py set_pwm_freq(250)
    resetLed_.requestOutputs({kResetLedPin}, 1);

    stop_ = false;
    running_ = true;
    dirty_ = true;
    thread_ = std::thread(&Leds::run, this);
    pwmThread_ = std::thread(&Leds::runResetPwm, this);
    logInfo("LEDs running (pca9685=%d reset=%d)", pca_.ok(), resetLed_.ok());
    return pca_.ok() ? 0 : -1;
}

void Leds::shutdown() {
    if (!running_) return;
    stop_ = true;
    cv_.notify_all();
    pwmCv_.notify_all();
    if (thread_.joinable()) thread_.join();
    if (pwmThread_.joinable()) pwmThread_.join();
    pca_.close();
    resetLed_.release();
    running_ = false;
}

void Leds::setButton(int id, double brightness) {
    if (id == kButtonReset) {
        uiResetDuty_ = resetDuty(brightness);  // immediate, like GPIOLed
        pwmCv_.notify_all();
        return;
    }
    if (id < 0 || id > 3) return;
    std::lock_guard<std::mutex> lock(mutex_);
    staged_[kButtonChannel[id]] = buttonOff(brightness);
}

void Leds::setRgb(int id, double r, double g, double b, double brightness) {
    if (id < 0 || id > 3) return;
    std::lock_guard<std::mutex> lock(mutex_);
    if (scOwned_[id]) return;  // sclang drives this LED
    staged_[kRgbChannel[id][0]] = rgbOff(r, brightness);
    staged_[kRgbChannel[id][1]] = rgbOff(g, brightness);
    staged_[kRgbChannel[id][2]] = rgbOff(b, brightness);
}

// Staged and committed at once: sclang's colours do not wait for Python's
// next commit.
void Leds::showRgb(int id, const int off[3]) {
    for (int k = 0; k < 3; ++k) staged_[kRgbChannel[id][k]] = committed_[kRgbChannel[id][k]] = off[k];
    dirty_ = true;
}

void Leds::setScRgb(int id, double r, double g, double b) {
    if (id < 0 || id > 3) return;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        const double rgb[3] = {r, g, b};
        for (int k = 0; k < 3; ++k) {
            double c = !(rgb[k] > 0) ? 0 : (rgb[k] > 4095 ? 4095 : rgb[k]);  // from sclang: clamp, NaN -> 0
            scRgb_[id][k] = rgbOff(c, 1.0);
        }
        scValid_[id] = true;
        if (!scOwned_[id]) return;
        showRgb(id, scRgb_[id]);
    }
    cv_.notify_all();
}

void Leds::setScOwned(int id, bool owned) {
    if (id < 0 || id > 3) return;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (scOwned_[id] == owned) return;
        scOwned_[id] = owned;
        if (!owned) return;  // Python sets the LED on its next update
        const int off[3] = {kLedOff, kLedOff, kLedOff};
        showRgb(id, scValid_[id] ? scRgb_[id] : off);
    }
    cv_.notify_all();
}

void Leds::clearSc() {
    std::lock_guard<std::mutex> lock(mutex_);
    for (bool &v : scValid_) v = false;
}

void Leds::commit() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        std::memcpy(committed_, staged_, sizeof(committed_));
        dirty_ = true;
    }
    cv_.notify_all();
}

void Leds::animation(const std::string &color, const std::string &behavior) {
    // bootleds.py colors
    double c[3] = {4095, 0, 1024};
    if (color == "booting") { c[0] = 4095; c[1] = 4095; c[2] = 4095; }
    else if (color == "loading") { c[0] = 0; c[1] = 0; c[2] = 4095; }
    else if (color == "loadingusb") { c[0] = 0; c[1] = 2047.5; c[2] = 2047.5; }  // blend(blue, green, 0.5)
    else if (color == "updating") { c[0] = 0; c[1] = 4095; c[2] = 0; }
    else if (color == "error") { c[0] = 4095; c[1] = 0; c[2] = 0; }
    else if (color == "calibration") { c[0] = 4095; c[1] = 3395; c[2] = 0; }
    else if (color == "wifi") { c[0] = 511; c[1] = 0; c[2] = 4095; }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        std::memcpy(animColor_, c, sizeof(c));
        animBehavior_ = behavior == "pulse" ? 1 : (behavior == "rainbow" ? 2 : 0);
        animating_ = true;
        dirty_ = true;
    }
    cv_.notify_all();
    pwmCv_.notify_all();
}

void Leds::animationStop() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        animating_ = false;
        dirty_ = true;
    }
    cv_.notify_all();
    pwmCv_.notify_all();
}

void Leds::setDim(double dim) {
    if (!(dim > 0)) dim = 0;  // also NaN
    if (dim > 1) dim = 1;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        dim_ = dim;
        dirty_ = true;
    }
    cv_.notify_all();
    pwmCv_.notify_all();
}

void Leds::setNoPwm(bool on) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        noPwm_ = on;
        dirty_ = true;
    }
    cv_.notify_all();
    pwmCv_.notify_all();
}

void Leds::setStagger(bool on) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stagger_ = on;
        dirty_ = true;
    }
    cv_.notify_all();
}

// Same math as bootleds.py.
void Leds::renderAnimation(int out[16], int &resetDutyOut) {
    timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    double secs = ts.tv_sec + ts.tv_nsec / 1e9;
    long long now = static_cast<long long>(std::llround(secs * 1000.0));

    double col[3] = {animColor_[0], animColor_[1], animColor_[2]};
    if (animBehavior_ == 2) {
        double phaser = std::fmod(secs * 2.13, 1.0);
        double r, g, b;
        hsvToRgb(phaser, r, g, b);
        col[0] = static_cast<int>(r * 4095);
        col[1] = static_cast<int>(g * 4095);
        col[2] = static_cast<int>(b * 4095);
    }
    double bright[5];
    for (int i = 0; i < 5; ++i) {
        long long t = now + i * 200;
        if (animBehavior_ == 1)
            bright[i] = std::fabs(static_cast<double>(now & 400) - 200.0) / 400.0;
        else
            bright[i] = std::fabs(std::fmod(static_cast<double>(t), 1000.0) / 500.0 - 1.0);
    }
    const int rgbBright[4] = {1, 2, 3, 4};  // pitch_pos, pitch_neg, speed_pos, speed_neg
    for (int id = 0; id < 4; ++id) {
        for (int k = 0; k < 3; ++k) out[kRgbChannel[id][k]] = rgbOff(col[k], bright[rgbBright[id]]);
    }
    const int buttonBright[4] = {0, 1, 2, 4};  // record, next, source, freeze
    for (int id = 0; id < 4; ++id) out[kButtonChannel[id]] = buttonOff(bright[buttonBright[id]]);
    resetDutyOut = resetDuty(bright[3]);
}

void Leds::run() {
    int out[16];
    while (!stop_) {
        int animDuty = 100;
        bool animating;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            if (animating_)
                cv_.wait_for(lock, std::chrono::milliseconds(kAnimFrameMs), [&] { return stop_.load(); });
            else
                cv_.wait(lock, [&] { return dirty_ || animating_ || stop_; });
            if (stop_) break;
            animating = animating_;
            if (animating)
                renderAnimation(out, animDuty);
            else
                std::memcpy(out, committed_, sizeof(out));
            dirty_ = false;
        }
        if (animating) {
            animResetDuty_ = animDuty;
            pwmCv_.notify_all();
        }

        // Dim: the on part of each channel (LEDs are active low, 4095 = off).
        // Quiet mode (no PWM) for the file and freeze LEDs: fully on from half
        // brightness, else off; the dim factor only counts as 0 = off.
        double dim = dim_.load();
        const int noPwmCh[2] = {kButtonChannel[kButtonNext], kButtonChannel[kButtonFreeze]};
        int noPwmOut[2];
        for (int k = 0; k < 2; ++k)
            noPwmOut[k] = (dim > 0 && kLedOff - out[noPwmCh[k]] >= (kLedOff + 1) / 2) ? 0 : kLedOff;
        if (dim < 1.0) {
            for (int ch = 0; ch < 16; ++ch)
                out[ch] = kLedOff - static_cast<int>(std::lround((kLedOff - out[ch]) * dim));
        }
        if (noPwm_) {
            for (int k = 0; k < 2; ++k) out[noPwmCh[k]] = noPwmOut[k];
        }
        // Quiet mode staggers the channels (writeRange): a switch changes
        // every channel's start, so all are written again.
        const bool stagger = stagger_;
        if (stagger != staggered_) {
            staggered_ = stagger;
            writtenValid_ = false;
        }

        int first = -1, last = -1;
        for (int ch = 0; ch < 16; ++ch) {
            if (!writtenValid_ || out[ch] != written_[ch]) {
                if (first < 0) first = ch;
                last = ch;
            }
        }
        // No sleep at dim 0: in sleep the PCA9685 drives its outputs low, and
        // the LEDs are active low, so they all lit up (tested 2026-10-21).
        // Dim 0 = all outputs static high with the full bit (writeRange).
        if (first >= 0 && pca_.writeRange(out, first, last, staggered_)) {
            std::memcpy(written_, out, sizeof(written_));
            writtenValid_ = true;
        }
    }
}

// Software PWM like RPi.GPIO: pin HIGH for duty% of each 1/150 s period.
void Leds::runResetPwm() {
    const int64_t periodNs = 1000000000LL / kResetPwmHz;
    int lastLevel = -1;
    while (!stop_) {
        int duty;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            duty = animating_ ? animResetDuty_.load() : uiResetDuty_.load();
        }
        // Dim: duty is the off (HIGH) part, so the on part is scaled.
        double dim = dim_.load();
        if (dim < 1.0) duty = 100 - static_cast<int>(std::lround((100 - duty) * dim));
        if (duty <= 0 || duty >= 100) {
            int level = duty >= 100 ? 1 : 0;
            if (level != lastLevel) resetLed_.set(kResetLedPin, level);
            lastLevel = level;
            std::unique_lock<std::mutex> lock(pwmMutex_);
            pwmCv_.wait_for(lock, std::chrono::milliseconds(20));
            continue;
        }
        int64_t highNs = periodNs * duty / 100;
        resetLed_.set(kResetLedPin, 1);
        sleepNs(highNs);
        resetLed_.set(kResetLedPin, 0);
        sleepNs(periodNs - highNs);
        lastLevel = 0;
    }
}

}  // namespace nebio
