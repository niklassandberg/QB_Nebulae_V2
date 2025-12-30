# Courtesy of hecanjob/pippi.pd
import sys
import os
import threading
import time

sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

from OSC import OSCClient, OSCMessage, OSCServer

class ScSend():
    values = {}
    serverhost = 'localhost'
    serverport = 3002 #SC server port
    resieveport = 3003 #this server port

    client = None
    server = None
    connected = False

    _listener_thread = None
    _running = False

    callbacks = {}      # address -> function
    default_callback = None

    def __init__(self):
        self.connect()
        #self.start_listener()

    # -------------------------
    # Sending
    # -------------------------

    def connect(self):
        if self.connected:
            return

        print 'connecting to sc'
        try:
            self.client = OSCClient()
            self.client.connect((self.serverhost, self.serverport))
            self.connected = True
            print 'Sending to SC on port {} : {}'.format(
                self.serverhost, self.serverport)
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
                (self.serverhost, self.resieveport))
            self.server.addDefaultHandlers()

            self.server.addMsgHandler('default', self._dispatch)

            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop)
            self._listener_thread.daemon = True
            self._listener_thread.start()

            print 'Listening for SC OSC on port', self.resieveport

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
            if addr in self.callbacks:
                self.callbacks[addr](addr, data, source)
            elif self.default_callback:
                self.default_callback(addr, data, source)
        except:
            print 'Error in OSC callback for', addr

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
