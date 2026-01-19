import sys
import os

nebulae_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../Code/nebulae"))
sys.path.insert(0, nebulae_path) 

from dearpygui import dearpygui as dpg
from pythonosc.udp_client import SimpleUDPClient

#run: py -3 gui.py

from pythonosc import dispatcher, osc_server
import threading
from queue import Queue

osc_queue = Queue()

def osc_sc_up(address, *args):
    print("Synth is up!", flush=True)
    osc_queue.put((address, args))

def start_osc_server():
    disp = dispatcher.Dispatcher()
    disp.map("/sc/up", osc_sc_up)

    server = osc_server.ThreadingOSCUDPServer(
        ("0.0.0.0", 3011),
        disp
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()

start_osc_server()


print("RUNNING UP NOW!", flush=True)

# OSC client setup
client = SimpleUDPClient("127.0.0.1", 3010)

# List of knobs with (OSC address, label, x, y, width, height)
knobs = [
    ("/neb/start", "start", 20, 20, 80, 80),
    ("/neb/speed", "speed", 120, 20, 60, 60),
    ("/neb/size", "size", 220, 20, 100, 100),
    ("/neb/density", "density", 20, 150, 90, 90),
    ("/neb/pitch", "pitch", 120, 150, 70, 70),
    ("/neb/overlap", "overlap", 220, 150, 80, 80),
    ("/neb/blend", "blend", 70, 280, 60, 60),
    ("/neb/windows", "windows", 170, 280, 100, 100)
]

def knob_callback(sender, app_data, user_data):
    """Send the knob value to its OSC address."""
    address = user_data
    client.send_message(address, float(app_data))

dpg.create_context()

# Create main window
with dpg.window(label="Nebulae Controls", width=400, height=400):
    for address, label, x, y, w, h in knobs:
        dpg.add_knob_float(
            label=label,
            min_value=0.0,
            max_value=1.0,
            default_value=0.0,
            callback=knob_callback,
            user_data=address,
            width=w,
            height=h,
            pos=(x, y)
        )

dpg.create_viewport(title='Nebulae OSC', width=400, height=400)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

