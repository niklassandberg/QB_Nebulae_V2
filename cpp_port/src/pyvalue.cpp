#include "pyvalue.h"

#include <cctype>
#include <charconv>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <regex>

namespace neb {

double Value::number() const {
    switch (type) {
    case Bool: return b ? 1.0 : 0.0;
    case Int: return static_cast<double>(i);
    case Float: return f;
    default: throw PyError("TypeError", "not a number");
    }
}

bool Value::truthy() const {
    switch (type) {
    case None: return false;
    case Bool: return b;
    case Int: return i != 0;
    case Float: return f != 0.0;
    case Str: return !s.empty();
    case List: return !list.empty();
    }
    return false;
}

bool operator==(const Value &a, const Value &b) {
    if (a.isNumber() && b.isNumber()) {
        if (a.type != Value::Float && b.type != Value::Float)
            return (a.type == Value::Bool ? a.b : a.i) == (b.type == Value::Bool ? b.b : b.i);
        return a.number() == b.number();
    }
    if (a.type != b.type) return false;
    switch (a.type) {
    case Value::None: return true;
    case Value::Str: return a.s == b.s;
    case Value::List: return a.list == b.list;
    default: return false;
    }
}

// Correctly rounded decimal text (glibc printf: exact value, ties to even),
// read back: what Python's round() does.
double pyRound(double x, int ndigits) {
    if (!std::isfinite(x)) return x;
    char buf[400];
    std::snprintf(buf, sizeof buf, "%.*f", ndigits, x);
    double r = std::strtod(buf, nullptr);
    return r == 0.0 ? std::copysign(0.0, x) : r;
}

// round(x) is an int: no negative zero.
double pyRound0(double x) { return std::nearbyint(x) + 0.0; }

std::string pyRepr(double x) {
    if (std::isnan(x)) return "nan";
    if (std::isinf(x)) return x > 0 ? "inf" : "-inf";
    if (x == 0.0) return std::signbit(x) ? "-0.0" : "0.0";
    // Shortest digits that read back to x (as Python's repr).
    char buf[64];
    auto res = std::to_chars(buf, buf + sizeof buf, x, std::chars_format::scientific);
    std::string sci(buf, res.ptr);
    bool neg = sci[0] == '-';
    if (neg) sci.erase(0, 1);
    size_t e = sci.find('e');
    std::string mant = sci.substr(0, e);
    int exp10 = std::atoi(sci.c_str() + e + 1);
    std::string digits;
    for (char c : mant)
        if (c != '.') digits += c;
    int decpt = exp10 + 1;  // digits[0] is at 10^(decpt-1)
    std::string out;
    if (decpt <= -4 || decpt > 16) {
        out = digits.substr(0, 1);
        if (digits.size() > 1) out += "." + digits.substr(1);
        char eb[16];
        std::snprintf(eb, sizeof eb, "e%c%02d", exp10 < 0 ? '-' : '+', std::abs(exp10));
        out += eb;
    } else if (decpt <= 0) {
        out = "0." + std::string(-decpt, '0') + digits;
    } else if (static_cast<size_t>(decpt) >= digits.size()) {
        out = digits + std::string(decpt - digits.size(), '0') + ".0";
    } else {
        out = digits.substr(0, decpt) + "." + digits.substr(decpt);
    }
    return neg ? "-" + out : out;
}

std::string pyStr(const Value &v) {
    switch (v.type) {
    case Value::None: return "None";
    case Value::Bool: return v.b ? "True" : "False";
    case Value::Int: return std::to_string(v.i);
    case Value::Float: return pyRepr(v.f);
    case Value::Str: return v.s;
    case Value::List: {
        std::string out = "[";
        for (size_t k = 0; k < v.list.size(); ++k) {
            if (k) out += ", ";
            const Value &x = v.list[k];
            out += x.type == Value::Str ? "'" + x.s + "'" : pyStr(x);
        }
        return out + "]";
    }
    }
    return "";
}

namespace {
// str.isspace() characters in UTF-8.
const char *const kSpaces[] = {
    " ", "\t", "\n", "\v", "\f", "\r", "\x1c", "\x1d", "\x1e", "\x1f",
    "\xc2\x85", "\xc2\xa0", "\xe1\x9a\x80", "\xe2\x80\x80", "\xe2\x80\x81", "\xe2\x80\x82", "\xe2\x80\x83",
    "\xe2\x80\x84", "\xe2\x80\x85", "\xe2\x80\x86", "\xe2\x80\x87", "\xe2\x80\x88", "\xe2\x80\x89",
    "\xe2\x80\x8a", "\xe2\x80\xa8", "\xe2\x80\xa9", "\xe2\x80\xaf", "\xe2\x81\x9f", "\xe3\x80\x80",
};

size_t spaceAt(const std::string &s, size_t i) {
    for (const char *sp : kSpaces) {
        size_t n = std::strlen(sp);
        if (s.compare(i, n, sp) == 0) return n;
    }
    return 0;
}

size_t spaceBefore(const std::string &s, size_t end) {
    for (const char *sp : kSpaces) {
        size_t n = std::strlen(sp);
        if (end >= n && s.compare(end - n, n, sp) == 0) return n;
    }
    return 0;
}
}  // namespace

std::string strip(const std::string &text) {
    size_t a = 0, b = text.size(), n;
    while (a < b && (n = spaceAt(text, a))) a += n;
    while (b > a && (n = spaceBefore(text, b))) b -= n;
    return text.substr(a, b - a);
}

std::string pyRstrip(const std::string &text) {
    size_t b = text.size(), n;
    while (b > 0 && (n = spaceBefore(text, b))) b -= n;
    return text.substr(0, b);
}

size_t pyIndent(const std::string &text) {
    size_t a = 0, count = 0, n;
    while (a < text.size() && (n = spaceAt(text, a))) {
        a += n;
        ++count;
    }
    return count;
}

static std::string withoutUnderscores(const std::string &t) {
    std::string out;
    for (char c : t)
        if (c != '_') out += c;
    return out;
}

std::optional<double> pyFloat(const std::string &text) {
    static const std::regex number(
        R"(^[+-]?(?:(?:[0-9](?:_?[0-9])*\.(?:[0-9](?:_?[0-9])*)?|\.[0-9](?:_?[0-9])*|[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?)$)");
    static const std::regex special(R"(^[+-]?(?:inf|infinity|nan)$)", std::regex::icase);
    std::string t = strip(text);
    if (std::regex_match(t, special)) {
        bool neg = t[0] == '-';
        bool nan = t.find_first_of("nN") != std::string::npos && t.find_first_of("iI") == std::string::npos;
        double v = nan ? std::nan("") : HUGE_VAL;
        return neg ? -v : v;
    }
    if (!std::regex_match(t, number)) return std::nullopt;
    return std::strtod(withoutUnderscores(t).c_str(), nullptr);
}

std::optional<long long> pyInt(const std::string &text) {
    static const std::regex integer(R"(^[+-]?[0-9](?:_?[0-9])*$)");
    std::string t = strip(text);
    if (!std::regex_match(t, integer)) return std::nullopt;
    errno = 0;
    long long v = std::strtoll(withoutUnderscores(t).c_str(), nullptr, 10);
    return v;  // strtoll saturates at LLONG_MIN/MAX
}

static bool bothInts(const Value &a, const Value &b) {
    if (!a.isNumber() || !b.isNumber()) throw PyError("TypeError", "unsupported operand");
    return a.type != Value::Float && b.type != Value::Float;
}

static long long asInt(const Value &v) { return v.type == Value::Bool ? (v.b ? 1 : 0) : v.i; }

Value add(const Value &a, const Value &b) {
    return bothInts(a, b) ? I(asInt(a) + asInt(b)) : F(a.number() + b.number());
}

Value sub(const Value &a, const Value &b) {
    return bothInts(a, b) ? I(asInt(a) - asInt(b)) : F(a.number() - b.number());
}

Value mul(const Value &a, const Value &b) {
    return bothInts(a, b) ? I(asInt(a) * asInt(b)) : F(a.number() * b.number());
}

bool lt(const Value &a, const Value &b) {
    if (bothInts(a, b)) return asInt(a) < asInt(b);
    return a.number() < b.number();
}

bool gt(const Value &a, const Value &b) { return lt(b, a); }

Value roundTo(const Value &v, int ndigits) {
    if (v.type == Value::Float) return F(pyRound(v.f, ndigits));
    if (v.type == Value::Int || v.type == Value::Bool) return I(asInt(v));
    throw PyError("TypeError", "round()");
}

long long toInt(const Value &v) {
    switch (v.type) {
    case Value::Bool: return v.b ? 1 : 0;
    case Value::Int: return v.i;
    case Value::Float:
        if (std::isnan(v.f)) throw PyError("ValueError", "int(nan)");
        if (std::isinf(v.f)) throw PyError("OverflowError", "int(inf)");
        return static_cast<long long>(std::trunc(v.f));
    case Value::Str: {
        auto i = pyInt(v.s);
        if (!i) throw PyError("ValueError", "int()");
        return *i;
    }
    default: throw PyError("TypeError", "int()");
    }
}

double toFloat(const Value &v) {
    if (v.isNumber()) return v.number();
    if (v.type == Value::Str) {
        auto f = pyFloat(v.s);
        if (!f) throw PyError("ValueError", "float()");
        return *f;
    }
    throw PyError("TypeError", "float()");
}

}  // namespace neb
