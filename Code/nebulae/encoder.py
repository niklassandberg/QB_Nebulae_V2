# encoder.py
#
# The rotary encoders are polled by nebio (C++) at 1 kHz with the same
# 3-state sequence check that used to live here (VALID_SEQ_3).

import nebio
from classlogger import ClassLogger


class Encoder:

    class Worker(object):
        def __init__(self, pin_a, pin_b):
            self.log = ClassLogger.loggerSetup(self)
            nebio.inputs()
            self.id = nebio.encoder_id(pin_a, pin_b)
            if self.id < 0:
                self.log.error("No nebio encoder on pins %d/%d", pin_a, pin_b)

        def start(self):
            pass

        def stop(self):
            pass

        def get_steps(self):
            if self.id < 0:
                return 0
            return nebio.encoder_steps(self.id)
