// Unit tests of the port's Python-semantics helpers (pyvalue.h) against
// values taken from CPython 3.14. Scenario tests (compare.py) cover the classes.
#include <cmath>
#include <cstdio>
#include <string>

#include "pyvalue.h"

using namespace neb;

static int failures = 0;

#define CHECK(cond)                                                   \
    do {                                                              \
        if (!(cond)) {                                                \
            std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            ++failures;                                               \
        }                                                             \
    } while (0)

#define CHECK_EQ(a, b)                                                                          \
    do {                                                                                        \
        auto va = (a);                                                                          \
        auto vb = (b);                                                                          \
        if (!(va == vb)) {                                                                      \
            std::printf("FAIL %s:%d: %s == %s\n", __FILE__, __LINE__, #a, #b);                  \
            ++failures;                                                                         \
        }                                                                                       \
    } while (0)

int main() {
    // repr(float)
    CHECK_EQ(pyRepr(0.1), std::string("0.1"));
    CHECK_EQ(pyRepr(1.0), std::string("1.0"));
    CHECK_EQ(pyRepr(-0.0), std::string("-0.0"));
    CHECK_EQ(pyRepr(1e16), std::string("1e+16"));
    CHECK_EQ(pyRepr(1234567890123456.0), std::string("1234567890123456.0"));
    CHECK_EQ(pyRepr(0.0001), std::string("0.0001"));
    CHECK_EQ(pyRepr(0.00001), std::string("1e-05"));
    CHECK_EQ(pyRepr(1.5e-7), std::string("1.5e-07"));
    CHECK_EQ(pyRepr(123.456), std::string("123.456"));
    CHECK_EQ(pyRepr(1.0 / 3.0), std::string("0.3333333333333333"));
    CHECK_EQ(pyRepr(2.0 / 3.0), std::string("0.6666666666666666"));
    CHECK_EQ(pyRepr(1e300 * 10), std::string("1e+301"));
    CHECK_EQ(pyRepr(INFINITY), std::string("inf"));
    CHECK_EQ(pyRepr(NAN), std::string("nan"));
    CHECK_EQ(pyRepr(5e-324), std::string("5e-324"));
    CHECK_EQ(pyRepr(0.1 + 0.2), std::string("0.30000000000000004"));

    // round(x, n): ties to even on the exact binary value
    CHECK_EQ(pyRound(2.675, 2), 2.67);  // 2.675 is 2.67499999...
    CHECK_EQ(pyRound(0.125, 2), 0.12);
    CHECK_EQ(pyRound(0.375, 2), 0.38);
    CHECK_EQ(pyRound(1.00005, 4), 1.0001);
    CHECK_EQ(pyRound(-0.00004, 4), -0.0);
    CHECK(std::signbit(pyRound(-0.00004, 4)));
    CHECK_EQ(pyRound0(0.5), 0.0);
    CHECK_EQ(pyRound0(1.5), 2.0);
    CHECK_EQ(pyRound0(2.5), 2.0);
    CHECK_EQ(pyRound0(-2.5), -2.0);
    CHECK(!std::signbit(pyRound0(-0.2)));

    // float(text)
    CHECK(pyFloat(" 1.5\n").value() == 1.5);
    CHECK(pyFloat("1_000.5").value() == 1000.5);
    CHECK(!pyFloat("1__0"));
    CHECK(!pyFloat("_1"));
    CHECK(!pyFloat("1._5"));
    CHECK(pyFloat(".5").value() == 0.5);
    CHECK(pyFloat("5.").value() == 5.0);
    CHECK(!pyFloat("."));
    CHECK(!pyFloat("1e"));
    CHECK(pyFloat("1E+2").value() == 100.0);
    CHECK(std::isinf(pyFloat("-Infinity").value()));
    CHECK(std::isnan(pyFloat("nan").value()));
    CHECK(!pyFloat("0x10"));
    CHECK(!pyFloat(""));
    CHECK(!pyFloat("1 2"));

    // int(text)
    CHECK(pyInt(" 42 ").value() == 42);
    CHECK(pyInt("007").value() == 7);
    CHECK(pyInt("-1_000").value() == -1000);
    CHECK(!pyInt("5.0"));
    CHECK(!pyInt("1e3"));
    CHECK(!pyInt(""));
    CHECK(pyInt("99999999999999999999999").value() == 9223372036854775807LL);

    // == and arithmetic keep Python's types
    CHECK(I(1) == F(1.0));
    CHECK(Value::boolean(true) == I(1));
    CHECK(!(Value::str("1") == I(1)));
    CHECK(Value() == Value());
    CHECK_EQ(add(I(1), I(2)).type, Value::Int);
    CHECK_EQ(add(I(1), F(2)).type, Value::Float);
    CHECK_EQ(sub(Value::boolean(true), I(1)).type, Value::Int);
    CHECK_EQ(roundTo(I(3), 4).type, Value::Int);
    CHECK_EQ(roundTo(F(0.12345), 4).f, 0.1235);  // 0.12345 is 0.12345000000000000417...
    CHECK_EQ(toInt(F(-2.9)), -2LL);
    CHECK_EQ(pyStr(F(0.5)), std::string("0.5"));
    CHECK_EQ(pyStr(I(5)), std::string("5"));
    CHECK_EQ(pyStr(Value::boolean(false)), std::string("False"));
    CHECK_EQ(pyStr(Value::of({Value::str("a"), F(1)})), std::string("['a', 1.0]"));

    // str.strip() / rstrip(): Unicode spaces and \x1c-\x1f too, not other bytes
    CHECK_EQ(strip(" \t\x1c" "a b" "\x1f\r\n"), std::string("a b"));
    CHECK_EQ(strip("\xc2\xa0" "0.5" "\xe2\x80\x83\xe3\x80\x80"), std::string("0.5"));
    CHECK_EQ(strip("\xc2\xa0\xc2\x85\xe2\x80\xa8"), std::string(""));
    CHECK_EQ(strip("\xc3\xa5"), std::string("\xc3\xa5"));        // å stays
    CHECK_EQ(strip("\xe2\x80\x8b" "x"), std::string("\xe2\x80\x8b" "x"));  // zero width space is no space
    CHECK_EQ(pyRstrip(" a\xc2\xa0 "), std::string(" a"));
    CHECK_EQ(pyIndent("\xc2\xa0 \tx "), size_t(3));
    CHECK(pyFloat("\xc2\xa0" "1.5\n").value() == 1.5);
    CHECK(pyInt("\xe3\x80\x80" "42\r\n").value() == 42);

    std::printf("%s (%d failures)\n", failures ? "FAILED" : "all unit tests passed", failures);
    return failures ? 1 : 0;
}
