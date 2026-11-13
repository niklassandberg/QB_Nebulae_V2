#include "fatal.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>

#include "nebio_api.h"
#include "pyvalue.h"
#include "settings.h"

namespace neb {
namespace fatal {

bool enabled = false;
int EXIT_CODE = 3;
std::string MARKER = "/run/nebulae-fatal";
std::string STICK = "/mnt/memory/";
std::string REPORT = "neb_error.txt";
std::string SCRIPTS = "/home/alarm/QB_Nebulae_V2/Code/scripts/";
int JOURNAL_LINES = 50;

std::vector<InstrDir> INSTR_DIRS = {
    {"instr", "/home/alarm/instr/", ".instr"},
    {"supercollider", "/home/alarm/sc/", ".scd"},
    {"puredata", "/home/alarm/pd/", ".pd"},
    {"programs", "/home/alarm/prog/", ".prog"},
};

namespace {
const std::vector<std::string> STATE_EXTS = {".pages", ".state"};

bool isFile(const std::string &path) {
    struct stat st;
    return ::stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode);
}

// os.path.abspath
std::string absPath(const std::string &path) {
    std::string full = path;
    if (full.empty() || full[0] != '/') {
        char cwd[4096];
        full = std::string(::getcwd(cwd, sizeof cwd) ? cwd : "") + "/" + path;
    }
    std::vector<std::string> parts;
    size_t start = 0;
    while (start <= full.size()) {
        size_t slash = full.find('/', start);
        std::string part = full.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
        if (part == "..") {
            if (!parts.empty()) parts.pop_back();
        } else if (!part.empty() && part != ".") {
            parts.push_back(part);
        }
        if (slash == std::string::npos) break;
        start = slash + 1;
    }
    std::string out;
    for (auto &p : parts) out += "/" + p;
    return out.empty() ? "/" : out;
}

std::string dirName(const std::string &path) {
    size_t slash = path.rfind('/');
    if (slash == 0) return "/";
    return slash == std::string::npos ? "" : path.substr(0, slash);
}

std::string baseName(const std::string &path) {
    size_t slash = path.rfind('/');
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

// os.path.splitext of a base name: leading dots are not an extension.
std::pair<std::string, std::string> splitExt(const std::string &name) {
    size_t lead = 0;
    while (lead < name.size() && name[lead] == '.') ++lead;
    size_t dot = name.rfind('.');
    if (dot == std::string::npos || dot < lead) return {name, ""};
    return {name.substr(0, dot), name.substr(dot)};
}

bool isStateExt(const std::string &ext) {
    for (auto &e : STATE_EXTS)
        if (ext == e) return true;
    return false;
}

// str() of Python's OSError for a file.
std::string osErrorText(int err, const std::string &path) {
    return "[Errno " + std::to_string(err) + "] " + std::strerror(err) + ": '" + path + "'";
}

void log(const std::string &line) { backend().log(line); }

void touch(const std::string &path) {
    int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) {
        log("Could not write " + path + ": " + osErrorText(errno, path));
        return;
    }
    ::close(fd);
}

std::vector<std::string> files(const std::string &folder, const std::string &name, const std::string &ext) {
    std::vector<std::string> out;
    std::vector<std::string> exts = {ext};
    exts.insert(exts.end(), STATE_EXTS.begin(), STATE_EXTS.end());
    for (auto &e : exts)
        if (isFile(folder + name + e)) out.push_back(folder + name + e);
    return out;
}

std::vector<std::string> takeOut(const std::pair<std::string, std::string> &instrument, bool mounted) {
    const std::string &bank = instrument.first, &name = instrument.second;
    const InstrDir *dir = nullptr;
    for (auto &d : INSTR_DIRS)
        if (d.bank == bank) dir = &d;
    std::vector<std::string> lines = {"Instrument " + name + " (" + bank + ") is taken out of Nebulae."};
    for (auto &f : files(dir->folder, name, dir->ext)) {
        if (std::remove(f.c_str()) == 0)
            lines.push_back("Deleted on Nebulae: " + f);
        else
            lines.push_back("Could not delete " + f + ": " + std::strerror(errno));
    }
    if (mounted) {
        for (auto &f : files(STICK, name, dir->ext)) {
            if (std::rename(f.c_str(), (f + ".bad").c_str()) == 0)
                lines.push_back("Renamed on the stick: " + baseName(f) + " -> " + baseName(f) + ".bad");
            else
                lines.push_back("Could not rename " + f + ": " + std::strerror(errno));
        }
    }
    lines.push_back("Save the file as UTF-8, give it its name back and load the instrument again.");
    return lines;
}

bool mountStick() {
    if (backend().stickMounted()) return true;
    backend().run({"bash", SCRIPTS + "usb_power.sh", "on"});
    std::string stick = STICK.substr(0, STICK.size() - 1);
    backend().run({"mount", "/dev/sda1", stick});
    return backend().stickMounted();
}

void writeReport(const std::vector<std::string> &report) {
    std::string text = backend().now() + "\n";
    for (size_t k = 0; k < report.size(); ++k) text += (k ? "\n" : "") + report[k];
    text += "\n\nLast log lines:\n";
    text += backend().run({"journalctl", "-u", "nebulae", "-n", std::to_string(JOURNAL_LINES), "--no-pager", "-o",
                           "short-iso"});
    std::string path = STICK + REPORT;
    int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) {
        log("Could not write " + path + ": " + osErrorText(errno, path));
        return;
    }
    bool ok = ::write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size());
    int err = errno;
    ::fsync(fd);
    ::close(fd);
    if (!ok) log("Could not write " + path + ": " + osErrorText(err, path));
}

std::string quote(const std::string &s) {
    std::string out = "'";
    for (char c : s) out += c == '\'' ? std::string("'\\''") : std::string(1, c);
    return out + "'";
}

Backend makeDefault() {
    Backend b;
    b.log = [](const std::string &line) {
        std::fprintf(stderr, "<2>CRITICAL [fatal.cpp]: %s\n", line.c_str());
        std::fflush(stderr);
    };
    b.now = [] {
        std::time_t t = std::time(nullptr);
        char buf[32];
        std::strftime(buf, sizeof buf, "%Y-%m-%d %H:%M:%S", std::localtime(&t));
        return std::string(buf);
    };
    b.stopNebio = [] {
        try {
            nebioC().shutdown();
        } catch (const PyError &) {
        }
    };
    b.stickMounted = [] {
        std::ifstream f("/proc/mounts");
        std::string dev, point, rest;
        std::string stick = STICK.substr(0, STICK.size() - 1);
        while (f >> dev >> point && std::getline(f, rest))
            if (point == stick) return true;
        return false;
    };
    b.run = [](const std::vector<std::string> &cmd) {
        std::string line = "timeout 10";
        for (auto &c : cmd) line += " " + quote(c);
        line += " 2>/dev/null";
        std::string out;
        if (std::FILE *p = ::popen(line.c_str(), "r")) {
            char buf[4096];
            size_t n;
            while ((n = std::fread(buf, 1, sizeof buf, p)) > 0) out.append(buf, n);
            ::pclose(p);
        }
        return out;
    };
    b.exit = [](int code) { std::_Exit(code); };
    return b;
}
}  // namespace

Backend &backend() {
    static Backend b = makeDefault();
    return b;
}

std::optional<std::pair<std::string, std::string>> instrumentOf(const std::string &path) {
    std::string abs = absPath(path);
    std::string folder = dirName(abs);
    folder += folder == "/" ? "" : "/";
    auto [name, ext] = splitExt(baseName(abs));
    for (auto &d : INSTR_DIRS) {
        if (folder == d.folder && (ext == d.ext || isStateExt(ext))) return std::make_pair(d.bank, name);
        if (folder == STICK && (ext == d.ext || (isStateExt(ext) && isFile(STICK + name + d.ext))))
            return std::make_pair(d.bank, name);
    }
    return std::nullopt;
}

namespace {
void stop(const std::string &path, size_t pos) {
    std::vector<std::string> report = {"Nebulae stopped: " + path + " is not a UTF-8 text file (byte " +
                                       std::to_string(pos) + ")."};
    log(report[0]);
    touch(MARKER);
    backend().stopNebio();
    backend().run({"sh", SCRIPTS + "nebulae_leds.sh"});
    // Silence: SuperCollider and JACK are services of their own; a program or
    // Pd is a child of Nebulae and goes with it.
    backend().run({"systemctl", "stop", "sclang.service", "jack@*.service"});
    auto instrument = instrumentOf(path);
    if (instrument && remountFs) backend().run({"sh", SCRIPTS + "mountfs.sh", "rw"});
    bool mounted = mountStick();
    if (!instrument) {
        report.push_back("It is a Nebulae system file: reinstall the firmware.");
    } else {
        auto more = takeOut(*instrument, mounted);
        report.insert(report.end(), more.begin(), more.end());
    }
    for (size_t k = 1; k < report.size(); ++k) log(report[k]);
    if (mounted) {
        writeReport(report);
        backend().run({"umount", "/dev/sda1"});
    }
}
}  // namespace

void badFile(const std::string &path, size_t pos) {
    if (!enabled) throw PyError("BadTextFile", path + " is not UTF-8 (byte " + std::to_string(pos) + ")");
    try {
        stop(path, pos);
    } catch (const std::exception &e) {  // a step that fails must not change the exit code
        log(std::string("Could not finish the stop: ") + e.what());
    }
    backend().exit(EXIT_CODE);
    std::_Exit(EXIT_CODE);
}

}  // namespace fatal
}  // namespace neb
