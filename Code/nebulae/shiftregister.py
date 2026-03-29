# shiftregister.py
# Stephen Hensley
# Python Class for Polling CD4021 Input Shift Register

import RPi.GPIO as GPIO
import time

PIN_NEXT = 7
PIN_SOURCE_GATE = 6
PIN_SOURCE = 5
PIN_FREEZE = 4
PIN_RECORD = 3
PIN_RESET = 0

DEBOUNCE_COUNT = 3

class ShiftRegister(object):
    def __init__(self):
        self.delay = 10
        self.delay_count = self.delay
        self.dataPin = 5
        self.latchPin = 15
        self.clkPin = 14
        GPIO.setup(self.dataPin, GPIO.IN)
        GPIO.setup(self.clkPin, GPIO.OUT)
        GPIO.setup(self.latchPin, GPIO.OUT)
        self.values = [-1, -1, -1, -1, -1, -1, -1, -1]
        self.prevValues = [-1, -1, -1, -1, -1, -1, -1, -1]
        self.rawValues = [-1, -1, -1, -1, -1, -1, -1, -1]
        self.stableCount = [0, 0, 0, 0, 0, 0, 0, 0]

    def update(self):
        for i in range(0, 8):
            self.prevValues[i] = self.values[i]
        GPIO.output(self.latchPin, 1)
        GPIO.output(self.latchPin, 0)
        raw = [0] * 8
        for i in range(0, 8):
            GPIO.output(self.clkPin, 0)
            raw[i] = GPIO.input(self.dataPin)
            GPIO.output(self.clkPin, 1)
        for i in range(0, 8):
            if raw[i] == self.rawValues[i]:
                self.stableCount[i] = min(self.stableCount[i] + 1, DEBOUNCE_COUNT)
            else:
                self.rawValues[i] = raw[i]
                self.stableCount[i] = 0
            if self.stableCount[i] >= DEBOUNCE_COUNT:
                self.values[i] = raw[i]
    
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
				
