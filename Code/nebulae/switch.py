import nebio

# GPIO input with pull-up (gates and encoder clicks). The pin is sampled by
# nebio (C++); update() reads it from the current input snapshot.
class Switch(object):
    def __init__(self, pin):
        self.pin = pin
        nebio.inputs()
        self.prev_state = 1
        self.current_state = 1

    def update(self):
        self.prev_state = self.current_state
        self.current_state = nebio.gpio_level(self.pin)

    def risingEdge(self):
        if self.current_state == 0 and self.prev_state == 1:
            return True
        else:
            return False

    def fallingEdge(self):
        if self.current_state == 1 and self.prev_state == 0:
            return True
        else:
            return False

    def state(self):
        if self.current_state == 1:
            return False
        else:
            return True

    def prevState(self):
        if self.prev_state == 1:
            return False
        else:
            return True
