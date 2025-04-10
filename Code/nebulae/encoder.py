# encoder.py

import RPi.GPIO as GPIO
import time
import math
import threading

# Clockwise sequence for your encoder: 0 -> 1 -> 3 -> 2 -> 0
SEQ = [0, 1, 3, 2]
SEQ_LEN = len(SEQ)

class Encoder:

    def __init__(self, pin_a, pin_b):
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.steps = 0
        self._seq_index = 0
        self._last_time = time.time()

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def rotation_state(self):
        a_state = GPIO.input(self.pin_a)
        b_state = GPIO.input(self.pin_b)
        r_state = a_state | b_state << 1
        return r_state

    def update(self):
        state = self.rotation_state()
        next_state = SEQ[(self._seq_index + 1) % SEQ_LEN]
        prev_state = SEQ[(self._seq_index - 1) % SEQ_LEN]

        if state == next_state:
            self._seq_index = (self._seq_index + 1) % SEQ_LEN
            if self._seq_index == 0:
                self.steps += 1
        elif state == prev_state:
            self._seq_index = (self._seq_index - 1) % SEQ_LEN
            if self._seq_index == 0:
                self.steps -= 1

    def _isr(self, channel):
        now = time.time()
        if now - self._last_time < 0.001:  # 1ms debounce
            return
        self.update()
        self._last_time = now


    def get_steps(self):
        steps = self.steps
        self.steps = 0
        return steps

    def get_cycles(self, steps_per_cycle=4):
        cycles = self.steps // steps_per_cycle
        self.steps %= steps_per_cycle
        return cycles

    def start(self):
        # Attach ISR to both channels
        GPIO.add_event_detect(self.pin_a, GPIO.BOTH, callback=self._isr)
        GPIO.add_event_detect(self.pin_b, GPIO.BOTH, callback=self._isr)

    def cleanup(self):
        GPIO.remove_event_detect(self.pin_a)
        GPIO.remove_event_detect(self.pin_b)

    class Worker(threading.Thread):
        def __init__(self, pin_a, pin_b):
            threading.Thread.__init__(self)
            self.lock = threading.Lock()
            self.stopping = False
            self.encoder = Encoder(pin_a, pin_b)
            self.daemon = True
            self.delta = 0
            self.delay = 0.001

        def run(self):
            while not self.stopping:
                self.encoder.update()
                time.sleep(self.delay)

        def stop(self):
            self.stopping = True

        def get_steps(self):
            return self.encoder.get_steps()
