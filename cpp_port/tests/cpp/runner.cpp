// Runs a scenario (tests/scenarios/*.txt) against the C++ port and prints the
// trace: "L<line> <result>". The same ops and fakes as tests/py/runner.py;
// compare.py checks both traces are identical.
#include <dirent.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "classlogger.h"
#include "configsettings.h"
#include "control.h"
#include "controlhandler.h"
#include "controlhandlerPD.h"
#include "controlhandlerProg.h"
#include "controlhandlerSC.h"
#include "digitaldata.h"
#include "encoderpages.h"
#include "fatal.h"
#include "inputs.h"
#include "nconfig.h"
#include "nebconfig.h"
#include "nebio.h"
#include "nebmixer.h"
#include "senders.h"
#include "settings.h"
#include "textfile.h"
#include "wavewriter.h"

using namespace neb;

namespace {

std::string esc(const std::string &s) {
    std::string out;
    for (char c : s) out += c == '\n' ? std::string("\\n") : std::string(1, c);
    return out;
}

std::string fmt(const Value &v) {
    switch (v.type) {
    case Value::None: return "None";
    case Value::Bool: return std::string("b:") + (v.b ? "True" : "False");
    case Value::Int: return "i:" + std::to_string(v.i);
    case Value::Float: return "f:" + pyRepr(v.f);
    case Value::Str: return "s:" + esc(v.s);
    case Value::List: {
        std::string out = "[";
        for (size_t k = 0; k < v.list.size(); ++k) out += (k ? "," : "") + fmt(v.list[k]);
        return out + "]";
    }
    }
    return "?";
}

Value B(bool b) { return Value::boolean(b); }
Value S(const std::string &s) { return Value::str(s); }
Value L(std::vector<Value> v) { return Value::of(std::move(v)); }

// "i:3 f:0.5 b:True s:text None L:a,b", else a number.
Value number(const std::string &text) {
    std::string low;
    for (char c : text) low += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    if (low.find_first_of(".e") != std::string::npos || low.find("inf") != std::string::npos ||
        low.find("nan") != std::string::npos) {
        auto f = pyFloat(text);
        if (!f) throw PyError("ValueError", "could not convert string to float");
        return F(*f);
    }
    auto i = pyInt(text);
    if (!i) throw PyError("ValueError", "invalid literal for int()");
    return I(*i);
}

Value val(const std::string &text) {
    if (text == "None") return Value();
    size_t colon = text.find(':');
    std::string kind = colon == std::string::npos ? text : text.substr(0, colon);
    std::string rest = colon == std::string::npos ? "" : text.substr(colon + 1);
    if (colon != std::string::npos) {
        if (kind == "i") return number(rest).type == Value::Int ? number(rest) : throw PyError("ValueError", "int");
        if (kind == "f") {
            auto f = pyFloat(rest);
            if (!f) throw PyError("ValueError", "float");
            return F(*f);
        }
        if (kind == "b") return B(rest == "True");
        if (kind == "s") return S(rest);
        if (kind == "L") {
            std::vector<Value> out;
            size_t start = 0;
            if (!rest.empty())
                while (true) {
                    size_t c = rest.find(',', start);
                    out.push_back(S(rest.substr(start, c == std::string::npos ? std::string::npos : c - start)));
                    if (c == std::string::npos) break;
                    start = c + 1;
                }
            return L(out);
        }
    }
    return number(text);
}

int ival(const std::string &t) { return static_cast<int>(toInt(number(t))); }

std::vector<std::string> tokens(const std::string &line) {
    std::vector<std::string> out;
    std::istringstream in(line);
    std::string t;
    while (in >> t) {
        size_t p;
        while ((p = t.find("\\_")) != std::string::npos) t.replace(p, 2, " ");
        out.push_back(t);
    }
    return out;
}

// ---- fakes (as tests/py/harness.py) -------------------------------------

class FakeClock : public Clock {
public:
    double t = 1000.0;
    double time() override { return t; }
    void sleep(double s) override { t += s; }
};

class FakeRandom : public Random {
public:
    std::deque<int> queue;
    int randint(int a, int b) override {
        int v = a;
        if (!queue.empty()) {
            v = queue.front();
            queue.pop_front();
        }
        return std::min(b, std::max(a, v));
    }
};

class FakeNebioC : public NebioC {
public:
    std::vector<std::string> calls;
    int adc[16] = {};
    int gpio[64];
    int sr = 0;
    long long snapN = 0;
    std::map<std::string, Value> ret;

    FakeNebioC() {
        for (int &g : gpio) g = -1;
    }
    void log(const std::string &name, std::vector<Value> args) {
        std::string s = name + "(";
        for (size_t k = 0; k < args.size(); ++k) s += (k ? "," : "") + fmt(args[k]);
        calls.push_back(s + ")");
    }
    int r(const std::string &name) {
        auto it = ret.find(name);
        return it == ret.end() ? 0 : static_cast<int>(toInt(it->second));
    }
    int call(const std::string &name, std::vector<Value> args = {}) {
        log(name, std::move(args));
        return r(name);
    }

    int inputs_init() override { return call("inputs_init"); }
    std::string last_error() override { return "fake error"; }
    long long snapshot() override { return ++snapN; }
    int sr_bits() override { return sr; }
    int adc_codes(int *out, int n) override {
        for (int i = 0; i < n; ++i) out[i] = adc[i];
        return n;
    }
    int gpio_levels(int *out, int n) override {
        for (int i = 0; i < n; ++i) out[i] = gpio[i];
        return n;
    }
    int encoder_id(int a, int b) override { return call("encoder_id", {I(a), I(b)}); }
    int encoder_steps(int id) override { return call("encoder_steps", {I(id)}); }
    void encoder_set_raw(int id, int on) override { call("encoder_set_raw", {I(id), I(on)}); }
    int encoder_raw(int id) override { return call("encoder_raw", {I(id)}); }
    void encoder_set_click(int id, int on) override { call("encoder_set_click", {I(id), I(on)}); }
    void set_eol(int h) override { call("set_eol", {I(h)}); }
    int set_input_rates(int s, int d, int a) override { return call("set_input_rates", {I(s), I(d), I(a)}); }
    int input_scan_hz() override { return call("input_scan_hz"); }
    int input_digital_hz() override { return call("input_digital_hz"); }
    int input_adc_hz() override { return call("input_adc_hz"); }
    void set_scan_jitter(double f) override { call("set_scan_jitter", {F(f)}); }
    void set_scan_trigger(int e) override { call("set_scan_trigger", {I(e)}); }
    void scan_trigger() override { call("scan_trigger"); }
    int set_fast_gpio(int on) override { return call("set_fast_gpio", {I(on)}); }
    int fast_gpio() override { return call("fast_gpio"); }
    int set_gate_interrupts(int on) override { return call("set_gate_interrupts", {I(on)}); }
    int gate_interrupts() override { return call("gate_interrupts"); }
    void set_gate_holdoff_us(int us) override { call("set_gate_holdoff_us", {I(us)}); }
    std::string stats() override { return "fake stats"; }
    void led_clear_sc() override { call("led_clear_sc"); }
    void shutdown() override { call("shutdown"); }
    int sc_open_sender() override { return call("sc_open_sender"); }
    void sc_close_sender() override { call("sc_close_sender"); }
    int sc_sender_open() override { return call("sc_sender_open"); }
    int sc_start_listener() override { return call("sc_start_listener"); }
    void sc_stop_listener() override { call("sc_stop_listener"); }
    int sc_listener_running() override { return call("sc_listener_running"); }
    void sc_send_int(const std::string &n, int v) override { call("sc_send_int", {S(n), I(v)}); }
    void sc_send_float(const std::string &n, double v) override { call("sc_send_float", {S(n), F(v)}); }
    void sc_send_bool(const std::string &n, int v) override { call("sc_send_bool", {S(n), I(v)}); }
    void sc_send_string(const std::string &n, const std::string &v) override {
        call("sc_send_string", {S(n), S(v)});
    }
    void sc_send_path_int(const std::string &p, int v) override { call("sc_send_path_int", {S(p), I(v)}); }
    void sc_send_path_float(const std::string &p, double v) override { call("sc_send_path_float", {S(p), F(v)}); }
    void sc_clear_cache() override { call("sc_clear_cache"); }
    int sc_synth_is_up() override { return call("sc_synth_is_up"); }
    void sc_set_synth_down() override { call("sc_set_synth_down"); }
    int sc_handshake() override { return call("sc_handshake"); }
    void sc_zero_handshake() override { call("sc_zero_handshake"); }
    int card_clip_count() override { return call("card_clip_count"); }
    int osc_open(int port) override { return call("osc_open", {I(port)}); }
    void osc_close() override { call("osc_close"); }
    void osc_send_float(const std::string &p, double v) override { call("osc_send_float", {S(p), F(v)}); }
    void pd_connect() override { call("pd_connect"); }
    void pd_close() override { call("pd_close"); }
    int pd_is_connected() override { return call("pd_is_connected"); }
    int pd_take_ready() override { return call("pd_take_ready"); }
    int pd_send(const std::string &d) override {
        return call("pd_send", {S(d), I(static_cast<long long>(d.size()))});
    }
};

class FakeCsound : public Csound {
public:
    std::map<std::string, double> chans;
    std::map<int, std::vector<double>> tables;
    std::vector<std::string> calls;
    std::vector<double> table(int number) override {
        calls.push_back("table(" + std::to_string(number) + ")");
        auto it = tables.find(number);
        return it == tables.end() ? std::vector<double>() : it->second;
    }
    double *channelPtr(const std::string &name, int flags) override {
        calls.push_back("channelPtr(" + name + "," + std::to_string(flags) + ")");
        return &chans[name];
    }
    void setControlChannel(const std::string &name, const Value &v) override {
        calls.push_back("setControlChannel(" + name + "," + fmt(v) + ")");
        chans[name] = v.number();
    }
};

class FakeUsb : public UsbStick {
public:
    bool mounted = true;
    std::vector<std::string> calls;
    void mount() override { calls.push_back("mount"); }
    void umount() override { calls.push_back("umount"); }
    bool isUSBMounted() override { return mounted; }
};

class Runner;

class FakeAsound : public Asound {
public:
    explicit FakeAsound(Runner &r) : runner(r) {}
    Runner &runner;
    std::set<std::string> fail, nohandle;
    void *const handle = reinterpret_cast<void *>(1234);

    static std::string p(void *x) { return x ? "i:" + std::to_string(reinterpret_cast<intptr_t>(x)) : "None"; }
    int log(const std::string &name, const std::string &args);
    int mixer_open(void **, int mode) override { return log("snd_mixer_open", "&,i:" + std::to_string(mode)); }
    int mixer_attach(void *m, const std::string &d) override { return log("snd_mixer_attach", p(m) + ",s:" + d); }
    int mixer_detach(void *m, const std::string &d) override { return log("snd_mixer_detach", p(m) + ",s:" + d); }
    int mixer_selem_register(void *m) override { return log("snd_mixer_selem_register", p(m) + ",None,None"); }
    int mixer_load(void *m) override { return log("snd_mixer_load", p(m)); }
    int mixer_close(void *m) override { return log("snd_mixer_close", p(m)); }
    void *mixer_find_selem_name(void *m, const std::string &name) override {
        int r = log("snd_mixer_find_selem", p(m) + ",s:" + name);
        (void)r;
        return nohandle.count("capture") ? nullptr : handle;
    }
    int selem_id_malloc(void **) override { return log("snd_mixer_selem_id_malloc", "&"); }
    void selem_id_set_name(void *sid, const std::string &n) override {
        log("snd_mixer_selem_id_set_name", p(sid) + ",s:" + n);
    }
    void selem_id_set_index(void *sid, unsigned i) override {
        log("snd_mixer_selem_id_set_index", p(sid) + ",i:" + std::to_string(i));
    }
    void *mixer_find_selem(void *m, void *sid) override {
        log("snd_mixer_find_selem", p(m) + "," + p(sid));
        return nohandle.count("hifi") ? nullptr : handle;
    }
    int selem_set_capture_volume(void *e, int ch, long v) override {
        return log("snd_mixer_selem_set_capture_volume", p(e) + ",i:" + std::to_string(ch) + ",i:" + std::to_string(v));
    }
    int selem_set_playback_switch_all(void *e, int v) override {
        return log("snd_mixer_selem_set_playback_switch_all", p(e) + ",i:" + std::to_string(v));
    }
};

// ---- the runner -----------------------------------------------------------

struct Obj {
    std::unique_ptr<Switch> sw;
    std::unique_ptr<ShiftRegister> sr;
    std::unique_ptr<MCP3208> mcp;
    std::unique_ptr<InputData> data;  // adc, hyb, st, raw, dd
    std::unique_ptr<CommChannel> comm;
    std::unique_ptr<ControlChannel> ctl;
    std::unique_ptr<Page> pg;
    std::unique_ptr<EncoderPages> ep;
    std::unique_ptr<PageState> ps;
    std::unique_ptr<SettingManager> set;
    std::unique_ptr<WaveWriter> wav;
    std::unique_ptr<PdSend> pd;
    std::unique_ptr<ScSend> sc;
    std::unique_ptr<ConfigSettings> cfg;
    std::unique_ptr<NConfig> ini;
    std::unique_ptr<NebConfig> nc;
    std::unique_ptr<OrderedDict> ncDict;  // the handler's configData lives as long as it
    std::unique_ptr<WaveWriter> hWriter;
    std::unique_ptr<ControlHandler> h;
};

FakeClock fakeClock;
FakeRandom fakeRandom;
FakeNebioC clib;
FakeUsb usb;

// fatal's exit in the tests.
struct FatalStop {};

class Runner {
public:
    explicit Runner(std::string dir) : dir_(std::move(dir)) {
        ::chdir(dir_.c_str());
        calibrationPath = path("calibration_data.txt");
        config::CONFIG_FILE = path("configsettings.txt");
        config::REQUEST_FILE = path("config_request");
        config::CMDLINE = path("cmdline.txt");
        config::kernelHasNohlt = [this] { return cmdlineNohlt_; };
        reloadControlDefaults("./nebulae.opt");

        fatal::INSTR_DIRS = {{"instr", path("instr") + "/", ".instr"},
                             {"supercollider", path("sc") + "/", ".scd"},
                             {"puredata", path("pd") + "/", ".pd"},
                             {"programs", path("prog") + "/", ".prog"}};
        fatal::STICK = path("stick") + "/";
        fatal::MARKER = path("nebulae-fatal");
        fatal::Backend &b = fatal::backend();
        b.log = [this](const std::string &line) { emit("fatal log " + line); };
        b.now = [] { return std::string("2026-11-13 12:00:00"); };
        b.stopNebio = [this] { emit("fatal stopNebio"); };
        b.stickMounted = [this] { return stickMounted_; };
        b.run = [this](const std::vector<std::string> &cmd) { return fatalRun(cmd); };
        b.exit = [this](int code) {
            emit("fatal exit " + std::to_string(code));
            throw FatalStop();
        };
    }

    std::string path(const std::string &name) const { return dir_ + "/" + name; }
    // The work dir differs between the runners: "W" in the trace.
    void emit(std::string text) {
        for (size_t p; (p = text.find(dir_)) != std::string::npos;) text.replace(p, dir_.size(), "W");
        out.push_back("L" + std::to_string(line_) + " " + text);
    }
    void put(const Value &v) { emit(fmt(v)); }

    std::vector<std::string> run(const std::vector<std::string> &lines) {
        for (size_t n = 0; n < lines.size(); ++n) {
            std::string l = strip(lines[n]);
            if (l.empty() || l[0] == '#') continue;
            line_ = static_cast<int>(n + 1);
            auto t = tokens(l);
            try {
                op(t[0], std::vector<std::string>(t.begin() + 1, t.end()));
            } catch (const FatalStop &) {
                emit("STOPPED");
            } catch (const PyError &e) {
                emit("E:" + e.type);
            } catch (const std::out_of_range &) {
                emit("E:IndexError");
            }
        }
        return out;
    }

    std::vector<std::string> out;

private:
    Obj &o(const std::string &id) {
        auto it = objs_.find(id);
        if (it == objs_.end()) throw PyError("KeyError", id);
        return it->second;
    }

    template <class T>
    T &data(const std::string &id) {
        auto *p = dynamic_cast<T *>(o(id).data.get());
        if (!p) throw PyError("AttributeError", id);
        return *p;
    }

    EncoderMap pagesDict(const std::string &spec) {
        EncoderMap m;
        if (spec == "-") return m;
        size_t start = 0;
        while (true) {
            size_t c = spec.find(',', start);
            std::string part = spec.substr(start, c == std::string::npos ? std::string::npos : c - start);
            size_t eq = part.find('=');
            std::string name = part.substr(0, eq);
            EncoderPages *ep = o(part.substr(eq + 1)).ep.get();
            bool found = false;
            for (auto &kv : m)
                if (kv.first == name) {
                    kv.second = ep;
                    found = true;
                }
            if (!found) m.emplace_back(name, ep);
            if (c == std::string::npos) break;
            start = c + 1;
        }
        return m;
    }

    std::unique_ptr<WaveWriter> makeWriter() {
        auto w = std::make_unique<WaveWriter>(usb, path("buffer_cnt.txt"), path("memory") + "/");
        w->statvfs = [this](const std::string &) {
            if (haveDisk_) return disk_;
            struct statvfs st {};
            if (::statvfs(path("memory").c_str(), &st) != 0)
                throw PyError(errno == ENOENT ? "FileNotFoundError" : "OSError", "statvfs");
            DiskSpace d;
            d.f_bsize = st.f_bsize;
            d.f_bfree = st.f_bfree;
            return d;
        };
        return w;
    }

    static void waveData(const std::string &kind, size_t n, std::vector<double> &left, std::vector<double> &right) {
        left.assign(n, 0.0);
        right.assign(n, 0.0);
        for (size_t i = 0; i < n; ++i) {
            double x = static_cast<double>(i);
            if (kind == "tri") {
                left[i] = std::fmod(x * 37, 1000.0) / 500.0 - 1.0;
                right[i] = std::fmod(x * 91, 999.0) / 499.5 - 1.0;
            } else if (kind == "ramp") {
                left[i] = std::fmod(x, 200.0) / 100.0 - 1.0;
                right[i] = 1.0 - std::fmod(x, 77.0) / 38.5;
            }
        }
    }

    static Value strs(const std::vector<std::string> &v) {
        std::vector<Value> l;
        for (auto &x : v) l.push_back(S(x));
        return L(l);
    }

    static Value pageSpecs(const EncoderPageSpecs &pages) {
        std::vector<Value> l;
        for (auto &[e, specs] : pages) {
            std::vector<Value> ps;
            for (auto &p : specs)
                ps.push_back(L({S(p.name), S(p.path), F(p.lo), F(p.hi), S(p.curve), F(p.value), F(p.step)}));
            l.push_back(L({S(e), L(ps)}));
        }
        return L(l);
    }

    EncoderControlHandler &enc(const std::string &id) {
        auto *h = dynamic_cast<EncoderControlHandler *>(o(id).h.get());
        if (!h) throw PyError("AttributeError", id);
        return *h;
    }

    SCControlHandler &sc(const std::string &id) {
        auto *h = dynamic_cast<SCControlHandler *>(o(id).h.get());
        if (!h) throw PyError("AttributeError", id);
        return *h;
    }

    std::function<void()> ltCb(const std::string &name) {
        return [this, name] { emit("LONGTOUCH " + name); };
    }

    void writeFile(const std::string &name, const std::vector<std::string> &a, size_t from) {
        std::string text;
        for (size_t k = from; k < a.size(); ++k) text += (k > from ? " " : "") + a[k];
        for (auto &c : text)
            if (c == '|') c = '\n';
        std::ofstream f(path(name), std::ios::binary | std::ios::trunc);
        f << text;
    }

    void op(const std::string &op, const std::vector<std::string> &a);
    void nebioOp(const std::string &name, const std::vector<std::string> &a);
    void methodOp(const std::string &prefix, const std::string &method, const std::vector<std::string> &a);
    void handlerMethod(ControlHandler &h, const std::string &method, const std::vector<Value> &args);

    // As Runner.passes in tests/py/runner.py: returns the timed seconds.
    double passes(long long first, long long n, ShiftRegister &srg, const std::vector<ControlChannel *> &chans,
                  std::vector<Value> &last, std::vector<long long> &changes, ScSend *sender) {
        double total = 0.0;
        for (long long i = first; i < first + n; ++i) {
            fakeClock.t += 0.001;
            for (int k = 0; k < 16; ++k) clib.adc[k] = static_cast<int>((i * 37 + k * 101) % 4096);
            clib.sr = static_cast<int>((i / 100) % 256);
            for (int p : {4, 6, 23, 24, 25}) clib.gpio[p] = static_cast<int>((i / (50 + p)) % 2);
            nebio::snapshot();
            auto t0 = std::chrono::steady_clock::now();
            srg.update();
            for (size_t j = 0; j < chans.size(); ++j) {
                chans[j]->update();
                Value v = chans[j]->getValue();
                if (v != last[j]) {
                    ++changes[j];
                    last[j] = v;
                }
            }
            total += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            if (sender)
                for (auto *c : chans) sender->send(c->name, c->getValue());
        }
        return total;
    }

    std::string fatalRun(const std::vector<std::string> &cmd) {
        std::string line;
        for (size_t k = 0; k < cmd.size(); ++k) line += (k ? " " : "") + cmd[k];
        emit("fatal run " + line);
        if (cmd[0] == "mount" && stickMountable_)
            stickMounted_ = true;
        else if (cmd[0] == "umount")
            stickMounted_ = false;
        else if (cmd[0] == "journalctl")
            return "journal line 1\njournal line 2\n";
        return "";
    }

    std::string dir_;
    int line_ = 0;
    bool stickMounted_ = false;
    bool stickMountable_ = true;
    std::map<std::string, Obj> objs_;
    std::unique_ptr<FakeCsound> cs_;
    std::vector<std::unique_ptr<OrderedDict>> cfgdatas_;
    OrderedDict *cfgdata_ = nullptr;
    std::unique_ptr<FakeAsound> asound_;
    bool haveDisk_ = false;
    DiskSpace disk_;
    bool cmdlineNohlt_ = false;

    friend class FakeAsound;
};

int FakeAsound::log(const std::string &name, const std::string &args) {
    runner.emit("asound " + name + "(" + args + ")");
    return fail.count(name) ? -1 : 0;
}

void Runner::op(const std::string &op, const std::vector<std::string> &a) {
    auto need = [&](size_t n) {
        if (a.size() < n) throw PyError("IndexError", "list index out of range");
    };
    // --- fakes -----------------------------------------------------------------
    if (op == "time") { fakeClock.t = val(a.at(0)).number(); }
    else if (op == "advance") { fakeClock.t += val(a.at(0)).number(); }
    else if (op == "rand") { for (auto &x : a) fakeRandom.queue.push_back(ival(x)); }
    else if (op == "ret") { clib.ret[a.at(0)] = val(a.at(1)); }
    else if (op == "gpio") { clib.gpio[ival(a.at(0))] = ival(a.at(1)); }
    else if (op == "sr") { clib.sr = ival(a.at(0)); }
    else if (op == "adc") { clib.adc[ival(a.at(0)) * 8 + ival(a.at(1))] = ival(a.at(2)); }
    else if (op == "calls") {
        for (auto &c : clib.calls) emit("call " + c);
        clib.calls.clear();
    }
    else if (op == "cs.new") { cs_ = std::make_unique<FakeCsound>(); }
    else if (op == "cs.none") { cs_.reset(); }
    else if (op == "cs.chan") { cs_->chans[a.at(0)] = toFloat(val(a.at(1))); }
    else if (op == "cs.read") {
        auto it = cs_->chans.find(a.at(0));
        put(it == cs_->chans.end() ? Value() : F(it->second));
    }
    else if (op == "cs.tables") {
        waveData(a.at(0), static_cast<size_t>(ival(a.at(1))), cs_->tables[200], cs_->tables[201]);
    }
    else if (op == "cs.calls") {
        for (auto &c : cs_->calls) emit("cs " + c);
        cs_->calls.clear();
    }
    else if (op == "usb.mounted") { usb.mounted = a.at(0) == "1"; }
    else if (op == "usb.calls") {
        for (auto &c : usb.calls) emit("usb " + c);
        usb.calls.clear();
    }
    else if (op == "disk") {
        haveDisk_ = a.at(0) != "real";
        if (haveDisk_) disk_ = {static_cast<unsigned long long>(ival(a.at(0))), static_cast<unsigned long long>(ival(a.at(1)))};
    }
    else if (op == "file.write") { writeFile(a.at(0), a, 1); }
    else if (op == "file.read") {
        std::ifstream f(path(a.at(0)), std::ios::binary);
        if (!f) { emit("file " + a[0] + " missing"); return; }
        std::string data((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
        std::string shown;  // as Python: the bytes read as Latin-1, printed as UTF-8
        for (unsigned char c : data) {
            if (c == '\n') {
                shown += '|';
            } else if (c < 0x80) {
                shown += static_cast<char>(c);
            } else {
                shown += static_cast<char>(0xC0 | (c >> 6));
                shown += static_cast<char>(0x80 | (c & 0x3F));
            }
        }
        emit("file " + a[0] + " " + shown);
    }
    else if (op == "file.hex") {
        std::ifstream f(path(a.at(0)), std::ios::binary);
        std::string data((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
        char hex[3];
        std::string h;
        for (size_t k = 0; k < data.size() && k < 48; ++k) {
            std::snprintf(hex, sizeof hex, "%02x", static_cast<unsigned char>(data[k]));
            h += hex;
        }
        // sha256 via the system tool: the test only needs equal hashes.
        std::string cmd = "sha256sum '" + path(a[0]) + "'";
        std::FILE *p = popen(cmd.c_str(), "r");
        char buf[128] = {};
        if (p) {
            if (!std::fgets(buf, sizeof buf, p)) buf[0] = 0;
            pclose(p);
        }
        std::string sum(buf);
        sum = sum.substr(0, sum.find(' '));
        emit("file " + a[0] + " " + std::to_string(data.size()) + " " + h + " " + sum);
    }
    else if (op == "file.rm") { std::remove(path(a.at(0)).c_str()); }
    else if (op == "bench" || op == "soak") {
        // As Runner.bench / Runner.soak in tests/py/runner.py.
        bool soak = op == "soak";
        size_t at = soak ? 4 : 2;
        long long chunks = soak ? ival(a.at(0)) : 1, n = ival(a.at(soak ? 1 : 0));
        ShiftRegister &srg = *o(a.at(soak ? 2 : 1)).sr;
        ScSend *sender = soak ? o(a.at(3)).sc.get() : nullptr;
        std::vector<ControlChannel *> chans;
        for (size_t k = at; k < a.size(); ++k) chans.push_back(o(a[k]).ctl.get());
        std::vector<Value> last;
        for (auto *c : chans) last.push_back(c->getValue());
        std::vector<long long> changes(chans.size(), 0);
        double total = 0.0;
        std::string rss;
        for (long long chunk = 0; chunk < chunks; ++chunk) {
            total += passes(chunk * n, n, srg, chans, last, changes, sender);
            if (!soak) continue;
            clib.calls.clear();  // the fake's call log, not the code under test
            std::ifstream statm("/proc/self/statm");
            long long size = 0, resident = 0;
            statm >> size >> resident;
            rss += (rss.empty() ? "" : " ") + std::to_string(resident * ::sysconf(_SC_PAGE_SIZE) / 1024);
        }
        if (soak)
            std::fprintf(stderr, "soak c++: %lld x %lld passes (%.1f h at 1 kHz), RSS KB: %s\n", chunks, n,
                         static_cast<double>(chunks * n) / 3.6e6, rss.c_str());
        else
            std::fprintf(stderr, "bench c++: %lld passes, %zu channels: %.2f us/pass\n", n, chans.size(),
                         total / static_cast<double>(n) * 1e6);
        std::vector<Value> out;
        for (size_t j = 0; j < chans.size(); ++j) out.push_back(Value::of({I(changes[j]), last[j]}));
        put(Value::of(out));
    }
    else if (op == "file.bytes") {
        std::string hex, data;
        for (size_t k = 1; k < a.size(); ++k) hex += a[k];
        for (size_t k = 0; k + 1 < hex.size(); k += 2) data += static_cast<char>(std::stoi(hex.substr(k, 2), nullptr, 16));
        std::ofstream f(path(a.at(0)), std::ios::binary | std::ios::trunc);
        f << data;
    }
    else if (op == "ls") {
        DIR *d = ::opendir(path(a.at(0)).c_str());
        if (!d) { emit("ls " + a[0] + " missing"); return; }
        std::vector<std::string> names;
        while (dirent *e = ::readdir(d)) {
            std::string n = e->d_name;
            if (n != "." && n != "..") names.push_back(n);
        }
        ::closedir(d);
        std::sort(names.begin(), names.end());
        std::string joined;
        for (size_t k = 0; k < names.size(); ++k) joined += (k ? "," : "") + names[k];
        emit("ls " + a[0] + " " + joined);
    }
    else if (op == "fatal.on") { fatal::enabled = true; }
    else if (op == "fatal.off") { fatal::enabled = false; }
    else if (op == "stick.mounted") { stickMounted_ = a.at(0) == "1"; }
    else if (op == "stick.mountable") { stickMountable_ = a.at(0) == "1"; }
    else if (op == "tf.read") { put(Value::str(textfile::read(path(a.at(0))))); }
    else if (op == "tf.lines") {
        std::vector<Value> v;
        for (auto &l : textfile::lines(path(a.at(0)))) v.push_back(Value::str(l));
        put(Value::of(v));
    }
    else if (op == "tf.instrument") {
        auto i = fatal::instrumentOf(path(a.at(0)));
        put(i ? Value::of({Value::str(i->first), Value::str(i->second)}) : Value());
    }
    else if (op == "mkdir") { ::mkdir(path(a.at(0)).c_str(), 0777); }
    else if (op == "rmdir") { std::system(("rm -rf '" + path(a.at(0)) + "'").c_str()); }
    // --- nebio.py ----------------------------------------------------------------
    else if (op.rfind("n.", 0) == 0) { nebioOp(op.substr(2), a); }
    // --- switch / shiftregister / MCP3208 ----------------------------------------
    else if (op == "sw.new") { objs_[a.at(0)].sw = std::make_unique<Switch>(ival(a.at(1))); }
    else if (op == "sr.new") { objs_[a.at(0)].sr = std::make_unique<ShiftRegister>(); }
    else if (op == "mcp.new") { objs_[a.at(0)].mcp = std::make_unique<MCP3208>(ival(a.at(1))); }
    // --- control.py -------------------------------------------------------------
    else if (op == "hyst") { put(addHysteresis(val(a.at(0)), val(a.at(1)), val(a.at(2)))); }
    else if (op == "control.reload") {
        if (a.at(0) == "none") std::remove(path("nebulae.opt").c_str());
        else writeFile("nebulae.opt", a, 0);
        reloadControlDefaults("./nebulae.opt");
    }
    else if (op == "adc.new") {
        need(7);
        objs_[a[0]].data = std::make_unique<AdcData>(ival(a[1]), ival(a[2]), a[3], val(a[4]), val(a[5]), val(a[6]));
    }
    else if (op == "hyb.new") {
        need(6);
        objs_[a[0]].data = std::make_unique<HybridData>(ival(a[1]), a[2], val(a[3]), val(a[4]), val(a[5]));
    }
    else if (op == "st.new") { objs_[a.at(0)].data = std::make_unique<StaticData>(val(a.at(1))); }
    else if (op == "raw.new") { objs_[a.at(0)].data = std::make_unique<RawEncoderData>(a.at(1)); }
    else if (op == "comm.new") { objs_[a.at(0)].comm = std::make_unique<CommChannel>(cs_.get(), a.at(1)); }
    else if (op == "ctl.new") {
        need(4);
        ControlChannel::Options opt;
        for (size_t k = 4; k < a.size(); ++k) {
            size_t eq = a[k].find('=');
            std::string key = a[k].substr(0, eq), v = a[k].substr(eq + 1);
            if (key == "sr") opt.sr = o(v).sr.get();
            else if (key == "config") {
                size_t c = v.find(',');
                opt.config = std::vector<std::string>{v.substr(0, c)};
                if (c != std::string::npos) opt.config->push_back(v.substr(c + 1));
            }
            else if (key == "longtouch_cb") opt.longtouch_cb = ltCb(a[1]);
            else if (key == "data_channel") opt.data_channel = static_cast<int>(toInt(val(v)));
            else if (key == "gate_pin") opt.gate_pin = static_cast<int>(toInt(val(v)));
            else if (key == "button_pin") opt.button_pin = static_cast<int>(toInt(val(v)));
            else if (key == "minimum") opt.minimum = val(v);
            else if (key == "maximum") opt.maximum = val(v);
            else if (key == "cvchn") opt.cvchn = static_cast<int>(toInt(val(v)));
            else throw PyError("TypeError", "unexpected keyword " + key);
        }
        objs_[a[0]].ctl = std::make_unique<ControlChannel>(cs_.get(), a[1], val(a[2]), a[3], opt);
    }
    else if (op == "ctl.chan") { put(o(a.at(0)).ctl->channelValue()); }
    else if (op == "calib") { writeFile("calibration_data.txt", a, 0); }
    else if (op == "calib.none") { std::remove(path("calibration_data.txt").c_str()); }
    // --- digitaldata.py -----------------------------------------------------------
    else if (op == "dd.new") {
        need(12);
        ShiftRegister *sr = objs_.count(a[5]) ? objs_[a[5]].sr.get() : nullptr;
        objs_[a[0]].data = std::make_unique<DigitalData>(
            a[1], ival(a[2]), ival(a[3]), ival(a[4]), sr, a[6], a[7], val(a[8]),
            a[9] == "1" ? ltCb(a[1]) : std::function<void()>(), ival(a[10]), val(a[11]));
    }
    // --- encoderpages.py ----------------------------------------------------------
    else if (op == "scale") { put(F(scale(val(a.at(0)), val(a.at(1)), val(a.at(2)), a.at(3)))); }
    else if (op == "pulse") { put(F(pulse(val(a.at(0))))); }
    else if (op == "pg.new") {
        need(7);
        Value step = a.size() > 7 ? val(a[7]) : F(PAGE_STEP);
        objs_[a[0]].pg = std::make_unique<Page>(a[1], a[2], val(a[3]), val(a[4]), a[5], val(a[6]), step);
    }
    else if (op == "pg.value") { put(o(a.at(0)).pg->value); }
    else if (op == "ep.new") {
        need(4);
        std::vector<Page *> pages;
        if (a[2] != "-") {
            size_t start = 0;
            while (true) {
                size_t c = a[2].find(',', start);
                pages.push_back(o(a[2].substr(start, c == std::string::npos ? std::string::npos : c - start)).pg.get());
                if (c == std::string::npos) break;
                start = c + 1;
            }
        }
        std::optional<std::string> target;
        if (a[3] != "None") target = a[3];
        std::optional<Colour> hold;
        if (a.size() > 4) {
            Colour c{};
            std::istringstream in(a[4]);
            std::string x;
            for (int k = 0; k < 3 && std::getline(in, x, ','); ++k) c[k] = static_cast<int>(*pyInt(x));
            hold = c;
        }
        objs_[a[0]].ep = std::make_unique<EncoderPages>(a[1], pages, target, hold);
    }
    else if (op == "ep.outputs") {
        std::vector<Value> out;
        for (auto &kv : o(a.at(0)).ep->outputs(val(a.at(1)))) out.push_back(L({S(kv.first), F(kv.second)}));
        put(L(out));
    }
    else if (op == "ep.state") {
        EncoderPages &p = *o(a.at(0)).ep;
        std::vector<Value> values;
        for (auto *pg : p.pages) values.push_back(pg->value);
        put(L({I(static_cast<long long>(p.current)), p.cv_target ? S(*p.cv_target) : Value(),
               p.candidate ? S(*p.candidate) : Value(), L(values)}));
    }
    else if (op == "ps.new") { objs_[a.at(0)].ps = std::make_unique<PageState>(path(a.at(1))); }
    else if (op == "ps.load") { o(a.at(0)).ps->load(pagesDict(a.at(1))); }
    else if (op == "ps.save") { o(a.at(0)).ps->save(pagesDict(a.at(1))); }
    else if (op == "ps.changed") { o(a.at(0)).ps->changed(val(a.at(1))); }
    else if (op == "ps.saveIfDue") { o(a.at(0)).ps->saveIfDue(val(a.at(1)), pagesDict(a.at(2))); }
    else if (op == "ps.dirty") { put(o(a.at(0)).ps->dirty_time); }
    // --- settings.py --------------------------------------------------------------
    else if (op == "cfgdata") {
        if (a.at(0) == "None") cfgdata_ = nullptr;
        else {
            cfgdatas_.push_back(std::make_unique<OrderedDict>());  // a SettingManager keeps its dict
            cfgdata_ = cfgdatas_.back().get();
            for (auto &item : a) {
                size_t eq = item.find('=');
                cfgdata_->set(item.substr(0, eq), val(item.substr(eq + 1)));
            }
        }
    }
    else if (op == "set.new") {
        auto s = std::make_unique<SettingManager>(cfgdata_);
        s->filepath = dir_ + "/";
        objs_[a.at(0)].set = std::move(s);
    }
    else if (op == "set.lines") {
        std::vector<Value> l;
        for (auto &x : o(a.at(0)).set->lines) l.push_back(S(x));
        put(L(l));
    }
    else if (op == "set.dicts") {
        SettingManager &s = *o(a.at(0)).set;
        for (auto *d : {&s.settingDict, &s.defaultDict, &s.mutableSettings}) {
            if (d == &s.mutableSettings) s.mutable_();
            std::vector<Value> items;
            for (auto &kv : d->items()) items.push_back(L({S(kv.first), kv.second}));
            put(L(items));
        }
    }
    // --- wavewriter.py ------------------------------------------------------------
    else if (op == "wav.new") {
        objs_[a.at(0)].wav = makeWriter();
    }
    else if (op == "wav.write") {
        need(4);
        std::vector<double> left, right;
        waveData(a[3], static_cast<size_t>(ival(a[2])), left, right);
        if (a.size() > 4) right.resize(static_cast<size_t>(ival(a[4])));
        WaveWriter &w = *o(a[0]).wav;
        put(B(w.WriteStereoWaveFile(left, right, val(a[1]))));
        put(w.num_written ? I(*w.num_written) : Value());
    }
    // --- nebmixer.py --------------------------------------------------------------
    else if (op == "mx.reset") {
        asound_ = std::make_unique<FakeAsound>(*this);
        nebmixer::setAsound(a.at(0) == "lib" ? asound_.get() : nullptr);
        nebmixer::resetForTests();
    }
    else if (op == "mx.fail") { asound_->fail.insert(a.at(0)); }
    else if (op == "mx.nohandle") { asound_->nohandle.insert(a.at(0)); }
    else if (op == "mx.init") { put(B(nebmixer::init())); }
    else if (op == "mx.remove") { put(B(nebmixer::remove())); }
    else if (op == "mx.enable") { nebmixer::enable(); put(Value()); }
    else if (op == "mx.disable") { nebmixer::disable(); put(Value()); }
    else if (op == "mx.inputLevel") { nebmixer::inputLevel(val(a.at(0))); put(Value()); }
    // --- pdsender.py / scsender.py ------------------------------------------------
    else if (op == "pd.new") { objs_[a.at(0)].pd = std::make_unique<PdSend>(); }
    else if (op == "sc.new") { objs_[a.at(0)].sc = std::make_unique<ScSend>(); }
    else if (op == "pd.send") {
        std::vector<Value> msgs;
        for (size_t k = 1; k < a.size(); ++k) msgs.push_back(val(a[k]));
        put(B(o(a.at(0)).pd->send(msgs)));
    }
    else if (op == "sc.const") { put(L({I(ScSend::rPort), I(ScSend::sPort), I(PdSend::sport)})); }
    else if (op == "sc.waitSynthIsUp") {
        put(B(o(a.at(0)).sc->waitSynthIsUp(val(a.at(1)).number())));
        put(F(fakeClock.t));
    }
    // --- configsettings.py --------------------------------------------------------
    else if (op == "cmdline.nohlt") { cmdlineNohlt_ = a.at(0) == "1"; }
    else if (op == "cfg.new") {
        auto c = std::make_unique<ConfigSettings>();
        c->runInBackgroundHook = [this](const ConfigJob &job) {
            std::string text;
            for (size_t k = 0; k < job.command.size(); ++k) text += (k ? " " : "") + job.command[k];
            emit("bg " + (job.command.empty() ? std::string("_syncCmdline") : text));
        };
        objs_[a.at(0)].cfg = std::move(c);
    }
    else if (op == "cfg.props") {
        ConfigSettings &c = *o(a.at(0)).cfg;
        put(L({S(c.powerRegulator()), B(c.noPwm()), B(c.ledStagger()), B(c.servicesQuiet()), B(c.wifiOn()),
               F(c.ledDim()), S(c.logLevel()), I(c.nebioScanHz()), I(c.nebioDigitalHz()), I(c.nebioAdcHz()),
               B(c.nebioFastGpio()), I(c.csoundRtPriority()), B(c.gateInterrupts()), F(c.gateHoldoffMs())}));
    }
    else if (op == "cfg.needsRestart") { put(B(o(a.at(0)).cfg->powerNeedsRestart())); }
    else if (op == "cfg.checked" || op == "cfg.writeRequest") {
        std::map<std::string, std::string> kv;
        for (auto &item : a) {
            size_t eq = item.find('=');
            kv[item.substr(0, eq)] = eq == std::string::npos ? "" : item.substr(eq + 1);
        }
        auto r = op == "cfg.checked" ? config::checkedRequest(kv) : config::writeRequest(kv);
        std::vector<Value> items;
        for (auto &x : r) items.push_back(L({S(x.first), x.second}));
        put(L(items));
    }
    else if (op == "cfg.takeRequest") {
        std::vector<Value> items;
        for (auto &x : config::takeRequest()) items.push_back(L({S(x.first), x.second}));
        put(L(items));
    }
    else if (op == "cfg.holdoff") {
        auto h = config::holdoff(val(a.at(0)));
        put(h ? F(*h) : Value());
    }
    else if (op == "cfg.rate") { put(I(config::rate(val(a.at(0)), toInt(val(a.at(1)))))); }
    else if (op == "cfg.syncCmdline") { o(a.at(0)).cfg->syncCmdline(); }
    else if (op == "cfg.setNebioRates") {
        std::vector<Value> v;
        for (size_t k = 1; k < a.size(); ++k) v.push_back(val(a[k]));
        while (v.size() < 3) v.push_back(Value());
        auto [s, d, ad] = o(a.at(0)).cfg->setNebioRates(v[0], v[1], v[2]);
        put(L({I(s), I(d), I(ad)}));
    }
    // --- classlogger.py -----------------------------------------------------------
    else if (op == "log.priority") { put(I(journalPriority(ival(a.at(0))))); }
    else if (op == "log.format") {
        need(5);
        std::string msg = a[3];
        for (auto &c : msg)
            if (c == '|') c = '\n';
        put(S(journalFormat(ival(a[0]), a[1], ival(a[2]), msg, a[4] == "1")));
    }
    // --- nconfig.py ---------------------------------------------------------------
    else if (op == "ini.new") { objs_[a.at(0)].ini = std::make_unique<NConfig>(); }
    else if (op == "ini.get") { put(o(a.at(0)).ini->getValue(a.at(1), a.at(2), val(a.at(3)))); }
    // --- nebconfig.py -------------------------------------------------------------
    else if (op == "nc.new") { objs_[a.at(0)].nc = std::make_unique<NebConfig>(NebConfig::readFile(path(a.at(1)))); }
    else if (op == "nc.entries") {
        std::vector<Value> l;
        OrderedDict d = o(a.at(0)).nc->asDict();
        for (auto &kv : d.items()) l.push_back(L({S(kv.first), kv.second}));
        put(L(l));
    }
    else if (op == "nc.pages") {
        auto [pages, errors] = o(a.at(0)).nc->encoderPages();
        put(pageSpecs(pages));
        put(strs(errors));
    }
    else if (op == "nc.holds") {
        auto [holds, errors] = o(a.at(0)).nc->holdPages();
        std::vector<Value> l;
        for (auto &[layer, encs] : holds) l.push_back(L({S(layer), pageSpecs(encs)}));
        put(L(l));
        put(strs(errors));
    }
    else if (op == "nc.cv") {
        std::vector<Value> l;
        for (auto &[e, t] : o(a.at(0)).nc->cvTargets()) l.push_back(L({S(e), t ? S(*t) : Value()}));
        put(L(l));
    }
    else if (op == "nc.osc") {
        auto [bindings, errors] = o(a.at(0)).nc->oscBindings();
        std::vector<Value> l;
        for (auto &b : bindings) l.push_back(L({S(b.control), S(b.path), F(b.lo), F(b.hi), S(b.curve)}));
        put(L(l));
        put(strs(errors));
    }
    else if (op == "nc.entry") {
        auto *e = o(a.at(0)).nc->entry(a.at(1));
        put(e ? strs(*e) : Value());
    }
    // --- controlhandler*.py ------------------------------------------------------
    else if (op == "h.new") {
        Obj &ob = objs_[a.at(0)];
        ob.h.reset();
        ob.ncDict.reset();
        if (a.at(5) != "None") ob.ncDict = std::make_unique<OrderedDict>(o(a[5]).nc->asDict());
        ob.hWriter = makeWriter();
        HandlerEnv env;
        env.settingsDir = dir_ + "/";
        env.writer = ob.hWriter.get();
        env.runWorker = [this](const std::function<void()> &work) {
            try {
                work();
            } catch (const PyError &e) {
                emit("thread E:" + e.type);
            } catch (const std::out_of_range &) {
                emit("thread E:IndexError");
            }
        };
        Csound *cs = cs_.get();
        try {
            if (a.at(1) == "prog") {
                // As nebulae.py's start_programs(): no configData, the port and bindings from the block.
                NebConfig &config = *o(a.at(5)).nc;
                int port;
                try {
                    port = config.oscPort();
                } catch (const PyError &) {
                    port = DEFAULT_OSC_PORT;
                }
                ob.h = std::make_unique<ProgControlHandler>(cs, val(a.at(2)), nullptr, a.at(3), a.at(4), port,
                                                            config.oscBindings().first, env);
            } else if (a.at(1) == "pd")
                ob.h = std::make_unique<PDControlHandler>(cs, val(a.at(2)), ob.ncDict.get(), a.at(3), a.at(4), env);
            else if (a.at(1) == "base")
                ob.h = std::make_unique<ControlHandler>(cs, val(a.at(2)), ob.ncDict.get(), a.at(3), a.at(4), env);
            else if (a.at(1) == "sc") {
                auto h = std::make_unique<SCControlHandler>(cs, val(a.at(2)), ob.ncDict.get(), a.at(3), a.at(4), env);
                h->udpTables = {path("proc_udp"), path("proc_udp6")};
                ob.h = std::move(h);
            }
            else
                throw PyError("KeyError", a[1]);
        } catch (...) {
            objs_.erase(a[0]);  // as Python, which never binds the name
            throw;
        }
    }
    else if (op == "h.setConfig") { enc(a.at(0)).setConfig(*o(a.at(1)).nc, path(a.at(2))); }
    else if (op == "h.state") {
        ControlHandler &h = *o(a.at(0)).h;
        std::vector<Value> flags;
        for (auto &[k, v] : h.editFunctionFlag) flags.push_back(L({S(k), B(v)}));
        put(L({S(h.control_mode), S(h.prev_control_mode), I(h.instr_sel_idx), B(h.prep_mode_change),
               h.static_file_idx, h.in_ticks, B(h.writing_buffer), B(h.buffer_failure), L(flags)}));
    }
    else if (op == "h.enc") {
        EncoderControlHandler &h = enc(a.at(0));
        std::vector<Value> blocked, since, sent, first, buttons;
        for (auto &b : h.hold_blocked) blocked.push_back(S(b));
        for (auto &[k, v] : h.hold_since) since.push_back(L({S(k), I(v)}));
        for (auto &[k, v] : h.page_sent) sent.push_back(L({S(k), F(v)}));
        for (auto &b : h.holdFirstButtons()) first.push_back(S(b));
        for (auto &b : h.holdButtons()) buttons.push_back(S(b));
        auto *scH = dynamic_cast<SCControlHandler *>(&h);
        put(L({h.hold_active ? S(*h.hold_active) : Value(), B(h.hold_used), L(blocked), L(since), B(h.cv_assign),
               L(sent), scH ? B(scH->rawReady) : Value(), L(first), L(buttons)}));
    }
    else if (op == "h.chans") {
        ControlHandler &h = *o(a.at(0)).h;
        std::vector<Value> c, alt;
        for (auto *chn : h.channels) c.push_back(L({S(chn->name), S(chn->source), chn->getValue()}));
        for (auto *chn : h.altchannels) alt.push_back(L({S(chn->name), chn->getValue()}));
        put(L(c));
        put(L(alt));
    }
    else if (op == "h.pages") {
        std::vector<Value> l;
        for (auto &[k, p] : enc(a.at(0)).allPages()) {
            std::vector<Value> values;
            for (auto *pg : p->pages) values.push_back(pg->value);
            Value hold = p->hold ? L({I((*p->hold)[0]), I((*p->hold)[1]), I((*p->hold)[2])}) : Value();
            l.push_back(L({S(k), I(static_cast<long long>(p->current)), p->cv_target ? S(*p->cv_target) : Value(),
                           p->candidate ? S(*p->candidate) : Value(), L(values), hold}));
        }
        put(L(l));
    }
    else if (op == "h.prog") {
        auto *h = dynamic_cast<ProgControlHandler *>(o(a.at(0)).h.get());
        if (!h) throw PyError("AttributeError", a[0]);
        std::vector<Value> sent, bindings;
        for (auto &[k, v] : h->prog_sent) sent.push_back(L({S(k), F(v)}));
        for (auto &[k, ts] : h->bindings) {
            std::vector<Value> l;
            for (auto &t : ts) l.push_back(L({S(t.path), F(t.lo), F(t.hi), S(t.curve)}));
            bindings.push_back(L({S(k), L(l)}));
        }
        put(L({I(h->oscPort), B(h->speed_leds), L(sent), L(bindings)}));
    }
    else if (op == "h.pd") {
        auto *h = dynamic_cast<PDControlHandler *>(o(a.at(0)).h.get());
        if (!h) throw PyError("AttributeError", a[0]);
        std::vector<Value> sent;
        for (auto &[k, v] : h->pd_sent) sent.push_back(L({S(k), v}));
        put(L({I(h->pd_resend_time), L(sent), B(h->pd_ready)}));
    }
    else if (op == "h.rawChannels") {
        std::vector<Value> l;
        for (auto *chn : sc(a.at(0)).rawChannels()) l.push_back(S(chn->name));
        put(L(l));
    }
    // --- any method of an object ----------------------------------------------------
    else {
        size_t dot = op.find('.');
        if (dot == std::string::npos) throw PyError("ValueError", "unknown op " + op);
        methodOp(op.substr(0, dot), op.substr(dot + 1), a);
    }
}

void Runner::nebioOp(const std::string &name, const std::vector<std::string> &a) {
    std::vector<Value> v;
    for (auto &x : a) v.push_back(val(x));
    auto arg = [&](size_t k) -> const Value & {
        if (k >= v.size()) throw PyError("TypeError", "missing argument");
        return v[k];
    };
    auto str = [&](size_t k) {
        if (arg(k).type != Value::Str) throw PyError("TypeError", "not a str");
        return arg(k).s;
    };
    auto tuple3 = [&](std::tuple<int, int, int> t) {
        return L({I(std::get<0>(t)), I(std::get<1>(t)), I(std::get<2>(t))});
    };
    if (name == "inputs") { nebio::inputs(); put(Value()); }
    else if (name == "snapshot") put(I(nebio::snapshot()));
    else if (name == "sr_bits") put(I(nebio::sr_bits()));
    else if (name == "gpio_level") put(I(nebio::gpio_level(static_cast<int>(toInt(arg(0))))));
    else if (name == "adc_code") put(I(nebio::adc_code(static_cast<int>(toInt(arg(0))), static_cast<int>(toInt(arg(1))))));
    else if (name == "adc_codes") {
        const int *c = nebio::adc_codes();
        std::vector<Value> l;
        for (int k = 0; k < 16; ++k) l.push_back(I(c[k]));
        put(L(l));
    }
    else if (name == "encoder_id") put(I(nebio::encoder_id(static_cast<int>(toInt(arg(0))), static_cast<int>(toInt(arg(1))))));
    else if (name == "encoder_steps") put(I(nebio::encoder_steps(static_cast<int>(toInt(arg(0))))));
    else if (name == "encoder_set_raw") { nebio::encoder_set_raw(str(0), arg(1).truthy()); put(Value()); }
    else if (name == "encoder_raw") put(B(nebio::encoder_raw(str(0))));
    else if (name == "encoder_set_click") { nebio::encoder_set_click(str(0), arg(1).truthy()); put(Value()); }
    else if (name == "set_eol") { nebio::set_eol(arg(0).truthy()); put(Value()); }
    else if (name == "set_input_rates") put(tuple3(nebio::set_input_rates(arg(0), arg(1), arg(2))));
    else if (name == "input_rates") put(tuple3(nebio::input_rates()));
    else if (name == "set_scan_jitter") { nebio::set_scan_jitter(toFloat(arg(0))); put(Value()); }
    else if (name == "set_scan_trigger") { nebio::set_scan_trigger(arg(0).truthy()); put(Value()); }
    else if (name == "scan_trigger") { nebio::scan_trigger(); put(Value()); }
    else if (name == "set_fast_gpio") put(B(nebio::set_fast_gpio(arg(0).truthy())));
    else if (name == "fast_gpio") put(B(nebio::fast_gpio()));
    else if (name == "set_gate_interrupts") put(B(nebio::set_gate_interrupts(arg(0).truthy(), arg(1).number())));
    else if (name == "stats") put(S(nebio::stats()));
    else if (name == "led_clear_sc") { nebio::led_clear_sc(); put(Value()); }
    else if (name == "sc_send_path_float") { nebio::sc_send_path_float(str(0), toFloat(arg(1))); put(Value()); }
    else if (name == "osc_open") put(B(nebio::osc_open(static_cast<int>(toInt(arg(0))))));
    else if (name == "osc_close") { nebio::osc_close(); put(Value()); }
    else if (name == "osc_send") { nebio::osc_send(str(0), toFloat(arg(1))); put(Value()); }
    else if (name == "card_clip_count") put(I(nebio::card_clip_count()));
    else if (name == "sc_forget_sent") { nebio::sc_forget_sent(); put(Value()); }
    else if (name == "sc_send") { nebio::sc_send(str(0), arg(1)); put(Value()); }
    else if (name == "last_error") put(S(nebio::last_error()));
    else throw PyError("AttributeError", name);
}

void Runner::methodOp(const std::string &prefix, const std::string &m, const std::vector<std::string> &a) {
    std::vector<Value> v;
    for (size_t k = 1; k < a.size(); ++k) v.push_back(val(a[k]));
    auto arg = [&](size_t k) -> const Value & {
        if (k >= v.size()) throw PyError("TypeError", "missing argument");
        return v[k];
    };
    auto str = [&](size_t k) {
        if (arg(k).type != Value::Str) throw PyError("TypeError", "not a str");
        return arg(k).s;
    };
    auto none = [&] { put(Value()); };
    Obj &ob = o(a.at(0));
    if (prefix == "sw") {
        Switch &s = *ob.sw;
        if (m == "update") { s.update(); none(); }
        else if (m == "q") put(L({B(s.risingEdge()), B(s.fallingEdge()), B(s.state()), B(s.prevState())}));
        else throw PyError("AttributeError", m);
    } else if (prefix == "sr") {
        ShiftRegister &s = *ob.sr;
        if (m == "update") { s.update(); none(); }
        else if (m == "q") {
            int i = ival(a.at(1));
            put(L({B(s.risingEdge(i)), B(s.fallingEdge(i)), B(s.state(i)), B(s.prevState(i))}));
        } else throw PyError("AttributeError", m);
    } else if (prefix == "mcp") {
        if (m == "read") put(I(ob.mcp->read_adc(ival(a.at(1)))));
        else throw PyError("AttributeError", m);
    } else if (prefix == "adc") {
        AdcData &d = data<AdcData>(a[0]);
        if (m == "getValue") put(d.getValue());
        else if (m == "getCV") put(d.getCV());
        else if (m == "getPot") put(d.getPot());
        else if (m == "setIgnoreHID") { d.setIgnoreHID(arg(0).truthy()); none(); }
        else if (m == "setResistVal") { d.setResistVal(arg(0)); none(); }
        else if (m == "clearResistVal") { d.clearResistVal(); none(); }
        else if (m == "isResisting") put(B(d.isResisting()));
        else if (m == "getRawPotValue") put(d.getRawPotValue());
        else if (m == "getRawCVValue") put(d.getRawCVValue());
        else if (m == "getPotValue") put(d.getPotValue());
        else if (m == "getCVValue") put(d.getCVValue());
        else if (m == "clipControl") put(d.clipControl(arg(0)));
        else if (m == "setCVOffset") { d.setCVOffset(toFloat(arg(0))); none(); }
        else if (m == "setValue") { d.setValue(arg(0)); none(); }
        else if (m == "convertRawCV") put(F(AdcData::convertRawCV(arg(0).number())));
        else throw PyError("AttributeError", m);
    } else if (prefix == "hyb") {
        HybridData &d = data<HybridData>(a[0]);
        if (m == "getValue") put(d.getValue());
        else if (m == "setCVOffset") { d.setCVOffset(toFloat(arg(0))); none(); }
        else if (m == "setIgnoreHID") { d.setIgnoreHID(arg(0).truthy()); none(); }
        else if (m == "setValue") { d.setValue(arg(0)); none(); }
        else if (m == "getStaticVal") put(d.getStaticVal());
        else if (m == "getRawCVValue") put(d.getRawCVValue());
        else if (m == "getCVValue") put(d.getCVValue());
        else throw PyError("AttributeError", m);
    } else if (prefix == "st") {
        StaticData &d = data<StaticData>(a[0]);
        if (m == "getValue") put(d.getValue());
        else if (m == "setValue") { d.setValue(arg(0)); none(); }
        else throw PyError("AttributeError", m);
    } else if (prefix == "raw") {
        RawEncoderData &d = data<RawEncoderData>(a[0]);
        if (m == "setActive") { d.setActive(arg(0).truthy()); none(); }
        else if (m == "getValue") put(d.getValue());
        else if (m == "setValue") { d.setValue(arg(0)); none(); }
        else if (m == "setIgnoreHID") { d.setIgnoreHID(arg(0).truthy()); none(); }
        else throw PyError("AttributeError", m);
    } else if (prefix == "comm") {
        CommChannel &c = *ob.comm;
        if (m == "update") { c.update(); none(); }
        else if (m == "getState") put(c.getState());
        else if (m == "risingEdge") put(B(c.risingEdge()));
        else if (m == "fallingEdge") put(B(c.fallingEdge()));
        else if (m == "clearState") { c.clearState(); none(); }
        else if (m == "flag") put(B(c.rising_edge_flag));
        else throw PyError("AttributeError", m);
    } else if (prefix == "ctl") {
        ControlChannel &c = *ob.ctl;
        if (m == "setValue") { c.setValue(arg(0)); none(); }
        else if (m == "getValue") put(c.getValue());
        else if (m == "getPrevValue") put(c.getPrevValue());
        else if (m == "getPotValue") put(c.getPotValue());
        else if (m == "getRawCVValue") put(c.getRawCVValue());
        else if (m == "getCVValue") put(c.getCVValue());
        else if (m == "getStaticVal") put(c.getStaticVal());
        else if (m == "setCVOffset") { c.setCVOffset(toFloat(arg(0))); none(); }
        else if (m == "setIgnoreNextButton") { c.setIgnoreNextButton(); none(); }
        else if (m == "setOutputPeriod") { c.setOutputPeriod(arg(0)); none(); }
        else if (m == "setMode") { c.setMode(str(0), str(1)); none(); }
        else if (m == "setModeChangeValue") { c.setModeChangeValue(arg(0)); none(); }
        else if (m == "clearResistVal") { c.clearResistVal(); none(); }
        else if (m == "isResisting") put(B(c.isResisting()));
        else if (m == "hasChanged") put(B(c.hasChanged()));
        else if (m == "setIgnoreHID") { c.setIgnoreHID(arg(0).truthy()); none(); }
        else if (m == "setIgnoreGate") { c.setIgnoreGate(arg(0).truthy()); none(); }
        else if (m == "getTrigSource") put(S(c.getTrigSource()));
        else if (m == "muteCSound") { c.muteCSound(arg(0).truthy()); none(); }
        else if (m == "isCSoundMuted") put(B(c.isCSoundMuted()));
        else if (m == "getLEDValue") put(c.getLEDValue());
        else if (m == "update") { c.update(); none(); }
        else if (m == "gatherOffset") put(F(c.gatherOffset(str(0))));
        else throw PyError("AttributeError", m);
    } else if (prefix == "dd") {
        DigitalData &d = data<DigitalData>(a[0]);
        if (m == "getValue") put(d.getValue());
        else if (m == "getLEDValue") put(d.getLEDValue());
        else if (m == "setIgnoreHID") { d.setIgnoreHID(arg(0).truthy()); none(); }
        else if (m == "setIgnoreGate") { d.setIgnoreGate(arg(0).truthy()); none(); }
        else if (m == "setValue") { d.setValue(arg(0)); none(); }
        else if (m == "setIncOrder") { d.setIncOrder(static_cast<int>(toInt(arg(0)))); none(); }
        else if (m == "setIgnoreNextButton") { d.setIgnoreNextButton(); none(); }
        else if (m == "setOutputPeriod") { d.setOutputPeriod(arg(0)); none(); }
        else if (m == "setMode") { d.setMode(str(0), str(1)); none(); }
        else if (m == "getTrigSource") put(S(d.getTrigSource()));
        else if (m == "getAction") put(I(d.getAction(static_cast<int>(toInt(arg(0))), static_cast<int>(toInt(arg(1))), str(2))));
        else if (m == "updateLongPress") { d.updateLongPress(static_cast<int>(toInt(arg(0)))); none(); }
        else if (m == "getRawValues") {
            auto [s, p] = d.getRawValues(str(0), v.size() > 1 && arg(1).truthy());
            put(L({I(s), I(p)}));
        }
        else if (m == "handle_button") { d.handle_button(); none(); }
        else if (m == "handle_gate") { d.handle_gate(); none(); }
        else if (m == "handle_incremental_value") { d.handle_incremental_value(); none(); }
        else throw PyError("AttributeError", m);
    } else if (prefix == "ep") {
        EncoderPages &p = *ob.ep;
        auto colour = [](const Colour &c) { return L({I(c[0]), I(c[1]), I(c[2])}); };
        if (m == "step") { p.step(arg(0)); none(); }
        else if (m == "move") { p.move(arg(0)); none(); }
        else if (m == "nextPage") { p.nextPage(); none(); }
        else if (m == "startChoosing") { p.startChoosing(); none(); }
        else if (m == "setCandidate") { p.setCandidate(arg(0).truthy()); none(); }
        else if (m == "candidateShown") put(B(p.candidateShown()));
        else if (m == "commitCandidate") put(B(p.commitCandidate()));
        else if (m == "colour") put(colour(p.colour(toInt(arg(0)))));
        else if (m == "marked") put(p.marked(toInt(arg(0))));
        else if (m == "names") {
            std::vector<Value> n;
            for (auto &x : p.names()) n.push_back(S(x));
            put(L(n));
        }
        else throw PyError("AttributeError", m);
    } else if (prefix == "set") {
        SettingManager &s = *ob.set;
        if (m == "read") { s.read(); none(); }
        else if (m == "write") { s.write(); none(); }
        else if (m == "update") { s.update(arg(0)); none(); }
        else if (m == "getDefault") put(s.getDefault(str(0)));
        else if (m == "load") put(s.load(str(0)));
        else if (m == "hasSetting") put(B(s.hasSetting(str(0))));
        else if (m == "save") { s.save(str(0), arg(1)); none(); }
        else if (m == "getLastUpdate") put(s.getLastUpdate());
        else if (m == "printSettings") none();
        else throw PyError("AttributeError", m);
    } else if (prefix == "pd") {
        PdSend &p = *ob.pd;
        if (m == "connect") { p.connect(); none(); }
        else if (m == "format") put(S(p.format(str(0), arg(1))));
        else if (m == "close") { p.close(); none(); }
        else if (m == "is_connected") put(B(p.is_connected()));
        else throw PyError("AttributeError", m);
    } else if (prefix == "sc") {
        ScSend &s = *ob.sc;
        if (m == "synthIsUpStatus") put(B(s.synthIsUpStatus()));
        else if (m == "setSynthIsDown") { s.setSynthIsDown(); none(); }
        else if (m == "pingLoaded") { s.pingLoaded(); none(); }
        else if (m == "sclangHandshakeStatus") put(B(s.sclangHandshakeStatus()));
        else if (m == "zeroSclangHandshake") { s.zeroSclangHandshake(); none(); }
        else if (m == "connectSender") { s.connectSender(); none(); }
        else if (m == "clear") { s.clear(); none(); }
        else if (m == "send") { s.send(str(0), arg(1)); none(); }
        else if (m == "startListener") put(B(s.startListener()));
        else if (m == "addResiver") { s.addResiver(str(0)); none(); }
        else if (m == "close") { s.close(); none(); }
        else if (m == "is_connected") put(B(s.is_connected()));
        else if (m == "close_client") { s.close_client(); none(); }
        else if (m == "close_server") { s.close_server(); none(); }
        else throw PyError("AttributeError", m);
    } else if (prefix == "cfg") {
        ConfigSettings &c = *ob.cfg;
        if (m == "load") { c.load(); none(); }
        else if (m == "applyAtStart") { c.applyAtStart(); none(); }
        else if (m == "setPowerRegulator") put(B(c.setPowerRegulator(str(0))));
        else if (m == "setNoPwm") { c.setNoPwm(arg(0).truthy()); none(); }
        else if (m == "setLedStagger") { c.setLedStagger(arg(0).truthy()); none(); }
        else if (m == "setServicesQuiet") { c.setServicesQuiet(arg(0).truthy()); none(); }
        else if (m == "setWifiOn") { c.setWifiOn(arg(0).truthy()); none(); }
        else if (m == "setLedDim") { c.setLedDim(arg(0)); none(); }
        else if (m == "setNebioFastGpio") { c.setNebioFastGpio(arg(0).truthy()); none(); }
        else if (m == "setGateInterrupts") { c.setGateInterrupts(arg(0).truthy()); none(); }
        else if (m == "setGateHoldoffMs") { c.setGateHoldoffMs(arg(0)); none(); }
        else if (m == "waitUntilApplied") { c.waitUntilApplied(); none(); }
        else throw PyError("AttributeError", m);
    } else if (prefix == "h") {
        handlerMethod(*ob.h, m, v);
    } else if (prefix == "nc") {
        NebConfig &c = *ob.nc;
        if (m == "encoderType") put(S(c.encoderType(str(0))));
        else if (m == "outputPeriod") put(F(c.outputPeriod()));
        else if (m == "oscPort") put(I(c.oscPort()));
        else if (m == "speedLeds") put(c.speedLeds() ? S(*c.speedLeds()) : Value());
        else if (m == "value") put(c.value(str(0)) ? S(*c.value(str(0))) : Value());
        else throw PyError("AttributeError", m);
    } else {
        throw PyError("ValueError", "unknown op " + prefix + "." + m);
    }
}

void Runner::handlerMethod(ControlHandler &h, const std::string &m, const std::vector<Value> &v) {
    auto arg = [&](size_t k) -> const Value & {
        if (k >= v.size()) throw PyError("TypeError", "missing argument");
        return v[k];
    };
    auto str = [&](size_t k) {
        if (arg(k).type != Value::Str) throw PyError("TypeError", "not a str");
        return arg(k).s;
    };
    auto none = [&] { put(Value()); };
    auto *e = dynamic_cast<EncoderControlHandler *>(&h);
    auto *s = dynamic_cast<SCControlHandler *>(&h);
    auto needE = [&]() -> EncoderControlHandler & {
        if (!e) throw PyError("AttributeError", m);
        return *e;
    };
    auto needS = [&]() -> SCControlHandler & {
        if (!s) throw PyError("AttributeError", m);
        return *s;
    };
    if (m == "updateAll") { h.updateAll(); none(); }
    else if (m == "enterNormalMode") { h.enterNormalMode(); none(); }
    else if (m == "enterSecondaryMode") { h.enterSecondaryMode(); none(); }
    else if (m == "enterInstrSelMode") { h.enterInstrSelMode(); none(); }
    else if (m == "saveInstrument") { h.saveInstrument(); none(); }
    else if (m == "closeSockets") { h.closeSockets(); none(); }
    else if (m == "setValue") { h.setValue(str(0), arg(1)); none(); }
    else if (m == "setAltValue") { h.setAltValue(str(0), arg(1)); none(); }
    else if (m == "getValue") put(h.getValue(str(0)));
    else if (m == "getAltValue") put(h.getAltValue(str(0)));
    else if (m == "getLEDValue") put(h.getLEDValue(str(0)));
    else if (m == "getAltLEDValue") put(h.getAltLEDValue(str(0)));
    else if (m == "getStaticVal") put(h.getStaticVal(str(0)));
    else if (m == "getAltStaticVal") put(h.getAltStaticVal(str(0)));
    else if (m == "getInstrValue") put(h.getInstrValue(str(0)));
    else if (m == "getInstrSelIdx") put(I(h.getInstrSelIdx()));
    else if (m == "setInstrSelOffset") { h.setInstrSelOffset(toInt(arg(0))); none(); }
    else if (m == "setInstrSelNumFiles") { h.setInstrSelNumFiles(toInt(arg(0))); none(); }
    else if (m == "setCurrentInstr") { h.setCurrentInstr(str(0)); none(); }
    else if (m == "mode") put(S(h.mode()));
    else if (m == "isRaw") put(B(h.isRaw(str(0))));
    else if (m == "inputClipCount") put(I(h.inputClipCount()));
    else if (m == "restoreAltToDefault") { h.restoreAltToDefault(); none(); }
    else if (m == "resistNormalSettings") { h.resistNormalSettings(); none(); }
    else if (m == "resistSecondarySettings") { h.resistSecondarySettings(); none(); }
    else if (m == "handleEndOfLoop") { h.handleEndOfLoop(); none(); }
    else if (m == "handleRecordStatus") { h.handleRecordStatus(); none(); }
    else if (m == "getEditFunctionFlag") put(B(h.getEditFunctionFlag(str(0))));
    else if (m == "clearEditFunctionFlag") { h.clearEditFunctionFlag(str(0)); none(); }
    else if (m == "setEditFunctionFlag") { h.setEditFunctionFlag(str(0)); none(); }
    else if (m == "updateChannel") { h.updateChannel(str(0)); none(); }
    else if (m == "updateAltChannel") { h.updateAltChannel(str(0)); none(); }
    else if (m == "setInputLevel") { h.setInputLevel(arg(0)); none(); }
    else if (m == "writeBufferToAudioFile") { h.writeBufferToAudioFile(); none(); }
    else if (m == "printAllControls") { h.printAllControls(); none(); }
    else if (m == "printAllControlsVerbose") { h.printAllControlsVerbose(); none(); }
    else if (m == "getEndOfLoopState") put(B(h.getEndOfLoopState()));
    // controlhandlerEncoders
    else if (m == "pageStep") { needE().pageStep(str(0), arg(1)); none(); }
    else if (m == "pageJump") { needE().pageJump(str(0), arg(1)); none(); }
    else if (m == "nextPage") { needE().nextPage(str(0)); none(); }
    else if (m == "setCvOn") { needE().setCvOn(str(0), arg(1).truthy()); none(); }
    else if (m == "cvAssignActive") put(B(needE().cvAssignActive()));
    else if (m == "sendPages") { needE().sendPages(v.empty() ? false : arg(0).truthy()); none(); }
    else if (m == "savePages") { needE().savePages(); none(); }
    else if (m == "buttonBlocked") put(B(needE().buttonBlocked(str(0))));
    else if (m == "sendsControl") put(B(needE().sendsControl(str(0))));
    else if (m == "encoderCV") put(needE().encoderCV(str(0)));
    else if (m == "updateHolds") { needE().updateHolds(); none(); }
    else if (m == "updateCvAssign") { needE().updateCvAssign(); none(); }
    // controlhandlerProg
    else if (m == "playbackSpeed" || m == "enterProgramsMode") {
        auto *p = dynamic_cast<ProgControlHandler *>(&h);
        if (!p) throw PyError("AttributeError", m);
        if (m == "enterProgramsMode") { p->enterProgramsMode(); none(); }
        else put(p->playbackSpeed() ? F(*p->playbackSpeed()) : Value());
    }
    // controlhandlerPD
    else if (m == "enterPureDataMode") {
        auto *p = dynamic_cast<PDControlHandler *>(&h);
        if (!p) throw PyError("AttributeError", m);
        p->enterPureDataMode();
        none();
    }
    // controlhandlerSC
    else if (m == "startRawEncoders") { needS().startRawEncoders(); none(); }
    else if (m == "setRawActive") { needS().setRawActive(arg(0).truthy()); none(); }
    else if (m == "enterSuperColliderMode") { needS().enterSuperColliderMode(); none(); }
    else if (m == "startScOscServer") { needS().startScOscServer(); none(); }
    else if (m == "waitOnScLang") { needS().waitOnScLang(); none(); }
    else if (m == "synthIsUpStatus") { needS().synthIsUpStatus(); none(); }
    else if (m == "waitForSclangPort") put(B(v.empty() ? needS().waitForSclangPort() : needS().waitForSclangPort(arg(0).number())));
    else if (m == "loadScSynth") { needS().loadScSynth(arg(0)); none(); }
    else if (m == "closeScSynthProcess") { needS().closeScSynthProcess(); none(); }
    else if (m == "sendScOscMessages") { needS().sendScOscMessages(); none(); }
    else throw PyError("AttributeError", m);
}

}  // namespace

// runner <scenario> [--expect <trace>]: prints the trace, or with --expect
// compares it with the expected one (CTest) and exits 1 on a difference.
int main(int argc, char **argv) {
    if (argc != 2 && !(argc == 4 && std::string(argv[2]) == "--expect")) {
        std::fprintf(stderr, "usage: runner <scenario> [--expect <trace>]\n");
        return 2;
    }
    Logger::setRootLevel(CRITICAL);
    std::ifstream f(argv[1]);
    std::vector<std::string> lines;
    std::string l;
    while (std::getline(f, l)) lines.push_back(l);
    char tmpl[] = "/tmp/nebport_cpp_XXXXXX";
    std::string dir = ::mkdtemp(tmpl);
    setNebioC(&clib);
    setClock(&fakeClock);
    setRandom(&fakeRandom);
    std::vector<std::string> out;
    {
        Runner r(dir);
        out = r.run(lines);
    }
    ::chdir("/");
    std::system(("rm -rf '" + dir + "'").c_str());
    if (argc == 4) {
        std::ifstream e(argv[3]);
        std::vector<std::string> want;
        while (std::getline(e, l)) want.push_back(l);
        for (size_t k = 0; k < std::max(want.size(), out.size()); ++k) {
            std::string w = k < want.size() ? want[k] : "<end>", g = k < out.size() ? out[k] : "<end>";
            if (w != g) {
                std::printf("trace line %zu differs\n  expected: %s\n  got:      %s\n", k + 1, w.c_str(), g.c_str());
                return 1;
            }
        }
        std::printf("%zu trace lines as expected\n", out.size());
        return 0;
    }
    for (auto &x : out) std::cout << x << "\n";
    return 0;
}
