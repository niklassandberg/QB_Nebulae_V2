// ConfigSettings under threads, as tests/py/test_threads.py does with the
// original: the job thread's syncCmdline beside setPowerRegulator, NebFile's
// threads writing requests, Nebulae taking them, setters beside getters.
// Build with -fsanitize=thread as well: the getters must not race the setters.
#include <unistd.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "classlogger.h"
#include "configsettings.h"

using namespace neb;

namespace {

int ROUNDS = 400;
int failures = 0;
std::string dir;
std::mutex errorsMutex;
std::vector<std::string> errors;

void error(const std::string &e) {
    std::lock_guard<std::mutex> lock(errorsMutex);
    errors.push_back(e);
}

void check(bool ok, const std::string &what) {
    if (ok) return;
    std::printf("FAIL %s\n", what.c_str());
    ++failures;
}

void checkNoErrors(const std::string &test) {
    std::lock_guard<std::mutex> lock(errorsMutex);
    if (!errors.empty()) {
        std::printf("FAIL %s: %zu errors, first: %s\n", test.c_str(), errors.size(), errors[0].c_str());
        ++failures;
    }
    errors.clear();
}

void runThreads(const std::vector<std::function<void()>> &targets) {
    std::vector<std::thread> threads;
    for (auto &t : targets) threads.emplace_back(t);
    for (auto &t : threads) t.join();
}

std::string readFile(const std::string &path) {
    std::ifstream f(path);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

void writeFile(const std::string &path, const std::string &text) { std::ofstream(path) << text; }

const std::string CMDLINE = "console=tty1 root=/dev/mmcblk0p2 rw rootwait";

void cmdlineJobAndPanel() {
    writeFile(config::CMDLINE, CMDLINE + "\n");
    ConfigSettings c;
    c.runInBackgroundHook = [](const ConfigJob &) {};  // the scripts
    runThreads({
        [&] {
            for (int i = 0; i < ROUNDS; ++i) try {
                    c.syncCmdline();  // the job thread's applyAtStart job
                } catch (const std::exception &e) {
                    error(std::string("syncCmdline: ") + e.what());
                }
        },
        [&] {
            for (int i = 0; i < ROUNDS; ++i) try {
                    c.setPowerRegulator(i % 2 == 0 ? "nohlt" : "off");
                } catch (const std::exception &e) {
                    error(std::string("setPowerRegulator: ") + e.what());
                }
        },
    });
    std::istringstream words(readFile(config::CMDLINE));
    std::string w, rest;
    while (words >> w) rest += (rest.empty() ? "" : " ") + w;
    check(rest == CMDLINE, "cmdline is \"" + rest + "\"");
    check(::access((config::CMDLINE + ".new").c_str(), F_OK) != 0, "cmdline.txt.new left");
    checkNoErrors("cmdline job and panel");
}

void webRequestsOverlap() {
    std::vector<std::function<void()>> pages;
    for (int n = 1; n <= 6; ++n)
        pages.push_back([n] {
            for (int i = 0; i < ROUNDS; ++i) try {
                    config::writeRequest({{"led_dim", "0." + std::to_string(n)},
                                          {"gate_holdoff_ms", std::to_string(i % 50)}});
                } catch (const std::exception &e) {
                    error(std::string("writeRequest: ") + e.what());
                }
        });
    runThreads(pages);
    checkNoErrors("web requests overlap");
    check(config::takeRequest().size() == 2, "the request after overlapping saves");
}

void requestTakenWhileWritten() {
    int lost = 0, trials = ROUNDS / 4;
    for (int trial = 0; trial < trials; ++trial) {
        std::vector<double> taken;
        std::atomic<bool> done{false};
        double last = trial % 90 + 0.5;
        auto take = [&] {
            auto r = config::takeRequest();
            if (r.count("gate_holdoff_ms")) taken.push_back(r["gate_holdoff_ms"].f);
        };
        runThreads({
            [&] {
                for (int v = 0; v < 30; ++v) config::writeRequest({{"gate_holdoff_ms", std::to_string(v) + ".1"}});
                config::writeRequest({{"gate_holdoff_ms", std::to_string(last)}});
                done = true;
            },
            [&] {
                while (!done) take();
                take();
            },
        });
        if (taken.empty() || taken.back() != last) ++lost;
    }
    check(lost == 0, "the last save was lost in " + std::to_string(lost) + " of " + std::to_string(trials) + " trials");
}

void settingsFileAlwaysWhole() {
    ConfigSettings c;
    c.runInBackgroundHook = [](const ConfigJob &) {};
    std::atomic<bool> stop{false};
    std::atomic<int> bad{0};
    std::thread reader([&] {
        while (!stop) {
            std::string text = readFile(config::CONFIG_FILE);
            int keys = 0;
            for (char ch : text) keys += ch == '=';
            if (keys && keys != 14) ++bad;
            // the getters beside the setters (ThreadSanitizer)
            if (c.ledDim() < 0 || c.gateHoldoffMs() < 0 || c.powerRegulator().empty() || c.logLevel().empty())
                ++bad;
        }
    });
    runThreads({
        [&] {
            for (int i = 0; i < ROUNDS; ++i) {
                c.setLedDim(Value::real(i % 100 / 100.0));
                c.setNoPwm(i % 2 == 0);
            }
        },
        [&] {
            for (int i = 0; i < ROUNDS; ++i) {
                c.setGateHoldoffMs(Value::integer(i % 100));
                c.setNebioRates(Value::integer(1000 + i % 500));
            }
        },
    });
    stop = true;
    reader.join();
    check(bad == 0, std::to_string(bad.load()) + " torn reads of the settings");
    checkNoErrors("settings file always whole");
}

}  // namespace

int main() {
    if (const char *r = std::getenv("NEB_THREAD_ROUNDS")) ROUNDS = std::atoi(r);
    Logger::setRootLevel(CRITICAL);
    char tmpl[] = "/tmp/nebport_threads_XXXXXX";
    dir = ::mkdtemp(tmpl);
    config::CONFIG_FILE = dir + "/configsettings.txt";
    config::REQUEST_FILE = dir + "/config_request";
    config::CMDLINE = dir + "/cmdline.txt";
    config::kernelHasNohlt = [] { return false; };

    cmdlineJobAndPanel();
    webRequestsOverlap();
    requestTakenWhileWritten();
    settingsFileAlwaysWhole();

    std::system(("rm -rf '" + dir + "'").c_str());
    std::printf("%s (%d failures)\n", failures ? "FAILED" : "all thread tests passed", failures);
    return failures ? 1 : 0;
}
