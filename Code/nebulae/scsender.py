# Courtesy of hecanjob/pippi.pd
import sys
import os
sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

from OSC import OSCClient, OSCMessage  # pyOSC

class ScSend():
    values = {}
    serverhost = 'localhost'
    serverport = 3000
    resieveport = 3001
    client = None
    connected = False

    def __init__(self):
        self.connect()

    def connect(self):
        print 'connecting to sc'
        try:
            self.client = OSCClient()
            self.client.connect((self.serverhost, self.serverport))
            self.connected = True
            print 'Sending to SC on port {} : {}'.format(self.serverhost, self.serverport)
        except:
            print 'Connection failed - open SC'

    def clear(self):
        self.values = {}

    def send(self, what, value):
        try:
            if what in self.values and self.values[what] == value:
                return
            str = "/neb/" + what
            print "SC OSC sending: " + str
            self.values[what] = value
            msg = OSCMessage()
            msg.setAddress(str)
            msg.append(value)
            if self.connected:
                self.client.send(msg)
        except:
            print 'Could not send to SC. Did you open a connection?'

    def close(self):
        try:
            if self.client and self.connected:
                print 'Closing connection to SC'
                self.client.close()
            else:
                print 'No SC client to close!!!'
        except:
            print 'except closing connection to SC'
        self.connected = False

    def is_connected(self):
        return self.connected
