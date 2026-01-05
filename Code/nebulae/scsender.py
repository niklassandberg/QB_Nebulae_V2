# Courtesy of hecanjob/pippi.pd
import sys
import os
import threading
import time
import logging

sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

from OSC import OSCClient, OSCMessage, OSCServer

class ScSend(object):

    values = {}
    rhost = '127.0.0.1'
    rPort = 3010 #SC server port
    sPort = 3011 #this server port

    client = None
    server = None
    connected = False

    _listener_thread = None
    _running = False

    callbacks = {}      # address -> function
    default_callback = None

    def __init__(self):
        self.connect()
        self.synthIsUpLock = threading.Lock()
        self.synthIsUp = False
        self.loogerSetup()

    def loogerSetup(self):
        # Dedicated logger for OSC
        self.osc_logger = logging.getLogger("OSC")
        self.osc_logger.setLevel(logging.DEBUG) 

        # File handler
        fh = logging.FileHandler("/tmp/osc_only.log")
        fh.setLevel(logging.DEBUG)

        # Formatter
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        fh.setFormatter(formatter)

        self.osc_logger.addHandler(fh)

    def on_sc_up(self, addr, data, source):
        with self.synthIsUpLock:
            self.osc_logger.debug('NOW SYNTH IS UP!!!!!!!!!')
            self.synthIsUp = True

    def synthIsUpStatus(self):
        with self.synthIsUpLock:
            return self.synthIsUp

    # -------------------------
    # Sending
    # -------------------------

    def connect(self):
        if self.connected:
            return

        print 'connecting to sc'
        try:
            self.client = OSCClient()
            self.client.connect((self.rhost, self.rPort))
            self.connected = True
            print 'Sending to SC on port {} : {}'.format(
                self.rhost, self.rPort)
        except:
            print 'Connection failed - open SC'

    def clear(self):
        self.values = {}

    def send(self, what, value):
        try:
            if what in self.values and self.values[what] == value:
                return

            addr = "/neb/" + what
            print "SC OSC sending:", addr

            self.values[what] = value
            msg = OSCMessage()
            msg.setAddress(addr)
            msg.append(value)

            if self.connected:
                self.client.send(msg)
        except:
            print 'Could not send to SC. Did you open a connection?'

    # -------------------------
    # Receiving
    # -------------------------

    def start_listener(self):
        
        if self._running:
            return True
        
        try:
            self.server = OSCServer(
                (self.rhost, self.sPort))
            self.server.addDefaultHandlers()

            self.server.addMsgHandler('default', self._dispatch)

            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop)
            self._listener_thread.daemon = True
            self._listener_thread.start()

            print 'Listening for SC OSC on port', self.sPort

            return True
        except:
            print 'Failed to start OSC listener'
            
        return False
 
    def _listen_loop(self):
        while self._running:
            try:
                self.server.handle_request()
            except:
                pass
            time.sleep(0.01) #low, to not hog CPU. Maybe set higher later if needed.

    def _dispatch(self, addr, tags, data, source):
        try:
            self.osc_logger.debug("DISPATCH CALLED: %s", addr)
            if addr in self.callbacks:
                self.print_osc_debug(addr, tags, data, source, "registered callback")
                self.callbacks[addr](addr, data, source)
            elif self.default_callback:
                self.print_osc_debug(addr, tags, data, source, "default callback")
                self.default_callback(addr, data, source)
        except:
            logging.error('Error in OSC callback for %s', addr)

    def print_osc_debug(self, addr, tags, data, source, which_callback):
        self.osc_logger.debug("which_callback(%s), addr(%s), tags(%s), data(%s), source(%s)", which_callback, addr, tags, data, source)
        

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
        """
        Called when no address-specific callback exists
        """
        self.default_callback = callback

    # -------------------------
    # Shutdown
    # -------------------------

    def close(self):
        self._running = False
        self.connected = False
        with self.synthIsUpLock:
            self.synthIsUp = False
        try:
            if self.client:
                print 'Closing client to SC'
                self.client.close()
                self.client = None
            else:
                print 'No SC client to close!!!'
        except:
            print 'except closing client to SC'

        try:
            if self.server:
                print 'Closing server to SC'
                self.server.close()
                self.server = None
            else:
                print 'No SC server to close!!!'
        except:
            print 'except closing server to SC'

    def is_connected(self):
        return self.connected
