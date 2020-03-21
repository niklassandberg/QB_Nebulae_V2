# Courtesy of hecanjob/pippi.pd
import sys
sys.path.insert(0, '/home/alarm/QB_Nebulae_V2/Code/nebulae/lib')

import socket
import scosc

class ScSend():
    schost = 'localhost'
    #pdhost = "192.168.0.33"
    serverport = 3000
    recvport = 3001
    socket = None
    timeout = 2
    connected = False

    def __init__(self):
        self.connect()

    def connect(self):
        print 'connecting to sc'
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)
            self.connected = True
            print 'Sending to SC on port ' + str(self.serverport)

        except:
            print 'Connection failed - open SC'

    def _send(self, bin):
        self.socket.sendto(bin, (self.serverip, self.serverport))

    def send(self, what, value):
        try 
            oscmessage = OSC.OSCMessage()
            oscmessage.setaddress("/neb/")
            oscmessage.append(value)
            self._send(oscmessage.getBinary())
        except:
            print 'Could not send to SC. Did you open a connection?'

    def close(self):
        print 'Closing connection to SC'
        self.socket.close()
        self.connected = False

    def is_connected(self):
        return self.connected
