#include "inputs.h"

#include "nebio.h"

namespace neb {

Switch::Switch(int pin) : pin_(pin) { nebio::inputs(); }

void Switch::update() {
    prev_ = current_;
    current_ = nebio::gpio_level(pin_);
}

ShiftRegister::ShiftRegister() { nebio::inputs(); }

void ShiftRegister::update() {
    for (int i = 0; i < 8; ++i) prev_[i] = values_[i];
    nebio::snapshot();
    int bits = nebio::sr_bits();
    for (int i = 0; i < 8; ++i) values_[i] = (bits >> i) & 1;
}

int ShiftRegister::at(const int (&v)[8], int index) {
    if (index < 0) index += 8;
    if (index < 0 || index >= 8) throw PyError("IndexError", "list index out of range");
    return v[index];
}

}  // namespace neb
