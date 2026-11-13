#include "configsettings.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>

#include "classlogger.h"
#include "textfile.h"

namespace neb {

namespace config {
std::string CONFIG_FILE = "/home/alarm/QB_Nebulae_V2/Code/config/configsettings.txt";
std::string SCRIPTS_DIR = "/home/alarm/QB_Nebulae_V2/Code/scripts/";
std::string QUIET_SCRIPT = SCRIPTS_DIR + "quiet.sh";
std::string WIFI_SCRIPT = SCRIPTS_DIR + "wifi.sh";
std::string CMDLINE = "/boot/cmdline.txt";
std::string REQUEST_FILE = "/tmp/nebulae_config_request";

std::function<bool()> kernelHasNohlt = [] {
    std::ifstream f("/proc/cmdline");
    std::string w;
    while (f >> w)
        if (w == "nohlt") return true;
    return false;
};

const std::vector<std::string> POWER_REGULATOR = {"off", "yield", "shell", "nohlt"};
const std::vector<std::string> ON_OFF = {"no_pwm", "led_stagger", "services_quiet", "wifi", "gate_interrupts",
                                         "nebio_fast_gpio"};
const std::vector<std::string> NEBIO_RATES = {"nebio_scan_hz", "nebio_digital_hz", "nebio_adc_hz"};
const std::vector<std::string> LOG_LEVELS = {"DEBUG", "STATS", "INFO", "WARNING", "ERROR", "CRITICAL"};

namespace {
bool in(const std::vector<std::string> &v, const std::string &s) { return std::find(v.begin(), v.end(), s) != v.end(); }

// min(hi, max(lo, v)) as Python evaluates it.
double clampF(double v, double lo, double hi) {
    double m = v > lo ? v : lo;
    return m < hi ? m : hi;
}
}  // namespace

std::optional<double> holdoff(const Value &text) {
    double ms;
    try {
        ms = toFloat(text);
    } catch (const PyError &) {
        return std::nullopt;  // TypeError, ValueError
    }
    if (!(0.0 <= ms && ms <= GATE_HOLDOFF_MAX_MS)) return std::nullopt;
    return pyRound(ms, 1);
}

long long rate(const Value &text, long long def) {
    long long hz;
    try {
        hz = toInt(text);
    } catch (const PyError &) {
        return def;
    }
    return (1 <= hz && hz <= 10000) ? hz : def;
}

Request checkedRequest(const std::map<std::string, std::string> &values) {
    Request out;
    auto get = [&](const std::string &k) -> const std::string * {
        auto it = values.find(k);
        return it == values.end() ? nullptr : &it->second;
    };
    if (auto v = get("power_regulator"); v && in(POWER_REGULATOR, *v)) out["power_regulator"] = Value::str(*v);
    for (auto &key : ON_OFF)
        if (auto v = get(key); v && (*v == "on" || *v == "off")) out[key] = Value::boolean(*v == "on");
    if (auto v = get("led_dim")) {
        if (auto f = pyFloat(*v)) out["led_dim"] = F(pyRound(clampF(*f, 0.0, 1.0), 2));
    }
    for (auto &key : NEBIO_RATES) {
        if (auto v = get(key)) {
            if (auto i = pyInt(*v)) out[key] = I(std::min<long long>(SCAN_HZ_MAX, std::max<long long>(1, *i)));
        }
    }
    auto h = holdoff(get("gate_holdoff_ms") ? Value::str(*get("gate_holdoff_ms")) : Value());
    if (h) out["gate_holdoff_ms"] = F(*h);
    // Not a setting: save the instrument, then restart Nebulae.
    if (auto v = get("restart"); v && *v == "nebulae") out["restart"] = Value::str("nebulae");
    return out;
}

Request writeRequest(const std::map<std::string, std::string> &values) {
    Request request = checkedRequest(values);
    // Python writes in insertion order: the order checkedRequest adds them.
    std::vector<std::string> order = {"power_regulator"};
    order.insert(order.end(), ON_OFF.begin(), ON_OFF.end());
    order.push_back("led_dim");
    order.insert(order.end(), NEBIO_RATES.begin(), NEBIO_RATES.end());
    order.push_back("gate_holdoff_ms");
    order.push_back("restart");
    std::string text;
    for (auto &key : order) {
        auto it = request.find(key);
        if (it == request.end()) continue;
        const Value &v = it->second;
        text += key + "=" + (v.type == Value::Bool ? (v.b ? "on" : "off") : pyStr(v)) + "\n";
    }
    // NebFile serves the page from a thread pool: a temp file of its own each.
    std::string tmp = REQUEST_FILE + "." + std::to_string(::getpid()) + "." +
                      std::to_string(std::hash<std::thread::id>()(std::this_thread::get_id())) + ".new";
    std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
    if (!f) throw PyError("FileNotFoundError", tmp);
    f << text;
    f.close();
    if (std::rename(tmp.c_str(), REQUEST_FILE.c_str()) != 0) throw PyError("OSError", REQUEST_FILE);
    return request;
}

Request takeRequest() {
    // Claimed by a rename first: a request saved while this one is read stays
    // for the next call instead of being removed unread.
    std::string taken = REQUEST_FILE + ".taken", text, line;
    if (std::rename(REQUEST_FILE.c_str(), taken.c_str()) != 0) return {};
    try {
        text = textfile::read(taken);
    } catch (const PyError &e) {
        if (!textfile::isOSError(e.type)) throw;
        return {};
    }
    if (std::remove(taken.c_str()) != 0) return {};
    std::map<std::string, std::string> values;
    std::istringstream lines(text);
    while (std::getline(lines, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        values[strip(line.substr(0, eq))] = strip(line.substr(eq + 1));
    }
    return checkedRequest(values);
}
}  // namespace config

using namespace config;

static Logger &cfgLog() {
    static Logger log("ConfigSettings");
    return log;
}

static void fsyncDir(const std::string &file) {
    size_t slash = file.find_last_of('/');
    std::string dir = slash == std::string::npos ? "." : (slash == 0 ? "/" : file.substr(0, slash));
    int fd = ::open(dir.c_str(), O_RDONLY);
    if (fd >= 0) {
        ::fsync(fd);
        ::close(fd);
    }
}

// Written, synced and renamed into place: a power cut keeps the old or the new file.
static bool writeSynced(const std::string &file, const std::string &text, std::string &err) {
    std::string tmp = file + ".new";
    int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        err = std::strerror(errno);
        return false;
    }
    bool ok = ::write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size()) && ::fsync(fd) == 0;
    ::close(fd);
    if (!ok || std::rename(tmp.c_str(), file.c_str()) != 0) {
        err = std::strerror(errno);
        return false;
    }
    fsyncDir(file);
    return true;
}

ConfigSettings::ConfigSettings() { load(); }

ConfigSettings::~ConfigSettings() {
    if (thread_.joinable()) {
        {
            std::lock_guard<std::mutex> lock(jobsMutex_);
            stop_ = true;
        }
        jobsCv_.notify_all();
        thread_.join();
    }
}

void ConfigSettings::load() {
    // No logging in here: the logger reads logLevel before it is set up.
    std::map<std::string, std::string> values;
    try {
        for (const std::string &line : textfile::lines(CONFIG_FILE)) {
            std::string s = strip(line);
            size_t eq = s.find('=');
            if (eq != std::string::npos) values[strip(s.substr(0, eq))] = strip(s.substr(eq + 1));
        }
    } catch (const PyError &e) {
        if (!textfile::isOSError(e.type)) throw;
        if (e.type == "FileNotFoundError") std::ofstream create(CONFIG_FILE, std::ios::app);
    }
    auto get = [&](const std::string &k) -> const std::string * {
        auto it = values.find(k);
        return it == values.end() ? nullptr : &it->second;
    };
    auto onOff = [&](const std::string &k, bool &field) {
        if (auto v = get(k); v && (*v == "on" || *v == "off")) field = *v == "on";
    };
    auto str = [&](const std::string &k) { return get(k) ? Value::str(*get(k)) : Value(); };
    std::lock_guard<std::mutex> lock(mutex_);
    if (auto v = get("power_regulator"); v && in(POWER_REGULATOR, *v)) powerRegulator_ = *v;
    onOff("no_pwm", noPwm_);
    onOff("led_stagger", ledStagger_);
    onOff("services_quiet", servicesQuiet_);
    onOff("wifi", wifiOn_);
    if (auto v = get("led_dim")) {
        if (auto d = pyFloat(*v)) ledDim_ = clampF(*d, 0.0, 1.0);
    }
    std::string level = get("log_level") ? *get("log_level") : "";
    for (auto &c : level) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    if (in(LOG_LEVELS, level)) logLevel_ = level;
    nebioScanHz_ = rate(str("nebio_scan_hz"), nebioScanHz_);
    nebioDigitalHz_ = rate(str("nebio_digital_hz"), nebioDigitalHz_);
    nebioAdcHz_ = rate(str("nebio_adc_hz"), nebioAdcHz_);
    onOff("nebio_fast_gpio", nebioFastGpio_);
    onOff("gate_interrupts", gateInterrupts_);
    if (auto h = holdoff(str("gate_holdoff_ms"))) gateHoldoffMs_ = *h;
    if (auto v = get("csound_rt_priority")) {
        if (auto p = pyInt(*v); p && 0 <= *p && *p <= 99) csoundRtPriority_ = *p;
    }
}

// The system boots with Quiet mode and Wi-Fi off. Called after the first
// instrument load: start_wifi.sh mounts the stick.
void ConfigSettings::applyAtStart() {
    std::string regulator = powerRegulator();
    if (servicesQuiet()) runInBackground({{QUIET_SCRIPT, "services", "on"}});
    if (regulator == "yield" || regulator == "shell") runInBackground({{QUIET_SCRIPT, "spin", regulator}});
    runInBackground({{WIFI_SCRIPT, wifiOn() ? "on" : "off"}});
    runInBackground({});
}

bool ConfigSettings::setPowerRegulator(const std::string &value) {
    if (!in(POWER_REGULATOR, value)) throw PyError("ValueError", "power_regulator off|yield|shell|nohlt");
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (value == powerRegulator_) return false;
        powerRegulator_ = value;
        save();
    }
    NLOG(cfgLog(), INFO, "Power regulator: %s", value.c_str());
    syncCmdline();  // not in the background: a reboot may follow
    if (powerNeedsRestart()) return true;
    runInBackground({{QUIET_SCRIPT, "spin", value != "nohlt" ? value : "off"}});
    return false;
}

#define NEB_ON_OFF_SETTER(method, field, text, extra)                        \
    void ConfigSettings::method(bool on) {                                  \
        {                                                                    \
            std::lock_guard<std::mutex> lock(mutex_);                        \
            if (on == field) return;                                         \
            field = on;                                                      \
            save();                                                          \
        }                                                                    \
        NLOG(cfgLog(), INFO, text, on ? "on" : "off");                       \
        extra;                                                               \
    }

NEB_ON_OFF_SETTER(setNoPwm, noPwm_, "No PWM: %s", (void)0)
NEB_ON_OFF_SETTER(setLedStagger, ledStagger_, "LED stagger: %s", (void)0)
NEB_ON_OFF_SETTER(setServicesQuiet, servicesQuiet_, "Services no sounds: %s",
                  runInBackground({{QUIET_SCRIPT, "services", on ? "on" : "off"}}))
NEB_ON_OFF_SETTER(setWifiOn, wifiOn_, "Wi-Fi %s", runInBackground({{WIFI_SCRIPT, on ? "on" : "off"}}))
NEB_ON_OFF_SETTER(setNebioFastGpio, nebioFastGpio_, "nebio fast GPIO: %s", (void)0)
NEB_ON_OFF_SETTER(setGateInterrupts, gateInterrupts_, "Gate interrupts: %s", (void)0)

void ConfigSettings::setLedDim(const Value &value) {
    double v = pyRound(clampF(toFloat(value), 0.0, 1.0), 2);
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (v == ledDim_) return;
        ledDim_ = v;
        save();
    }
    NLOG(cfgLog(), INFO, "LED dim %.2f", v);
}

void ConfigSettings::setGateHoldoffMs(const Value &msValue) {
    auto ms = holdoff(msValue);
    if (!ms) throw PyError("ValueError", "gate_holdoff_ms 0-100");
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (*ms == gateHoldoffMs_) return;
        gateHoldoffMs_ = *ms;
        save();
    }
    NLOG(cfgLog(), INFO, "Gate hold-off %.1f ms", *ms);
}

std::tuple<long long, long long, long long> ConfigSettings::setNebioRates(const Value &scan, const Value &digital,
                                                                         const Value &adc) {
    std::tuple<long long, long long, long long> rates;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        long long s = std::min<long long>(SCAN_HZ_MAX, std::max<long long>(SCAN_HZ_MIN,
                                          toInt(scan.isNone() ? I(nebioScanHz_) : scan)));
        long long d = std::min<long long>(s, std::max<long long>(1, toInt(digital.isNone() ? I(nebioDigitalHz_) : digital)));
        long long a = std::min<long long>(s, std::max<long long>(1, toInt(adc.isNone() ? I(nebioAdcHz_) : adc)));
        rates = {s, d, a};
        if (rates != std::make_tuple(nebioScanHz_, nebioDigitalHz_, nebioAdcHz_)) {
            nebioScanHz_ = s;
            nebioDigitalHz_ = d;
            nebioAdcHz_ = a;
            save();
        }
    }
    NLOG(cfgLog(), INFO, "nebio input rates (scan, digital, adc): (%lld, %lld, %lld)", std::get<0>(rates),
         std::get<1>(rates), std::get<2>(rates));
    return rates;
}

// Synced with its folder: else the rename reaches the SD card only after up
// to 5 s, and a case switched off sooner keeps the old values.
void ConfigSettings::save() {
    char buf[1024];
    std::snprintf(buf, sizeof buf,
                  "power_regulator=%s\nno_pwm=%s\nled_stagger=%s\nservices_quiet=%s\nwifi=%s\nled_dim=%.2f\n"
                  "log_level=%s\nnebio_scan_hz=%lld\nnebio_digital_hz=%lld\nnebio_adc_hz=%lld\n"
                  "nebio_fast_gpio=%s\ncsound_rt_priority=%lld\ngate_interrupts=%s\ngate_holdoff_ms=%.1f\n",
                  powerRegulator_.c_str(), noPwm_ ? "on" : "off", ledStagger_ ? "on" : "off",
                  servicesQuiet_ ? "on" : "off", wifiOn_ ? "on" : "off", ledDim_, logLevel_.c_str(), nebioScanHz_,
                  nebioDigitalHz_, nebioAdcHz_, nebioFastGpio_ ? "on" : "off", csoundRtPriority_,
                  gateInterrupts_ ? "on" : "off", gateHoldoffMs_);
    std::string err;
    if (!writeSynced(CONFIG_FILE, buf, err))
        NLOG(cfgLog(), ERROR, "Could not save %s: %s", CONFIG_FILE.c_str(), err.c_str());
}

// One thread: the scripts run in the order the settings were changed.
void ConfigSettings::runInBackground(ConfigJob job) {
    if (runInBackgroundHook) {
        runInBackgroundHook(job);
        return;
    }
    std::lock_guard<std::mutex> lock(jobsMutex_);
    if (!started_) {
        started_ = true;
        thread_ = std::thread(&ConfigSettings::worker, this);
    }
    jobs_.push_back(std::move(job));
    ++pending_;
    jobsCv_.notify_all();
}

void ConfigSettings::worker() {
    while (true) {
        ConfigJob job;
        {
            std::unique_lock<std::mutex> lock(jobsMutex_);
            jobsCv_.wait(lock, [&] { return stop_ || !jobs_.empty(); });
            if (stop_ && jobs_.empty()) return;
            job = std::move(jobs_.front());
            jobs_.pop_front();
        }
        try {
            if (job.command.empty()) {
                syncCmdline();
            } else {
                std::string cmd = "systemd-cat -t nebulae-config /bin/bash";
                for (auto &a : job.command) cmd += " '" + a + "'";
                std::system((cmd + " </dev/null").c_str());
            }
        } catch (const std::exception &e) {
            NLOG(cfgLog(), ERROR, "Could not run job: %s", e.what());
        }
        {
            std::lock_guard<std::mutex> lock(jobsMutex_);
            --pending_;
        }
        jobsCv_.notify_all();
    }
}

void ConfigSettings::syncCmdline() {
    std::lock_guard<std::mutex> cmdlineLock(cmdlineMutex_);
    bool want = wantNohlt();
    std::istringstream f(textfile::read(CMDLINE));
    std::vector<std::string> words;
    std::string w;
    while (f >> w) words.push_back(w);
    bool has = std::find(words.begin(), words.end(), "nohlt") != words.end();
    if (has == want) return;
    std::string text;
    for (auto &x : words) {
        if (x == "nohlt") continue;
        text += (text.empty() ? "" : " ") + x;
    }
    if (want) text += (text.empty() ? "" : " ") + std::string("nohlt");
    std::string err;
    if (!writeSynced(CMDLINE, text + "\n", err)) throw PyError("OSError", err);
    NLOG(cfgLog(), INFO, "%s nohlt in %s: active from the next restart", want ? "Added" : "Removed",
         CMDLINE.c_str());
}

void ConfigSettings::waitUntilApplied() {
    std::unique_lock<std::mutex> lock(jobsMutex_);
    jobsCv_.wait(lock, [&] { return pending_ == 0; });
}

ConfigSettings &configSettings() {
    static ConfigSettings settings;
    return settings;
}

}  // namespace neb
