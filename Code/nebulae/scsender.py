# Courtesy of hecanjob/pippi.pd
# the only documentation find for OSCServer https://www.acmesystems.it/touchosc 

import sys
import threading
import time
import logging

from classlogger import ClassLogger

sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

from OSC import OSCClient, OSCMessage, OSCServer


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
        self._connected = False

        self._listener_thread = None
        self._running = False

        self.synthIsUpLock = threading.Lock()
        self.sclangIsReadyLock = threading.Lock()
        self.synthIsUp = False
        self.sclangIsReady = False

    # -------------------------
    # Synth status
    # -------------------------

    def scdFileLoaded(self, addr, tags, data, source):
        with self.synthIsUpLock:
            self.log.debug("synth is up!")
            self.synthIsUp = True

    def synthIsUpStatus(self):
        with self.synthIsUpLock:
            self.log.debug("synthIsUpStatus=%s", self.synthIsUp)
            return self.synthIsUp

    def setSynthIsDown(self):
        self.values = {} #we know this is called in the main thread so no worries.
        with self.synthIsUpLock:
            self.log.debug("SET SYNTH TO DOWN!!!")
            self.synthIsUp = False

    def setSclangHandshake(self, addr, tags, data, source):
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
            self.client = OSCClient()
            self.client.connect((self.rhost, self.rPort))
            self._connected = True
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
            self.log.debug("OSC sending: %s %s", addr,value)

            self.values[what] = value
            msg = OSCMessage()
            msg.setAddress(addr)
            msg.append(value)

            if self._connected and self.client:
                self.client.send(msg)
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
        while self._running:
            #self.log.debug("_listen_loop: waiting for request")
            try:
                self.server.handle_request()
            except Exception as e:
                self.log.error("OSC handle_request error: %s", e)
                time.sleep(1)  # avoid CPU hogging
        self.log.debug("_listen_loop: stopped listening!!!!")

    def _no_dispatch(self, addr, tags, data, source):
        try:
            self.log.error("DISPATCH CALLED MISSED!!!: %s", addr)
        except Exception as e:
            self.log.error("Error in OSC callback for %s, error: %s", addr, e)

    # -------------------------
    # Callback registration
    # -------------------------

    def addResiver(self, address, callback):
        try:
            if self.server is None:
                self.log.debug("OSCServer create")
                self.server = OSCServer((self.shost, self.sPort))
                self.server.addDefaultHandlers()
                self.server.addMsgHandler('default', self._no_dispatch)
                self.log.debug("OSCServer default")
            self.log.debug("OSCServer add_listener")
            self.server.addMsgHandler(address, callback)
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
                self.client.close()
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
                #self._running is the Thread run. If server does not close it is still a problem. Cannot be open.
                self._running = False 
                self.server.close()
                self.server = None
            except Exception as e:
                self.log.error("Error closing OSC server: %s", e)
        else:
            self.log.info("OSC server is None!!!")
