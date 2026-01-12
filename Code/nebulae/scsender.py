# Courtesy of hecanjob/pippi.pd
import sys
import threading
import time
import logging

from classlogger import ClassLogger

sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

from OSC import OSCClient, OSCMessage, OSCServer


class ScSend(object):

    rhost = '127.0.0.1'
    rPort = 3010  # SC server port
    sPort = 3011  # this server port

    def __init__(self):
        # Logger FIRST
        self.log = ClassLogger.loggerSetup(self)

        # Instance state (not class variables!)
        self.values = {}
        self.callbacks = {}
        self.default_callback = None

        self.client = None
        self.server = None
        self.connected = False

        self._listener_thread = None
        self._running = False

        self.synthIsUpLock = threading.Lock()
        self.synthIsUp = False

        self.connect()

    # -------------------------
    # Synth status
    # -------------------------

    def on_sc_up(self, addr, data, source):
        with self.synthIsUpLock:
            self.log.debug(
                "on_sc_up called [ScSend id=%s, synthIsUp=%s]", 
                id(self), self.synthIsUp
            )
            self.log.debug("synth is up!")
            self.synthIsUp = True

    def synthIsUpStatus(self):
        with self.synthIsUpLock:
            self.log.debug(
                "synthIsUpStatus called [ScSend id=%s, synthIsUp=%s]", 
                id(self), self.synthIsUp
            )
            return self.synthIsUp

    def setSynthIsDown(self):
        with self.synthIsUpLock:
            self.log.debug("SET SYNTH TO DOWN!!!")
            self.synthIsUp = False

    # -------------------------
    # Sending
    # -------------------------

    def connect(self):
        if self.connected:
            return

        self.log.info("Connecting")
        try:
            self.client = OSCClient()
            self.client.connect((self.rhost, self.rPort))
            self.connected = True
            self.log.info(
                "Sending to %s:%s", self.rhost, self.rPort)
        except Exception as e:
            self.log.error("Connection failed: %s", e)

    def clear(self):
        self.values = {}

    def send(self, what, value):
        try:
            if what in self.values and self.values[what] == value:
                return

            addr = "/neb/" + what
            self.log.debug("OSC sending: %s", addr)

            self.values[what] = value
            msg = OSCMessage()
            msg.setAddress(addr)
            msg.append(value)

            if self.connected and self.client:
                self.client.send(msg)
        except Exception as e:
            self.log.error("Could not send to: %s", e)

    # -------------------------
    # Receiving
    # -------------------------

    def start_listener(self):
        if self._running:
            return True

        try:
            self.server = OSCServer((self.rhost, self.sPort))
            self.server.addDefaultHandlers()
            self.server.addMsgHandler('default', self._dispatch)

            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop)
            self._listener_thread.daemon = True
            self._listener_thread.start()

            self.log.info("Listening for OSC on port %s", self.sPort)
            return True

        except Exception as e:
            self.log.error("Failed to start OSC listener: %s", e)
            self.close_server()
            return False

    def _listen_loop(self):
        while self._running:
            try:
                self.server.handle_request()
            except Exception as e:
                self.log.error("OSC handle_request error: %s", e)
            time.sleep(0.01)  # avoid CPU hogging

    def _dispatch(self, addr, tags, data, source):
        try:
            self.log.debug("DISPATCH CALLED: %s", addr)

            if addr in self.callbacks:
                self._print_osc_debug(
                    addr, tags, data, source, "registered callback")
                self.callbacks[addr](addr, data, source)

            elif self.default_callback:
                self._print_osc_debug(
                    addr, tags, data, source, "default callback")
                self.default_callback(addr, data, source)

        except Exception as e:
            self.log.error("Error in OSC callback for %s, error: %s", addr, e)

    def _print_osc_debug(self, addr, tags, data, source, which_callback):
        self.log.debug(
            "which_callback(%s), addr(%s), tags(%s), data(%s), source(%s)",
            which_callback, addr, tags, data, source
        )

    # -------------------------
    # Callback registration
    # -------------------------

    def add_listener(self, address, callback):
        """
        address: OSC address string (e.g. '/neb/foo')
        callback: function(addr, data, source)
        """
        self.callbacks[address] = callback

    def set_default_listener(self, callback):
        self.default_callback = callback

    # -------------------------
    # Shutdown
    # -------------------------

    def close(self):
        self.log.info("Closing OSC server and client!!!!")
        self.close_client()
        self.close_server()

    def is_connected(self):
        return self.connected

    def close_client(self):
        self.connected = False
        if self.client is not None:
            try:
                self.log.info("Closing OSCclient")
                self.client.close()
            except Exception as e:
                self.log.error("Error closing OSC client: %s", e)
        else:
            self.log.info("OSC client is None!!!")
        self.client = None

    def close_server(self):
        self._running = False
        if self.server is not None:
            try:
                self.log.info("Closing OSC server")
                self.server.close()
            except Exception as e:
                self.log.error("Error closing OSC server: %s", e)
        else:
            self.log.info("OSC server is None!!!")
        self.server = None
