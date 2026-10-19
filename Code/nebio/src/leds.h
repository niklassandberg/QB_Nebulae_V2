// leds.h - PCA9685 LED driver (I2C) + reset LED (GPIO 12 software PWM).
//
// Python stages LED values and commits them once per ui.update(), like the
// old leddriver.update(). The LED thread then writes every changed channel in
// one I2C transaction (auto-increment), instead of one LED per loop.
#pragma once

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>

#include "gpio.h"

namespace nebio {

class Pca9685 {
public:
    ~Pca9685();
    bool open(const char *bus, int address, double pwmFreqHz);
    void close();
    bool ok() const { return fd_ >= 0; }
    // Writes OFF values for channels [first, last] in one transaction (ON = 0).
    bool writeRange(const int *offValues, int first, int last);

private:
    bool writeReg(uint8_t reg, uint8_t value);
    bool readReg(uint8_t reg, uint8_t &value);
    int fd_ = -1;
};

class Leds {
public:
    static Leds &instance();

    int init();
    void shutdown();

    void setButton(int id, double brightness);
    void setRgb(int id, double r, double g, double b, double brightness);
    void commit();
    void animation(const std::string &color, const std::string &behavior);
    void animationStop();

    // sclang's colour for an RGB LED (/sc/led/<led>, 0-4095 per colour). It is
    // always remembered, and shown while sclang owns the LED; then setRgb()
    // from Python is ignored for it. Taking ownership shows the remembered
    // colour (off if sclang has sent none since clearSc()).
    void setScRgb(int id, double r, double g, double b);
    void setScOwned(int id, bool owned);
    void clearSc();  // new patch: forget sclang's colours

private:
    Leds() = default;
    void run();
    void runResetPwm();
    void renderAnimation(int out[16], int &resetDuty);
    void showRgb(int id, const int off[3]);  // caller holds mutex_

    Pca9685 pca_;
    GpioLines resetLed_;
    std::thread thread_;
    std::thread pwmThread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_{false};

    std::mutex mutex_;
    std::condition_variable cv_;
    bool dirty_ = false;
    int staged_[16];
    int committed_[16];
    int written_[16];
    bool writtenValid_ = false;

    // sclang's RGB colours (as PCA9685 off values), guarded by mutex_
    int scRgb_[4][3];
    bool scValid_[4] = {false, false, false, false};
    bool scOwned_[4] = {false, false, false, false};

    // Animation
    bool animating_ = false;
    double animColor_[3] = {0, 0, 0};
    int animBehavior_ = 0;  // 0 cycle, 1 pulse, 2 rainbow

    // Reset LED: duty in percent the pin is HIGH (LED is active low), as RPi.GPIO PWM.
    std::atomic<int> uiResetDuty_{100};
    std::atomic<int> animResetDuty_{100};
    std::mutex pwmMutex_;
    std::condition_variable pwmCv_;
};

}  // namespace nebio
