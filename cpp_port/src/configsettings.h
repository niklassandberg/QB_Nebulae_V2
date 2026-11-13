// configsettings.py: the config settings, "key=value" lines in CONFIG_FILE:
//   power_regulator=off    off | yield | shell | nohlt (nohlt: the Pi restarts)
//   no_pwm=off             file and freeze LEDs without PWM
//   led_stagger=on
//   services_quiet=off
//   wifi=on
//   led_dim=0.50
//   log_level=INFO         DEBUG, STATS, INFO .. CRITICAL (by hand)
//   nebio_scan_hz=1200, nebio_digital_hz=400, nebio_adc_hz=400,
//   nebio_fast_gpio=off    on: /dev/gpiomem instead of libgpiod (Pi 1-4)
//   csound_rt_priority=70  SCHED_FIFO 1-99, 0 = normal (by hand)
//   gate_interrupts=off    off: gates polled with a Schmitt trigger hold-off; on: interrupts
//   gate_holdoff_ms=5.0    0-100, only with gate_interrupts=off
// A missing or invalid value keeps its default.
#pragma once

#include <condition_variable>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

#include "pyvalue.h"

namespace neb {

namespace config {
extern std::string CONFIG_FILE;
extern std::string SCRIPTS_DIR;
extern std::string QUIET_SCRIPT;
extern std::string WIFI_SCRIPT;
extern std::string CMDLINE;
// Changes from the web page (NebFile /config). Nebulae applies them: it owns
// the LEDs, the scripts and the restart, and a direct file write would be
// overwritten by its next save.
extern std::string REQUEST_FILE;
extern std::function<bool()> kernelHasNohlt;  // "nohlt" in /proc/cmdline

constexpr double GATE_HOLDOFF_DEFAULT_MS = 5.0;
constexpr double GATE_HOLDOFF_MAX_MS = 100.0;
constexpr int SCAN_HZ_MIN = 100, SCAN_HZ_MAX = 2000;  // nebio's limits (inputs.cpp)
extern const std::vector<std::string> POWER_REGULATOR;
extern const std::vector<std::string> ON_OFF;
extern const std::vector<std::string> NEBIO_RATES;
extern const std::vector<std::string> LOG_LEVELS;

using Request = std::map<std::string, Value>;  // key: value (bool for on/off)

// The valid settings of values (key: text), as setter arguments.
Request checkedRequest(const std::map<std::string, std::string> &values);
Request writeRequest(const std::map<std::string, std::string> &values);
Request takeRequest();
std::optional<double> holdoff(const Value &text);  // _holdoff()
long long rate(const Value &text, long long def);  // _rate()
}  // namespace config

// A job for the background thread: a script command, or _syncCmdline.
struct ConfigJob {
    std::vector<std::string> command;  // empty: syncCmdline
};

class ConfigSettings {
public:
    ConfigSettings();
    ~ConfigSettings();
    void load();

    // Locked: the web page, the UI and the job thread use one ConfigSettings.
    std::string powerRegulator() const { return locked(powerRegulator_); }
    bool powerNeedsRestart() const { return wantNohlt() != config::kernelHasNohlt(); }
    bool noPwm() const { return locked(noPwm_); }
    bool ledStagger() const { return locked(ledStagger_); }
    bool servicesQuiet() const { return locked(servicesQuiet_); }
    bool wifiOn() const { return locked(wifiOn_); }
    double ledDim() const { return locked(ledDim_); }
    std::string logLevel() const { return locked(logLevel_); }
    long long nebioScanHz() const { return locked(nebioScanHz_); }
    long long nebioDigitalHz() const { return locked(nebioDigitalHz_); }
    long long nebioAdcHz() const { return locked(nebioAdcHz_); }
    bool nebioFastGpio() const { return locked(nebioFastGpio_); }
    long long csoundRtPriority() const { return locked(csoundRtPriority_); }
    bool gateInterrupts() const { return locked(gateInterrupts_); }
    double gateHoldoffMs() const { return locked(gateHoldoffMs_); }

    void applyAtStart();
    bool setPowerRegulator(const std::string &value);  // true: the Pi must restart
    void setNoPwm(bool on);
    void setLedStagger(bool on);
    void setServicesQuiet(bool on);
    void setWifiOn(bool on);
    void setLedDim(const Value &value);
    void setNebioFastGpio(bool on);
    void setGateInterrupts(bool on);
    void setGateHoldoffMs(const Value &ms);
    // Missing ones keep their value. Returns the saved (scan, digital, adc).
    std::tuple<long long, long long, long long> setNebioRates(const Value &scan = Value(),
                                                              const Value &digital = Value(),
                                                              const Value &adc = Value());
    void syncCmdline();
    void waitUntilApplied();

    // Tests: jobs go here instead of the background thread.
    std::function<void(const ConfigJob &)> runInBackgroundHook;

private:
    template <class T>
    T locked(const T &field) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return field;
    }
    bool wantNohlt() const { return locked(powerRegulator_) == "nohlt"; }
    void save();  // called with mutex_ held
    void runInBackground(ConfigJob job);
    void worker();

    std::string powerRegulator_ = "off";
    bool noPwm_ = false, ledStagger_ = true, servicesQuiet_ = false, wifiOn_ = false;
    double ledDim_ = 1.0;
    std::string logLevel_ = "INFO";
    long long nebioScanHz_ = 1200, nebioDigitalHz_ = 400, nebioAdcHz_ = 400;
    bool nebioFastGpio_ = false;
    long long csoundRtPriority_ = 70;  // below jackd's 75
    bool gateInterrupts_ = false;
    double gateHoldoffMs_ = config::GATE_HOLDOFF_DEFAULT_MS;

    mutable std::mutex mutex_;
    std::mutex cmdlineMutex_;  // syncCmdline: the job thread and setPowerRegulator
    std::mutex jobsMutex_;
    std::condition_variable jobsCv_;
    std::deque<ConfigJob> jobs_;
    int pending_ = 0;
    bool started_ = false, stop_ = false;
    std::thread thread_;
};

ConfigSettings &configSettings();  // the module's configSettings

}  // namespace neb
