// switch.py and shiftregister.py: the GPIO inputs and the CD4021 shift
// register, read from nebio's snapshot.
#pragma once

namespace neb {

// GPIO input with pull-up (gates and encoder clicks).
class Switch {
public:
    explicit Switch(int pin);
    void update();
    bool risingEdge() const { return current_ == 0 && prev_ == 1; }
    bool fallingEdge() const { return current_ == 1 && prev_ == 0; }
    bool state() const { return current_ != 1; }
    bool prevState() const { return prev_ != 1; }
    int pin() const { return pin_; }

private:
    int pin_;
    int prev_ = 1;
    int current_ = 1;
};

constexpr int PIN_NEXT = 7;
constexpr int PIN_SOURCE_GATE = 6;
constexpr int PIN_SOURCE = 5;
constexpr int PIN_FREEZE = 4;
constexpr int PIN_RECORD = 3;
constexpr int PIN_RESET = 0;

// update() takes one snapshot of all inputs, so every channel read in the
// same updateAll() sees the same state.
class ShiftRegister {
public:
    ShiftRegister();
    void update();
    bool risingEdge(int index) const { return at(values_, index) == 1 && at(prev_, index) == 0; }
    bool fallingEdge(int index) const { return at(values_, index) == 0 && at(prev_, index) == 1; }
    bool state(int index) const { return at(values_, index) == 1; }
    bool prevState(int index) const { return at(prev_, index) == 1; }

private:
    static int at(const int (&v)[8], int index);  // Python list index (negative from the end)
    int values_[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
    int prev_[8] = {-1, -1, -1, -1, -1, -1, -1, -1};
};

}  // namespace neb
