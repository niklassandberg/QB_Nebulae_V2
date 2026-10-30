// gpiomem.h - direct GPIO register access through /dev/gpiomem (no syscall
// per read/write). Used only for the fast input path (shift register clock and
// latch, reading input levels); libgpiod still owns the lines and sets their
// direction, pulls and edge detection.
//
// Works on BCM2835/2836/2837 (Pi 1-3, Zero) and BCM2711 (Pi 4): same register
// layout for GPFSEL/GPSET/GPCLR/GPLEV, /dev/gpiomem hides the base address.
// Refuses anything else (e.g. Pi 5, where GPIO lives on the RP1 chip).
//
// Safety: pin functions (GPFSEL) are only read, never written, and only the
// pins in the writable mask can be set or cleared.
#pragma once

#include <cstdint>
#include <string>

namespace nebio {

class GpioMem {
public:
    static GpioMem &instance();

    // Checks the SoC and maps the GPIO registers. Idempotent. false (and
    // lastError) if the board is not supported or /dev/gpiomem is missing.
    bool open();
    bool ok() const { return regs_ != nullptr; }
    const std::string &board() const { return board_; }

    // Function of a pin from GPFSEL: 0 = input, 1 = output, 2-7 = alt. -1 on error.
    int function(unsigned pin) const;

    // GPLEV0: levels of pins 0-31.
    uint32_t levels() const { return regs_[kLev0]; }

    // Only pins in this mask can ever be written (set once, by Inputs).
    void setWritable(uint32_t mask) { writable_ = mask; }
    // Sets the pins in setMask high and those in clearMask low. Pins outside
    // the writable mask are ignored (and logged once).
    void write(uint32_t setMask, uint32_t clearMask);

private:
    GpioMem() = default;
    static constexpr int kFsel0 = 0;   // GPFSEL0, word index
    static constexpr int kSet0 = 7;    // GPSET0  (0x1c)
    static constexpr int kClr0 = 10;   // GPCLR0  (0x28)
    static constexpr int kLev0 = 13;   // GPLEV0  (0x34)

    volatile uint32_t *regs_ = nullptr;
    uint32_t writable_ = 0;
    bool warned_ = false;
    std::string board_;
};

}  // namespace nebio
