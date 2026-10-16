# Text messages to Pure Data over TCP ("name value;"), sent by the nebio C++
# library. Open PD with [netreceive 3000]. Keeps the old PdSend interface.
import nebio
from classlogger import ClassLogger


class PdSend(object):
    sport = 3000

    def __init__(self):
        self.log = ClassLogger.loggerSetup(self)
        self.lib = nebio.lib()
        self.warned = False

    # -------------------------
    # Connection
    # -------------------------

    def connect(self):
        # Connects in the background and retries until PD answers or close().
        self.log.info("Connecting to PD")
        self.lib.nebio_pd_connect()

    # -------------------------
    # Sending
    # -------------------------

    def send(self, msgs):
        if not self.lib.nebio_pd_is_connected():
            if not self.warned: # the connect runs in the background, warn once
                self.log.warning("PD socket not connected. Cannot send messages.")
                self.warned = True
            return
        self.warned = False
        data = ''.join(str(msg) + ';' for msg in msgs).encode('utf-8')
        if self.lib.nebio_pd_send(data, len(data)) != 0:
            self.log.error("Could not send to PD: %s", nebio.last_error())

    # -------------------------
    # Utilities
    # -------------------------

    def format(self, target, val):
        """Return a formatted PD message string"""
        return target + ' ' + str(val)

    # -------------------------
    # Shutdown
    # -------------------------

    def close(self):
        if self.lib.nebio_pd_is_connected():
            self.log.info("Closing connection to PD")
        else:
            self.log.warning("No PD client to close.")
        self.lib.nebio_pd_close()

    def is_connected(self):
        return self.lib.nebio_pd_is_connected() != 0
