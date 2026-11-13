// fatal.py: a text file that is not UTF-8 stops Nebulae. Red LEDs
// (nebulae_leds.sh), a report on the stick, an instrument's files taken out
// (deleted on the Pi, renamed .bad on the stick), exit code 3. Only with
// enabled; otherwise PyError BadTextFile.
#pragma once

#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace neb {
namespace fatal {

extern bool enabled;
extern int EXIT_CODE;
extern std::string MARKER;
extern std::string STICK;   // ends with "/"
extern std::string REPORT;
extern std::string SCRIPTS;
extern int JOURNAL_LINES;

// nebconfig.INSTR_DIRS, in its order.
struct InstrDir {
    std::string bank, folder, ext;  // folder ends with "/"
};
extern std::vector<InstrDir> INSTR_DIRS;

// What the tests replace (fatal.py's _log, _now, _stopNebio, _stickMounted,
// _run, _exit). exit must not return.
struct Backend {
    std::function<void(const std::string &)> log;
    std::function<std::string()> now;
    std::function<void()> stopNebio;
    std::function<bool()> stickMounted;
    std::function<std::string(const std::vector<std::string> &)> run;
    std::function<void(int)> exit;
};
Backend &backend();

[[noreturn]] void badFile(const std::string &path, size_t pos);

// (bank, name) when path is an instrument's file on the Pi or the stick.
std::optional<std::pair<std::string, std::string>> instrumentOf(const std::string &path);

}  // namespace fatal
}  // namespace neb
