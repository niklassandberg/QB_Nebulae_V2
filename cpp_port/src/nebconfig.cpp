#include "nebconfig.h"

#include <algorithm>
#include <cctype>
#include <set>

#include "textfile.h"

namespace neb {

namespace {

const double PAGE_STEP = 0.01;
const char *PAGE_FIELDS = "<path>,<min>,<max>[,curve[,default[,step]]]";
const std::vector<std::string> ENCODERS = {"speed", "pitch"};
const std::vector<std::string> HOLD_BUTTONS = {"record", "file", "reset", "freeze", "source"};
const std::vector<std::string> OSC_CURVES = {"lin", "exp", "int"};

bool contains(const std::vector<std::string> &list, const std::string &x) {
    return std::find(list.begin(), list.end(), x) != list.end();
}

bool startsWith(const std::string &s, const std::string &prefix) { return s.compare(0, prefix.size(), prefix) == 0; }

std::string lower(std::string s) {
    for (auto &c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
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

std::string join(const std::vector<std::string> &parts, const std::string &sep) {
    std::string out;
    for (size_t k = 0; k < parts.size(); ++k) out += (k ? sep : "") + parts[k];
    return out;
}

// repr() of a str, as Python's error messages show it.
std::string repr(const std::string &s) {
    char q = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, q);
    for (char c : s) {
        if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c == q) out += std::string("\\") + c;
        else out += c;
    }
    return out + q;
}

struct BadEntry {
    std::string message;
};

double toNumber(const std::string &text) {
    auto f = pyFloat(text);
    if (!f) throw BadEntry{"could not convert string to float: " + repr(text)};
    return *f;
}

PageSpec pageFields(const std::string &name, const std::vector<std::string> &values, const std::string &usage) {
    if (values.size() < 3 || !startsWith(values[0], "/")) throw BadEntry{usage};
    double lo = toNumber(values[1]), hi = toNumber(values[2]);
    std::string curve = values.size() > 3 && !values[3].empty() ? lower(values[3]) : "lin";
    if (!contains(OSC_CURVES, curve)) throw BadEntry{"curve one of ('lin', 'exp', 'int')"};
    if (curve == "exp" && (lo <= 0 || hi <= 0)) throw BadEntry{"exp needs min and max > 0"};
    double value = values.size() > 4 && !values[4].empty() ? toNumber(values[4]) : 0.0;
    double step = values.size() > 5 && !values[5].empty() ? toNumber(values[5]) : PAGE_STEP;
    if (!(0.0 < step && step <= 1.0)) throw BadEntry{"step: a part of the range per click, 0 < step <= 1"};
    value = value > 0.0 ? value : 0.0;  // NaN: 0, as max(0.0, nan)
    value = value < 1.0 ? value : 1.0;
    return PageSpec{name, values[0], lo, hi, curve, value, step};
}

std::vector<std::string> stripped(const std::vector<std::string> &values) {
    std::vector<std::string> out;
    for (auto &v : values) out.push_back(strip(v));
    return out;
}

template <class T>
T &slot(std::vector<std::pair<std::string, T>> &list, const std::string &key) {
    for (auto &kv : list)
        if (kv.first == key) return kv.second;
    list.emplace_back(key, T());
    return list.back().second;
}

bool isSpace(char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v'; }

// " ".join(text.split())
std::string squeeze(const std::string &text) {
    std::string out;
    size_t i = 0;
    while (i < text.size()) {
        while (i < text.size() && isSpace(text[i])) ++i;
        size_t start = i;
        while (i < text.size() && !isSpace(text[i])) ++i;
        if (i > start) out += (out.empty() ? "" : " ") + text.substr(start, i - start);
    }
    return out;
}

bool isNumber(const std::string &t, size_t &i) {  // -?\d+ at i
    size_t start = i;
    if (i < t.size() && t[i] == '-') ++i;
    size_t digits = i;
    while (i < t.size() && std::isdigit(static_cast<unsigned char>(t[i]))) ++i;
    if (i == digits) {
        i = start;
        return false;
    }
    return true;
}

std::string replaceAll(std::string s, const std::string &from, const std::string &to) {
    for (size_t p = 0; (p = s.find(from, p)) != std::string::npos; p += to.size()) s.replace(p, from.size(), to);
    return s;
}

// One Pd statement as a nebconfig entry: "#X text <x> <y> nebconfig <entry>".
std::optional<std::string> pdEntry(const std::string &statement) {
    std::string t = squeeze(statement);
    const std::string head = "#X text ";
    if (!startsWith(t, head)) return std::nullopt;
    size_t i = head.size();
    if (!isNumber(t, i) || i >= t.size() || t[i++] != ' ') return std::nullopt;
    if (!isNumber(t, i) || i >= t.size() || t[i++] != ' ') return std::nullopt;
    if (t.compare(i, 9, "nebconfig") != 0) return std::nullopt;
    i += 9;
    if (i >= t.size() || t[i] != ' ') return std::nullopt;
    std::string entry = t.substr(i + 1);
    if (!entry.empty() && entry.back() == ';') entry.pop_back();
    entry = replaceAll(replaceAll(replaceAll(entry, "\\,", ","), "\\;", ";"), "\\$", "$");
    entry = strip(entry);
    std::string joined;  // re.sub(r"\s*,\s*", ",", ...)
    for (size_t k = 0; k < entry.size(); ++k) {
        if (entry[k] == ',') {
            while (!joined.empty() && isSpace(joined.back())) joined.pop_back();
            joined += ',';
            while (k + 1 < entry.size() && isSpace(entry[k + 1])) ++k;
        } else {
            joined += entry[k];
        }
    }
    size_t f = joined.rfind(",f ");  // the box width ", f 20"
    if (f != std::string::npos && f + 3 < joined.size() &&
        std::all_of(joined.begin() + static_cast<long>(f) + 3, joined.end(),
                    [](char c) { return std::isdigit(static_cast<unsigned char>(c)); }))
        joined.erase(f);
    return joined;
}

// A .pd file's statements end in an unescaped ";" before a line end.
std::vector<std::string> pdEntries(const std::string &text) {
    std::vector<std::string> entries;
    size_t start = 0, i = 0;
    auto take = [&](size_t end) {
        if (auto e = pdEntry(text.substr(start, end - start))) entries.push_back(*e);
    };
    while (i < text.size()) {
        if (text[i] == ';' && !(i > 0 && text[i - 1] == '\\')) {
            size_t k = i + 1;
            while (k < text.size() && (text[k] == ' ' || text[k] == '\t')) ++k;
            if (k < text.size() && text[k] == '\r') ++k;
            if (k < text.size() && text[k] == '\n') {
                take(i);
                start = i = k + 1;
                continue;
            }
        }
        ++i;
    }
    take(text.size());
    return entries;
}

}  // namespace

NebConfig::NebConfig(const std::vector<std::string> &entries, std::string body_) : body(std::move(body_)) {
    for (auto &raw : entries) {
        std::string line = pyRstrip(raw);
        if (line.empty() || startsWith(strip(line), "#")) continue;
        std::vector<std::string> values = split(line, ',');
        std::string key = values.front();
        values.erase(values.begin());
        slot(entries_, key) = values;
    }
}

NebConfig NebConfig::readFile(const std::string &path) {
    std::string text = textfile::read(path);
    if (path.size() >= 3 && path.compare(path.size() - 3, 3, ".pd") == 0) return NebConfig(pdEntries(text), text);
    std::vector<std::string> entries;
    std::string body;
    bool inside = false;
    size_t start = 0;
    while (start < text.size()) {
        size_t nl = text.find('\n', start);
        size_t end = nl == std::string::npos ? text.size() : nl + 1;
        std::string line = text.substr(start, end - start);
        start = end;
        if (startsWith(line, "nebconfigbegin")) inside = true;
        if (inside) {
            if (startsWith(line, "nebconfigend"))
                inside = false;
            else if (!startsWith(line, "nebconfigbegin"))
                entries.push_back(line);
        } else {
            body += line;
        }
    }
    return NebConfig(entries, body);
}

const std::vector<std::string> *NebConfig::entry(const std::string &name) const {
    for (auto &kv : entries_)
        if (kv.first == name) return &kv.second;
    return nullptr;
}

std::optional<std::string> NebConfig::value(const std::string &name) const {
    auto *values = entry(name);
    if (!values || values->empty()) return std::nullopt;
    return values->front();
}

std::string NebConfig::value(const std::string &name, const std::string &fallback) const {
    return value(name).value_or(fallback);
}

OrderedDict NebConfig::asDict() const {
    OrderedDict d;
    for (auto &kv : entries_) {
        std::vector<Value> list;
        for (auto &v : kv.second) list.push_back(Value::str(v));
        d.set(kv.first, Value::of(list));
    }
    return d;
}

std::string NebConfig::encoderType(const std::string &name) const {
    std::string v = lower(strip(value(name, "")));
    if (v == "rawencoder" || v == "pages") return v;
    std::string prefix = "page:" + name + ":";
    for (auto &kv : entries_)
        if (startsWith(kv.first, prefix)) return "pages";
    return "hybrid";
}

double NebConfig::outputPeriod() const {
    auto ksmps = pyInt(value("ksmps", "128"));
    auto sr = pyInt(value("sr", "48000"));
    if (!ksmps || !sr) throw PyError("ValueError", "invalid literal for int()");
    if (*sr == 0) throw PyError("ZeroDivisionError", "float division by zero");
    double block_ms = (static_cast<double>(*ksmps) / static_cast<double>(*sr)) * 1000.0;
    double period = block_ms * 75;
    return period > 100.0 ? period : 100.0;
}

std::optional<std::string> NebConfig::speedLeds() const {
    std::string v = lower(strip(value("speedleds", "")));
    if (v == "playback") return v;
    return std::nullopt;
}

int NebConfig::oscPort() const {
    auto v = value("oscport");
    if (!v) return DEFAULT_OSC_PORT;
    long long port = pyInt(*v).value_or(0);
    if (!(1024 <= port && port <= 65535))
        throw PyError("ValueError", "oscport " + repr(*v) + ": a UDP port, 1024..65535");
    return static_cast<int>(port);
}

std::pair<std::vector<OscBinding>, std::vector<std::string>> NebConfig::oscBindings() const {
    std::vector<OscBinding> bindings;
    std::vector<std::string> errors;
    for (auto &kv : entries_) {
        if (!startsWith(kv.first, "osc:")) continue;
        std::string control = strip(kv.first.substr(4));
        auto values = stripped(kv.second);
        try {
            if (control.empty() || values.size() < 3 || !startsWith(values[0], "/"))
                throw BadEntry{"osc:<control>,<path>,<min>,<max>[,curve]"};
            double lo = toNumber(values[1]), hi = toNumber(values[2]);
            std::string curve = values.size() > 3 && !values[3].empty() ? lower(values[3]) : "lin";
            if (!contains(OSC_CURVES, curve)) throw BadEntry{"curve one of ('lin', 'exp', 'int')"};
            if (curve == "exp" && (lo <= 0 || hi <= 0)) throw BadEntry{"exp needs min and max > 0"};
            bindings.push_back(OscBinding{control, values[0], lo, hi, curve});
        } catch (const BadEntry &e) {
            errors.push_back(kv.first + "," + join(values, ",") + ": " + e.message);
        }
    }
    return {bindings, errors};
}

std::pair<EncoderPageSpecs, std::vector<std::string>> NebConfig::encoderPages() const {
    EncoderPageSpecs pages;
    std::vector<std::string> errors;
    std::string usage = std::string("page:<speed|pitch>:<name>,") + PAGE_FIELDS;
    for (auto &kv : entries_) {
        if (!startsWith(kv.first, "page:")) continue;
        auto values = stripped(kv.second);
        try {
            auto parts = split(kv.first, ':');
            if (parts.size() != 3 || !contains(ENCODERS, parts[1]) || parts[2].empty()) throw BadEntry{usage};
            // The list first, as Python's setdefault() runs before the fields are read.
            PageList &list = slot(pages, parts[1]);
            list.push_back(pageFields(parts[2], values, usage));
        } catch (const BadEntry &e) {
            errors.push_back(kv.first + "," + join(values, ",") + ": " + e.message);
        }
    }
    return {pages, errors};
}

std::pair<HoldPageSpecs, std::vector<std::string>> NebConfig::holdPages() const {
    HoldPageSpecs holds;
    std::vector<std::string> errors;
    std::string usage = "hold:<" + join(HOLD_BUTTONS, "|") + ">[+<button>]:<speed|pitch>:<name>," + PAGE_FIELDS;
    for (auto &kv : entries_) {
        if (!startsWith(kv.first, "hold:")) continue;
        auto values = stripped(kv.second);
        try {
            auto parts = split(kv.first, ':');
            if (parts.size() != 4 || !contains(ENCODERS, parts[2]) || parts[3].empty()) throw BadEntry{usage};
            auto buttons = split(parts[1], '+');
            std::set<std::string> unique(buttons.begin(), buttons.end());
            bool known = std::all_of(buttons.begin(), buttons.end(),
                                     [](const std::string &b) { return contains(HOLD_BUTTONS, b); });
            if (buttons.size() > 2 || unique.size() != buttons.size() || !known) throw BadEntry{usage};
            PageList &list = slot(slot(holds, parts[1]), parts[2]);
            list.push_back(pageFields(parts[3], values, usage));
        } catch (const BadEntry &e) {
            errors.push_back(kv.first + "," + join(values, ",") + ": " + e.message);
        }
    }
    return {holds, errors};
}

std::vector<std::pair<std::string, std::optional<std::string>>> NebConfig::cvTargets() const {
    std::vector<std::pair<std::string, std::optional<std::string>>> targets;
    for (auto &encoder : ENCODERS) {
        auto v = value("cv:" + encoder);
        if (!v) continue;
        std::string target = strip(*v);
        targets.emplace_back(encoder, target.empty() || target == "none" ? std::nullopt
                                                                         : std::optional<std::string>(target));
    }
    return targets;
}

}  // namespace neb
