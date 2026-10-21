# shiftregister.py
# Stephen Hensley
# Python Class for Polling CD4021 Input Shift Register
#
# The register is read and debounced by nebio (C++) at 1 kHz. update() takes
# one snapshot of all inputs, so every channel in the same updateAll() sees
# the same state.

import nebio

PIN_NEXT = 7
PIN_SOURCE_GATE = 6
PIN_SOURCE = 5
PIN_FREEZE = 4
PIN_RECORD = 3
PIN_RESET = 0

class ShiftRegister(object):
    def __init__(self):
        nebio.inputs()
        self.values = [-1, -1, -1, -1, -1, -1, -1, -1]
        self.prevValues = [-1, -1, -1, -1, -1, -1, -1, -1]

    def update(self):
        self.prevValues = self.values
        nebio.snapshot()
        bits = nebio.sr_bits()
        self.values = [(bits >> i) & 1 for i in range(8)]

    def risingEdge(self, index):
        if (self.values[index] == 1 and self.prevValues[index] == 0):
            return True
        else:
            return False

    def fallingEdge(self, index):
        if (self.values[index] == 0 and self.prevValues[index] == 1):
            return True
        else:
            return False

    def state(self, index):
        if self.values[index] == 1:
            return True
        else:
            return False

    def prevState(self, index):
        if self.prevValues[index] == 1:
            return True
        else:
            return False
