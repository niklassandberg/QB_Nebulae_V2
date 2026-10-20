# OSC communication with sclang. The OSC sender and listener run inside the
# nebio C++ library (liblo); this class keeps the old ScSend interface.
#   send:   127.0.0.1:3010  "/neb/<name> value"
#   listen: :3011           "/sc/up", "/neb/ready"

import time

import nebio
from classlogger import ClassLogger


class ScSend(object):

    rPort = 3010  # SC server port
    sPort = 3011  # this server port

    # OSC addresses handled inside nebio; anything else is logged there.
    _handled = ('/sc/up', '/neb/ready')

    def __init__(self):
        self.log = ClassLogger.loggerSetup(self)
        self.lib = nebio.lib()

    # -------------------------
    # Synth status
    # -------------------------

    def synthIsUpStatus(self):
        status = self.lib.nebio_sc_synth_is_up() != 0
        self.log.debug("synthIsUpStatus=%s", status)
        return status

    def waitSynthIsUp(self, timeout):
        """True as soon as sclang sent /sc/up, False after timeout seconds."""
        end = time.time() + timeout
        while True:
            if self.lib.nebio_sc_synth_is_up():
                return True
            if time.time() >= end:
                return False
            time.sleep(0.01)

    def setSynthIsDown(self):
        self.log.debug("SET SYNTH TO DOWN!!!")
        self.lib.nebio_sc_set_synth_down()
        nebio.sc_forget_sent()

    def pingLoaded(self):
        if self.lib.nebio_sc_sender_open():
            self.log.debug("sending /neb/hasbeenloaded ping")
            self.lib.nebio_sc_send_path_int(b'/neb/hasbeenloaded', 0)

    def sclangHandshakeStatus(self):
        status = self.lib.nebio_sc_handshake() != 0
        self.log.debug("sclangHandshakeStatus=%s", status)
        return status

    def zeroSclangHandshake(self):
        self.log.debug("sclang handshake zero!")
        self.lib.nebio_sc_zero_handshake()

    # -------------------------
    # Sending
    # -------------------------

    def connectSender(self):
        if self.lib.nebio_sc_sender_open():
            self.log.info("No need to connect, is connected")
            return
        self.log.info("Connecting")
        if self.lib.nebio_sc_open_sender() == 0:
            self.log.info("Sending to 127.0.0.1:%s", self.rPort)
        else:
            self.log.error("Connection failed: %s", nebio.last_error())

    def clear(self):
        self.lib.nebio_sc_clear_cache()
        nebio.sc_forget_sent()

    def send(self, what, value):
        # Only changed values are sent (checked in nebio).
        nebio.sc_send(what, value)

    # -------------------------
    # Receiving
    # -------------------------

    def startListener(self):
        if self.lib.nebio_sc_listener_running():
            return True
        if self.lib.nebio_sc_start_listener() == 0:
            self.log.info("Listening for OSC on port %s", self.sPort)
            return True
        self.log.error("Failed to start OSC listener: %s", nebio.last_error())
        return False

    def addResiver(self, address, callback):
        # /sc/up and /neb/ready are handled inside nebio and read through
        # synthIsUpStatus()/sclangHandshakeStatus(); callbacks are not used.
        if address not in self._handled:
            self.log.error("OSC address %s is not handled by nebio", address)

    # -------------------------
    # Shutdown
    # -------------------------

    def close(self):
        self.log.info("Closing OSC server and client!!!!")
        self.close_client()
        self.close_server()

    def is_connected(self):
        return bool(self.lib.nebio_sc_sender_open() or self.lib.nebio_sc_listener_running())

    def close_client(self):
        if self.lib.nebio_sc_sender_open():
            self.log.info("Closing OSCclient")
            self.lib.nebio_sc_close_sender()
        else:
            self.log.info("OSC client is None!!!")

    def close_server(self):
        if self.lib.nebio_sc_listener_running():
            self.log.info("Closing OSC server")
            self.lib.nebio_sc_stop_listener()
        else:
            self.log.info("OSC server is None!!!")
