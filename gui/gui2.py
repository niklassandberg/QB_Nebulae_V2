from dearpygui import dearpygui as dpg
from pythonosc.udp_client import SimpleUDPClient

client = SimpleUDPClient("127.0.0.1", 3000)

# Knobs: (OSC address, label, x, y, width, height)
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
    # Just scale for OSC sending, keep GUI smooth
    scale = 0.3  # smaller = need more movement for full range
    client.send_message(user_data, app_data * scale)

dpg.create_context()

with dpg.window(label="Nebulae Controls", width=400, height=400):
    for address, label, x, y, w, h in knobs:
        dpg.add_knob_float(
            label=label,
            min_value=0.0,
            max_value=1.0,
            default_value=0.0,
            width=w,
            height=h,
            pos=(x, y),
            callback=knob_callback,
            user_data=address
        )

dpg.create_viewport(title='Nebulae OSC', width=400, height=400)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

