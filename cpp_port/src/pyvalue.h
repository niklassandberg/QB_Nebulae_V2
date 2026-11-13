// Python semantics the port needs to give the same results as the originals:
// a value with Python's type (None/bool/int/float/str/list), round(), repr()
// of a float, float()/int() of a text, str().
#pragma once

#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace neb {

struct Value {
    enum Type { None, Bool, Int, Float, Str, List };
    Type type = None;
    bool b = false;
    long long i = 0;
    double f = 0.0;
    std::string s;
    std::vector<Value> list;

    Value() = default;
    static Value none() { return Value(); }
    static Value boolean(bool v) { Value x; x.type = Bool; x.b = v; return x; }
    static Value integer(long long v) { Value x; x.type = Int; x.i = v; return x; }
    static Value real(double v) { Value x; x.type = Float; x.f = v; return x; }
    static Value str(const std::string &v) { Value x; x.type = Str; x.s = v; return x; }
    static Value of(std::vector<Value> v) { Value x; x.type = List; x.list = std::move(v); return x; }

    bool isNone() const { return type == None; }
    bool isNumber() const { return type == Bool || type == Int || type == Float; }
    double number() const;  // bool/int/float as a double
    bool truthy() const;
};

// Python's ==: numbers by value (1 == 1.0 == True), str by text, never str == number.
bool operator==(const Value &a, const Value &b);
inline bool operator!=(const Value &a, const Value &b) { return !(a == b); }

// Exceptions with the Python type name, so a trace shows the same error.
struct PyError : std::runtime_error {
    std::string type;
    PyError(const std::string &t, const std::string &msg) : std::runtime_error(msg), type(t) {}
};

double pyRound(double x, int ndigits);  // round(x, ndigits)
double pyRound0(double x);              // float(round(x)): half to even
std::string pyRepr(double x);           // repr(float)
std::string pyStr(const Value &v);      // str(v)

// float(text) / int(text): nullopt where Python raises ValueError.
std::optional<double> pyFloat(const std::string &text);
std::optional<long long> pyInt(const std::string &text);  // saturates on overflow

std::string strip(const std::string &text);   // str.strip()
std::string pyRstrip(const std::string &text);  // str.rstrip()
size_t pyIndent(const std::string &text);  // leading str.isspace() characters

// Python arithmetic on numbers: int op int stays int, otherwise float.
Value add(const Value &a, const Value &b);
Value sub(const Value &a, const Value &b);
Value mul(const Value &a, const Value &b);
bool lt(const Value &a, const Value &b);
bool gt(const Value &a, const Value &b);
Value roundTo(const Value &v, int ndigits);  // round(v, n): an int stays int
long long toInt(const Value &v);             // int(v); PyError ValueError/TypeError
double toFloat(const Value &v);              // float(v); PyError ValueError/TypeError
inline Value F(double v) { return Value::real(v); }
inline Value I(long long v) { return Value::integer(v); }

}  // namespace neb
