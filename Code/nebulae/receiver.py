import threading
import socket
import struct

class Receive(threading.Thread):
    def __init__(self, port=3100):
        threading.Thread.__init__(self)
        self.daemon = True
        self.port = port
        self.handlers = {}
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', self.port))
        self.sock.settimeout(0.2)  # allows clean shutdown

        print 'Listening for SC on port', self.port

    def add_handler(self, address, callback):
        """
        address  : OSC address string, e.g. '/sc/up'
        callback : function(addr, args)
        """
        self.handlers[address] = callback

    # --------------------------
    # Minimal OSC parsing
    # --------------------------
    def _parse_osc_message(self, data):
        """
        Parses a basic OSC message:
        - Address: null-terminated string
        - Type tag string: starts with ',', null-padded to 4 bytes
        - Arguments: int (i), float (f), or string (s)
        Returns (address, [arg1, arg2, ...])
        """
        print 'Got message, so happy!!!'
        try:
            # Find address (first null byte)
            address_end = data.find('\0')
            if address_end == -1:
                return None, []

            address = data[:address_end]

            # Align to 4-byte boundary
            addr_padding = (4 - (address_end % 4)) % 4
            type_start = address_end + 1 + addr_padding

            if type_start >= len(data):
                return address, []

            # Type tag string
            type_end = data.find('\0', type_start)
            if type_end == -1:
                return address, []

            type_tags = data[type_start:type_end]

            # Align to 4-byte boundary
            type_padding = (4 - ((type_end - type_start + 1) % 4)) % 4
            args_start = type_end + 1 + type_padding

            args = []
            offset = args_start

            for tag in type_tags[1:]:  # skip leading ','
                if tag == 'i':  # 32-bit int
                    arg = struct.unpack('>i', data[offset:offset+4])[0]
                    args.append(arg)
                    offset += 4
                elif tag == 'f':  # 32-bit float
                    arg = struct.unpack('>f', data[offset:offset+4])[0]
                    args.append(arg)
                    offset += 4
                elif tag == 's':  # string
                    str_end = data.find('\0', offset)
                    if str_end == -1:
                        str_end = len(data)
                    arg = data[offset:str_end]
                    args.append(arg)
                    # Align to 4-byte boundary
                    padding = (4 - ((str_end - offset + 1) % 4)) % 4
                    offset = str_end + 1 + padding
                else:
                    # Unknown type, skip
                    pass

            return address, args

        except Exception as e:
            print 'Failed to parse OSC message:', e
            return None, []

    # --------------------------
    # Thread run loop
    # --------------------------
    def run(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                address, args = self._parse_osc_message(data)
                if address in self.handlers:
                    self.handlers[address](address, args)
                else:
                    print 'Unhandled OSC message:', address, args
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print 'OSC receive error:', e

    def close(self):
        print 'Closing OSC receiver'
        self.running = False
        self.sock.close()