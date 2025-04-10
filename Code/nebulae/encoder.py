# encoder.py

import RPi.GPIO as GPIO
import time
import math
import threading
from collections import deque

class Encoder:
    _valid_sequences = {
        (0, 1, 3, 2): +1,
        (1, 3, 2, 0): +1,
        (3, 2, 0, 1): +1,
        (2, 0, 1, 3): +1,

        (0, 2, 3, 1): -1,
        (2, 3, 1, 0): -1,
        (3, 1, 0, 2): -1,
        (1, 0, 2, 3): -1,
    }

    def __init__(self, pin_a, pin_b):
        self.pin_a = pin_b
        self.pin_b = pin_a

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.steps = 0
        self._state_history = deque(maxlen=4)


        initial_state = self.rotation_state()
        self._state_history.append(initial_state)

    def rotation_state(self):
        a = GPIO.input(self.pin_a)
        b = GPIO.input(self.pin_b)
        return a | (b << 1)

    def update(self):
        state = self.rotation_state()
        if self._state_history[-1] == state:
            return
        self._state_history.append(state)
        if len(self._state_history) == 4:
            seq = tuple(self._state_history)
            if seq in self._valid_sequences:
                self.steps += self._valid_sequences[seq]
            self._state_history.popleft()

    def _isr(self, channel):
        now = time.time()
        if now - self._last_time < 0.001:
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