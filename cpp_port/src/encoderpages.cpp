#include "encoderpages.h"

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

#include "textfile.h"

namespace neb {

const Colour PAGE_COLOURS[5] = {
    {4095, 4095, 4095},
    {4095, 0, 0},     // red
    {0, 600, 4095},   // blue
    {0, 4095, 300},   // green
    {4095, 0, 2600},  // pink
};
const Colour HOLD_COLOUR = {0, 4095, 4095};
const Colour HOLD2_COLOUR = {4095, 2000, 0};

namespace {
// Python's max(0.0, v) and min(1.0, v): the first argument unless the other is bigger/smaller.
Value clamp01(const Value &v) {
    Value m = gt(v, F(0.0)) ? v : F(0.0);
    return lt(m, F(1.0)) ? m : F(1.0);
}

double pyMod(double a, double b) {
    if (b == 0.0) throw PyError("ZeroDivisionError", "float modulo");
    double m = std::fmod(a, b);
    if (m != 0.0 && ((b < 0) != (m < 0))) m += b;
    else if (m == 0.0) m = std::copysign(0.0, b);
    return m;
}

// Length of a str.splitlines() separator at text[i] (UTF-8), 0 if none.
size_t lineBreak(const std::string &text, size_t i) {
    static const char *const multi[] = {"\r\n", "\xc2\x85", "\xe2\x80\xa8", "\xe2\x80\xa9"};
    for (const char *m : multi)
        if (text.compare(i, std::strlen(m), m) == 0) return std::strlen(m);
    return std::strchr("\r\n\v\f\x1c\x1d\x1e", text[i]) && text[i] ? 1 : 0;
}

// str.splitlines() of UTF-8 text.
std::vector<std::string> splitlines(const std::string &text) {
    std::vector<std::string> out;
    size_t start = 0, i = 0;
    while (i < text.size()) {
        size_t n = lineBreak(text, i);
        if (n == 0) {
            ++i;
            continue;
        }
        out.push_back(text.substr(start, i - start));
        i += n;
        start = i;
    }
    if (start < text.size()) out.push_back(text.substr(start));
    return out;
}

std::vector<std::string> split(const std::string &s, char sep) {
    std::vector<std::string> out;
    size_t start = 0;
    while (true) {
        size_t p = s.find(sep, start);
        out.push_back(s.substr(start, p == std::string::npos ? std::string::npos : p - start));
        if (p == std::string::npos) return out;
        start = p + 1;
    }
}

const EncoderPages *find(const EncoderMap &m, const std::string &name) {
    for (auto &kv : m)
        if (kv.first == name) return kv.second;
    return nullptr;
}
}  // namespace

double scale(const Value &value, const Value &lo, const Value &hi, const std::string &curve) {
    double f = toFloat(value);
    double v = f > 0.0 ? f : 0.0;
    v = v < 1.0 ? v : 1.0;
    if (curve == "exp") {
        if (lo.number() == 0.0) throw PyError("ZeroDivisionError", "division by zero");
        double base = hi.number() / lo.number();
        if (base < 0 && std::floor(v) != v) throw PyError("ValueError", "math domain error");
        double p = std::pow(base, v);
        if (std::isinf(p) && std::isfinite(base)) throw PyError("OverflowError", "math range error");
        return lo.number() * p;
    }
    double out = add(lo, F(sub(hi, lo).number() * v)).number();
    if (curve == "int") {
        if (std::isnan(out)) throw PyError("ValueError", "cannot convert float NaN to integer");
        if (std::isinf(out)) throw PyError("OverflowError", "cannot convert float infinity to integer");
        return pyRound0(out);
    }
    return out;
}

double pulse(const Value &now_ms) {
    double phase = pyMod(now_ms.number(), PAGE_PULSE_MS) / static_cast<double>(PAGE_PULSE_MS);
    return PAGE_DIM_LOW + (PAGE_DIM_HIGH - PAGE_DIM_LOW) * 0.5 * (1.0 - std::cos(2.0 * M_PI * phase));
}

EncoderPages::EncoderPages(std::string encoder_, std::vector<Page *> pages_, std::optional<std::string> target,
                           std::optional<Colour> hold_)
    : encoder(std::move(encoder_)), pages(std::move(pages_)), hold(hold_) {
    if (target) {
        for (auto &n : names())
            if (n == *target) cv_target = target;
    }
}

std::vector<std::string> EncoderPages::names() const {
    std::vector<std::string> out;
    for (auto *p : pages) out.push_back(p->name);
    return out;
}

Page &EncoderPages::page() {
    if (current >= pages.size()) throw PyError("IndexError", "list index out of range");
    return *pages[current];
}

void EncoderPages::step(const Value &steps) { move(mul(steps, page().step)); }

void EncoderPages::move(const Value &amount) {
    Page &p = page();
    p.value = clamp01(roundTo(add(p.value, amount), 6));
}

void EncoderPages::nextPage() {
    if (pages.empty()) throw PyError("ZeroDivisionError", "integer modulo by zero");
    current = (current + 1) % pages.size();
}

void EncoderPages::setCandidate(bool on) {
    if (on) {
        candidate = page().name;
    } else {
        const std::string &shown = page().name;
        if (candidate && *candidate == shown) candidate.reset();
    }
}

bool EncoderPages::candidateShown() {
    const std::string &shown = page().name;
    return candidate && *candidate == shown;
}

bool EncoderPages::commitCandidate() {
    bool changed = candidate != cv_target;
    cv_target = candidate;
    return changed;
}

Value EncoderPages::withCV(const Page &p, const Value &cv) const {
    Value v = (cv_target && p.name == *cv_target) ? add(p.value, cv) : p.value;
    return clamp01(v);
}

std::vector<std::pair<std::string, double>> EncoderPages::outputs(const Value &cv) const {
    std::vector<std::pair<std::string, double>> out;
    for (auto *p : pages) out.emplace_back(p->path, scale(withCV(*p, cv), p->lo, p->hi, p->curve));
    return out;
}

Colour EncoderPages::colour(long long index) const {
    if (hold && index == 0) return *hold;
    long long k = index % 5;
    if (k < 0) k += 5;
    return PAGE_COLOURS[k];
}

Value EncoderPages::marked(long long index) const {
    if (index > 0) return Value::boolean(true);
    if (!hold) return Value::none();
    return Value::of({I((*hold)[0]), I((*hold)[1]), I((*hold)[2])});
}

void PageState::load(const EncoderMap &encoders) {
    std::string text;
    try {
        text = textfile::read(path);
    } catch (const PyError &e) {
        if (!textfile::isOSError(e.type)) throw;
        return;
    }
    for (const std::string &line : splitlines(text)) {
        std::vector<std::string> parts = split(strip(line), ',');
        if (parts.size() < 3) continue;
        auto *pages = const_cast<EncoderPages *>(find(encoders, parts[1]));
        if (!pages) continue;
        std::vector<std::string> names = pages->names();
        auto at = std::find(names.begin(), names.end(), parts[2]);
        if (parts[0] == "value" && parts.size() == 4 && at != names.end()) {
            auto v = pyFloat(parts[3]);
            if (v) pages->pages[at - names.begin()]->value = clamp01(F(*v));
        } else if (parts[0] == "cv") {
            if (parts[2] == "none")
                pages->cv_target.reset();
            else if (at != names.end())
                pages->cv_target = parts[2];
        }
    }
}

void PageState::saveIfDue(const Value &now, const EncoderMap &encoders) {
    if (dirty_time.isNone() || lt(sub(now, dirty_time), I(SAVE_DELAY_MS))) return;
    dirty_time = Value::none();
    save(encoders);
}

static bool fsyncWrite(const std::string &file, const std::string &text, std::string &err) {
    int fd = ::open(file.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        err = std::strerror(errno);
        return false;
    }
    bool ok = ::write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size()) && ::fsync(fd) == 0;
    if (!ok) err = std::strerror(errno);
    ::close(fd);
    return ok;
}

static bool makedirs(const std::string &dir) {
    if (dir.empty()) return false;  // os.makedirs("") raises
    std::string partial;
    for (size_t i = 0; i <= dir.size(); ++i) {
        if (i == dir.size() || dir[i] == '/') {
            if (!partial.empty() && ::mkdir(partial.c_str(), 0777) != 0 && errno != EEXIST) return false;
        }
        if (i < dir.size()) partial += dir[i];
    }
    return true;
}

void PageState::save(const EncoderMap &encoders) {
    std::string text;
    for (auto &kv : encoders) {
        for (auto *p : kv.second->pages) {
            Value r = roundTo(p->value, 4);
            text += "value," + kv.first + "," + p->name + "," + pyStr(r) + "\n";
        }
        const auto &t = kv.second->cv_target;
        text += "cv," + kv.first + "," + (t && !t->empty() ? *t : std::string("none")) + "\n";
    }
    if (text.empty()) text = "\n";  // "\n".join([]) + "\n"
    size_t slash = path.find_last_of('/');
    std::string dir = slash == std::string::npos ? "" : path.substr(0, slash);
    std::string err;
    if (!makedirs(dir)) {
        NLOG(log_, ERROR, "Could not save %s: %s", path.c_str(), "makedirs");
        return;
    }
    std::string tmp = path + ".tmp";
    if (!fsyncWrite(tmp, text, err) || std::rename(tmp.c_str(), path.c_str()) != 0) {
        NLOG(log_, ERROR, "Could not save %s: %s", path.c_str(), err.c_str());
    }
}

}  // namespace neb
