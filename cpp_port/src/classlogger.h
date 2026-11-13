// classlogger.py: log lines to stderr (the journal), "<N>" journal priority
// prefix on every line when stderr is not a terminal. Level: NEB_LOG_LEVEL,
// else log_level from configsettings.
#pragma once

#include <cstdarg>
#include <string>

namespace neb {

enum LogLevel { DEBUG = 10, STATS = 15, INFO = 20, WARNING = 30, ERROR = 40, CRITICAL = 50 };

int journalPriority(int levelno);                 // _priority()
std::string levelName(int levelno);               // logging.getLevelName()
int levelNumber(const std::string &name);         // -1: unknown
// JournalFormatter.format() of "%(levelname)s [%(filename)s:%(lineno)d]: %(message)s".
std::string journalFormat(int levelno, const std::string &pathname, int lineno,
                          const std::string &message, bool journal);

class Logger {
public:
    explicit Logger(std::string name) : name_(std::move(name)) {}
    void log(int level, const char *file, int line, const char *fmt, ...) const
        __attribute__((format(printf, 5, 6)));
    const std::string &name() const { return name_; }

    static int rootLevel();               // set once from NEB_LOG_LEVEL / configsettings
    static void setRootLevel(int level);  // tests

private:
    std::string name_;
};

}  // namespace neb

#define NLOG(logger, level, ...) (logger).log((level), __FILE__, __LINE__, __VA_ARGS__)
