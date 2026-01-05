# Import SPI library (for hardware SPI) and MCP3008 library.
from controlhandler import ControlHandler

# Main Class. Holds all ControlChannels
class SCControlHandler(ControlHandler):

    def __init__(self, *args, **kwargs):
        super(SCControlHandler, self).__init__(*args, **kwargs)