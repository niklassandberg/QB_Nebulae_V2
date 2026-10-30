// log.h - minimal logging for nebio. Goes to stderr, which ends up in the
// nebulae.service journal next to the Python log. "<6>" / "<3>" in front is
// the syslog priority (info / error): the journal stores it as the level of
// the line ("journalctl -u nebulae -p err") and removes it. Not on a
// terminal (nebio tools, nebulae.py started by hand), where it would show.
#pragma once

#include <cstdarg>
#include <cstdio>
#include <mutex>
#include <string>
#include <unistd.h>

namespace nebio {

void setLastError(const std::string &msg);
const char *lastError();

inline const char *logPrefix(int prio) {
    static const bool journal = !isatty(STDERR_FILENO);
    if (!journal)
        return "";
    return prio <= 3 ? "<3>" : "<6>";
}

inline void logLine(int prio, const char *level, const char *fmt, va_list ap) {
    static std::mutex m;
    std::lock_guard<std::mutex> lock(m);
    std::fprintf(stderr, "%s[nebio] %s: ", logPrefix(prio), level);
    std::vfprintf(stderr, fmt, ap);
    std::fputc('\n', stderr);
    std::fflush(stderr);
}

inline void logInfo(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    logLine(6, "INFO", fmt, ap);
    va_end(ap);
}

inline void logError(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    setLastError(buf);
    std::fprintf(stderr, "%s[nebio] ERROR: %s\n", logPrefix(3), buf);
    std::fflush(stderr);
}

}  // namespace nebio
