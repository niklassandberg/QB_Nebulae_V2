# Courtesy of hecanjob/pippi.pd
# the only documentation find for OSCServer https://www.acmesystems.it/touchosc

import threading
import time

from classlogger import ClassLogger

from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer


class ScSend(object):

    rhost = '127.0.0.1'
    shost = '0.0.0.0'
    rPort = 3010  # SC server port
    sPort = 3011  # this server port

    def __init__(self):
        # Logger FIRST
        self.log = ClassLogger.loggerSetup(self)

        # Instance state (not class variables!)
        self.values = {}

        self.client = None
        self.server = None
        self.dispatcher = None
        self._connected = False

        self._listener_thread = None
        self._running = False

        self.synthIsUpLock = threading.Lock()
        self.sclangIsReadyLock = threading.Lock()
        self.synthIsUp = False
        self.sclangIsReady = False
        self.synthIsUpEvent = threading.Event()

    # -------------------------
    # Synth status
    # -------------------------

    def scdFileLoaded(self, addr, *args):
        with self.synthIsUpLock:
            self.log.debug("synth is up!")
            self.synthIsUp = True
        self.synthIsUpEvent.set()

    def synthIsUpStatus(self):
        with self.synthIsUpLock:
            self.log.debug("synthIsUpStatus=%s", self.synthIsUp)
            return self.synthIsUp

    def setSynthIsDown(self):
        self.values = {} #we know this is called in the main thread so no worries.
        with self.synthIsUpLock:
            self.log.debug("SET SYNTH TO DOWN!!!")
            self.synthIsUp = False
        self.synthIsUpEvent.clear()

    def pingLoaded(self):
        if self._connected and self.client:
            self.log.debug("sending /neb/hasbeenloaded ping")
            self.client.send_message('/neb/hasbeenloaded', 0)

    def setSclangHandshake(self, addr, *args):
        with self.sclangIsReadyLock:
            self.log.debug("sclang handshake!")
            self.sclangIsReady = True

    def sclangHandshakeStatus(self):
        with self.sclangIsReadyLock:
            self.log.debug("sclangHandshakeStatus=%s", self.sclangIsReady)
            return self.sclangIsReady

    def zeroSclangHandshake(self):
        with self.sclangIsReadyLock:
            self.log.debug("sclang handshake zero!")
            self.sclangIsReady = False

    # -------------------------
    # Sending
    # -------------------------

    def connectSender(self):
        if self._connected:
            self.log.info("No need to connect, is connected")
            return

        self.log.info("Connecting")
        try:
            self.client = SimpleUDPClient(self.rhost, self.rPort)
            self._connected = True
            self.log.info("Sending to %s:%s", self.rhost, self.rPort)
        except Exception as e:
            self.log.error("Connection failed: %s", e)

    def clear(self):
        self.values = {}

    def send(self, what, value):
        try:
            if what in self.values and self.values[what] == value:
                return

            addr = "/neb/" + what
            self.log.debug("OSC sending: %s %s", addr, value)

            self.values[what] = value
            if self._connected and self.client:
                self.client.send_message(addr, value)
        except Exception as e:
            self.log.error("Could not send to: %s", e)

    # -------------------------
    # Receiving
    # -------------------------

    def startListener(self):
        if self._running:
            return True
        self._running = True

        try:
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
        try:
            self.server.serve_forever()
        except Exception as e:
            self.log.error("OSC server error: %s", e)
        self.log.debug("_listen_loop: stopped listening!!!!")

    def _no_dispatch(self, addr, *args):
        try:
            self.log.error("DISPATCH CALLED MISSED!!!: %s", addr)
        except Exception as e:
            self.log.error("Error in OSC callback for %s, error: %s", addr, e)

    # -------------------------
    # Callback registration
    # -------------------------

    def addResiver(self, address, callback):
        try:
            if self.dispatcher is None:
                self.log.debug("OSCServer create dispatcher")
                self.dispatcher = Dispatcher()
                self.dispatcher.set_default_handler(self._no_dispatch)
            self.log.debug("OSCServer add_listener")
            self.dispatcher.map(address, callback)
            if self.server is None:
                self.server = ThreadingOSCUDPServer((self.shost, self.sPort), self.dispatcher)
                self.log.debug("OSCServer created")
        except Exception as e:
            self.log.error("Failed add_listener: %s", e)

    # -------------------------
    # Shutdown
    # -------------------------

    def close(self):
        self.log.info("Closing OSC server and client!!!!")
        self.close_client()
        self.close_server()

    def is_connected(self):
        return self._connected or self._running

    def close_client(self):
        if self.client is not None:
            try:
                self.log.info("Closing OSCclient")
                self._connected = False
                self.client = None
            except Exception as e:
                self.log.error("Error closing OSC client: %s", e)
        else:
            self.log.info("OSC client is None!!!")

    def close_server(self):
        if self.server is not None:
            try:
                self.log.info("Closing OSC server")
                self._running = False
                self.server.shutdown()
                self.server = None
                self.dispatcher = None
            except Exception as e:
                self.log.error("Error closing OSC server: %s", e)
        else:
            self.log.info("OSC server is None!!!")
