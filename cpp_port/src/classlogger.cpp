#include "classlogger.h"

#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <vector>

#include "configsettings.h"

namespace neb {

int journalPriority(int levelno) {
    if (levelno >= CRITICAL) return 2;
    if (levelno >= ERROR) return 3;
    if (levelno >= WARNING) return 4;
    if (levelno >= INFO) return 6;
    return 7;
}

std::string levelName(int levelno) {
    switch (levelno) {
    case DEBUG: return "DEBUG";
    case STATS: return "STATS";
    case INFO: return "INFO";
    case WARNING: return "WARNING";
    case ERROR: return "ERROR";
    case CRITICAL: return "CRITICAL";
    case 0: return "NOTSET";
    }
    return "Level " + std::to_string(levelno);
}

int levelNumber(const std::string &name) {
    for (int l : {DEBUG, STATS, INFO, WARNING, ERROR, CRITICAL})
        if (levelName(l) == name) return l;
    if (name == "WARN") return WARNING;
    if (name == "FATAL") return CRITICAL;
    if (name == "NOTSET") return 0;
    return -1;
}

std::string journalFormat(int levelno, const std::string &pathname, int lineno,
                          const std::string &message, bool journal) {
    size_t slash = pathname.find_last_of('/');
    std::string filename = slash == std::string::npos ? pathname : pathname.substr(slash + 1);
    std::string text = levelName(levelno) + " [" + filename + ":" + std::to_string(lineno) + "]: " + message;
    if (!journal) return text;
    // str.splitlines(): no empty last line for a trailing newline.
    std::string prefix = "<" + std::to_string(journalPriority(levelno)) + ">";
    std::vector<std::string> lines;
    size_t start = 0;
    while (start < text.size()) {
        size_t nl = text.find_first_of("\r\n", start);
        if (nl == std::string::npos) {
            lines.push_back(text.substr(start));
            break;
        }
        lines.push_back(text.substr(start, nl - start));
        start = nl + ((text[nl] == '\r' && nl + 1 < text.size() && text[nl + 1] == '\n') ? 2 : 1);
    }
    std::string out;
    for (size_t k = 0; k < lines.size(); ++k) {
        if (k) out += "\n";
        out += prefix + lines[k];
    }
    return out;
}

static int g_level = -2;  // -2: not read yet
static std::mutex g_mutex;

int Logger::rootLevel() {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_level == -2) {
        const char *env = std::getenv("NEB_LOG_LEVEL");
        std::string name = env && *env ? env : configSettings().logLevel();
        for (auto &c : name) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        int l = levelNumber(name);
        g_level = l < 0 ? INFO : l;
    }
    return g_level;
}

void Logger::setRootLevel(int level) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_level = level;
}

void Logger::log(int level, const char *file, int line, const char *fmt, ...) const {
    if (level < rootLevel()) return;
    char buf[2048];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    static const bool journal = !isatty(STDERR_FILENO);
    std::string text = journalFormat(level, file, line, buf, journal);
    std::lock_guard<std::mutex> lock(g_mutex);
    std::fprintf(stderr, "%s\n", text.c_str());
}

}  // namespace neb
