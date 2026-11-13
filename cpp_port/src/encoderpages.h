// encoderpages.py: several values on the speed or pitch encoder ("page:" and
// "cv:" lines in the nebconfig block), saved in <name>.pages.
#pragma once

#include <array>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "classlogger.h"
#include "pyvalue.h"

namespace neb {

constexpr const char *PAGES_EXT = ".pages";
constexpr double PAGE_STEP = 0.01;
constexpr double PAGE_JUMP = 0.2;
constexpr int PAGE_JUMP_DELAY_MS = 125;
constexpr int SAVE_DELAY_MS = 1000;
constexpr int HOLD_MS = 500;
constexpr double CHOOSE_BRIGHT = 0.4;
constexpr int PAGE_PULSE_MS = 88;
constexpr double PAGE_DIM_LOW = 0.0, PAGE_DIM_HIGH = 0.01;

using Colour = std::array<int, 3>;
// Page 1 has no colour, like the plain encoder.
extern const Colour PAGE_COLOURS[5];
extern const Colour HOLD_COLOUR;   // cyan
extern const Colour HOLD2_COLOUR;  // orange

// 0..1 to lo..hi: lin, exp (lo, hi > 0) or int (rounded). Always a float.
double scale(const Value &value, const Value &lo, const Value &hi, const std::string &curve);
double pulse(const Value &now_ms);

struct Page {
    Page(std::string name, std::string path, Value lo, Value hi, std::string curve, Value value,
         Value step = F(PAGE_STEP))
        : name(std::move(name)), path(std::move(path)), lo(std::move(lo)), hi(std::move(hi)),
          curve(std::move(curve)), value(std::move(value)), step(std::move(step)) {}
    std::string name, path;
    Value lo, hi;
    std::string curve;
    Value value;  // 0..1
    Value step;
};

class EncoderPages {
public:
    EncoderPages(std::string encoder, std::vector<Page *> pages, std::optional<std::string> cv_target,
                 std::optional<Colour> hold = std::nullopt);
    std::vector<std::string> names() const;
    Page &page();
    void step(const Value &steps);
    void move(const Value &amount);
    void nextPage();
    void startChoosing() { candidate = cv_target; }
    void setCandidate(bool on);  // on: the CV goes to the page shown; off: to none, if it went here
    bool candidateShown();
    bool commitCandidate();
    Value withCV(const Page &page, const Value &cv) const;
    std::vector<std::pair<std::string, double>> outputs(const Value &cv) const;
    Colour colour(long long index) const;
    Value marked(long long index) const;  // True, or the hold colour / None

    std::string encoder;
    std::vector<Page *> pages;
    size_t current = 0;
    std::optional<std::string> cv_target, candidate;
    std::optional<Colour> hold;  // a hold: layer (its colour): no CV
};

using EncoderMap = std::vector<std::pair<std::string, EncoderPages *>>;  // in insertion order

// Lines "value,<encoder>,<page>,<0..1>" and "cv,<encoder>,<page|none>".
class PageState {
public:
    explicit PageState(std::string path) : path(std::move(path)) {}
    void load(const EncoderMap &encoders);
    void changed(const Value &now) { dirty_time = now; }
    void saveIfDue(const Value &now, const EncoderMap &encoders);
    void save(const EncoderMap &encoders);

    std::string path;
    Value dirty_time;  // None: nothing to save

private:
    Logger log_{"PageState"};
};

}  // namespace neb
