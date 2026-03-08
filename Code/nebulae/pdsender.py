# Courtesy of hecanjob/pippi.pd
import socket
from classlogger import ClassLogger


class PdSend(object):
    pdhost = 'localhost'
    # pdhost = "192.168.0.33"
    sport = 3000
    rport = 3001

    def __init__(self):
        # Logger first
        self.log = ClassLogger.loggerSetup(self)

        # Instance state
        self.pd = None
        self.connected = False

    # -------------------------
    # Connection
    # -------------------------

    def connect(self):
        self.log.info("Connecting to PD")
        try:
            self.pd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.log.info("Created socket.")
            self.pd.connect((self.pdhost, self.sport))
            self.connected = True
            self.log.info("Sending to PD on port %s", self.sport)

        except Exception as e:
            self.log.error(
                "Connection failed - open PD with [netreceive %s]: %s",
                self.sport, e
            )

    # -------------------------
    # Sending
    # -------------------------

    def send(self, msgs):
        if not self.connected or not self.pd:
            self.log.warning("PD socket not connected. Cannot send messages.")
            return

        try:
            for msg in msgs:
                msg_str = str(msg) + ';'
                self.pd.send(msg_str)
                self.log.debug("Sent to PD: %s", msg_str)
        except Exception as e:
            self.log.error("Could not send to PD: %s", e)

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
        if self.pd and self.connected:
            try:
                self.log.info("Closing connection to PD")
                self.pd.close()
            except Exception as e:
                self.log.error("Error closing PD connection: %s", e)
        else:
            self.log.warning("No PD client to close.")
        self.connected = False

    def is_connected(self):
        return self.connected
