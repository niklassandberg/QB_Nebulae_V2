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

MCP3208::MCP3208(int device) : base_(device * 8) {
    nebio::inputs();
    codes_ = nebio::adc_codes();
}

int MCP3208::read_adc(int adc_number) const {
    if (!(0 <= adc_number && adc_number <= 7))
        throw PyError("AssertionError", "ADC number must be a value of 0-7!");
    int k = base_ + adc_number;
    if (k < 0) k += 16;
    if (k < 0 || k >= 16) throw PyError("IndexError", "invalid index");
    return codes_[k];
}

}  // namespace neb
