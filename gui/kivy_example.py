from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Color, Ellipse, Line
from kivy.core.window import Window
from kivy.properties import NumericProperty
from pythonosc.udp_client import SimpleUDPClient
import math

client = SimpleUDPClient("127.0.0.1", 3000)

class Knob(Widget):
    value = NumericProperty(0.0)

    def __init__(self, osc_address="/neb/pitch", label="knob", **kwargs):
        super().__init__(**kwargs)
        self.address = osc_address
        self.label_text = label
        self.dragging = False
        self.start_y = 0
        self.start_value = 0.0

        # Canvas drawing
        with self.canvas:
            Color(0.2, 0.6, 0.9)
            self.circle = Ellipse(pos=self.pos, size=(50*2, 50*2))
            Color(1, 1, 1)
            self.line = Line(circle=(self.center_x, self.center_y, 50, 0, 0), width=2)

        self.bind(pos=self.update_graphics, size=self.update_graphics, value=self.update_graphics)

    def update_graphics(self, *args):
        radius = min(self.width, self.height) / 2
        self.circle.pos = (self.center_x - radius, self.center_y - radius)
        self.circle.size = (radius*2, radius*2)
        self.line.circle = (self.center_x, self.center_y, radius, 0, self.value*360)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
            self.start_y = touch.pos[1]
            self.start_value = self.value
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.dragging:
            dy = self.start_y - touch.pos[1]
            factor = 0.005
            fine_scale = max(0.05, min(1.0, 200 / (abs(dy)+1)))
            delta = dy * factor * fine_scale
            new_val = self.start_value + delta
            self.value = max(0.0, min(1.0, new_val))
            client.send_message(self.address, self.value)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.dragging:
            self.dragging = False
            return True
        return super().on_touch_up(touch)

class KnobWithLabel(Widget):
    """Helper class to combine a knob with its title and value labels"""
    def __init__(self, osc_address, label_text, size=(100,100), pos=(0,0), **kwargs):
        super().__init__(**kwargs)
        self.knob = Knob(osc_address=osc_address, size=size, pos=pos)
        self.add_widget(self.knob)

        # Title label
        self.title_label = Label(text=label_text, size_hint=(None,None))
        self.value_label = Label(text=f"{self.knob.value:.2f}", size_hint=(None,None))
        self.add_widget(self.title_label)
        self.add_widget(self.value_label)

        # Bind updates
        self.knob.bind(pos=self.update_labels, size=self.update_labels, value=self.update_value)
        self.update_labels()

    def update_labels(self, *args):
        self.title_label.text = self.title_label.text
        self.title_label.texture_update()
        self.title_label.pos = (self.knob.center_x - self.title_label.width/2, self.knob.top + 5)

        self.value_label.texture_update()
        self.value_label.pos = (self.knob.center_x - self.value_label.width/2, self.knob.y - 20)

    def update_value(self, *args):
        self.value_label.text = f"{self.knob.value:.2f}"

class KnobApp(App):
    def build(self):
        Window.size = (400, 400)
        root = Widget()
        # Example knobs
        knob1 = KnobWithLabel(osc_address="/neb/pitch", label_text="pitch", size=(100,100), pos=(50,200))
        knob2 = KnobWithLabel(osc_address="/neb/speed", label_text="speed", size=(120,120), pos=(200,200))
        root.add_widget(knob1)
        root.add_widget(knob2)
        return root

if __name__ == "__main__":
    KnobApp().run()

