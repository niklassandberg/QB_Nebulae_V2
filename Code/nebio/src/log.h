// log.h - minimal logging for nebio. Goes to stderr, which ends up in the
// nebulae.service journal next to the Python log.
#pragma once

#include <cstdarg>
#include <cstdio>
#include <mutex>
#include <string>

namespace nebio {

void setLastError(const std::string &msg);
const char *lastError();

inline void logLine(const char *level, const char *fmt, va_list ap) {
    static std::mutex m;
    std::lock_guard<std::mutex> lock(m);
    std::fprintf(stderr, "[nebio] %s: ", level);
    std::vfprintf(stderr, fmt, ap);
    std::fputc('\n', stderr);
    std::fflush(stderr);
}

inline void logInfo(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    logLine("INFO", fmt, ap);
    va_end(ap);
}

inline void logError(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    setLastError(buf);
    std::fprintf(stderr, "[nebio] ERROR: %s\n", buf);
    std::fflush(stderr);
}

}  // namespace nebio
