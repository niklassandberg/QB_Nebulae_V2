from pythonosc import udp_client
import sys

address = sys.argv[1]      # "/neb/pitch"
value = float(sys.argv[2]) # 0.7

client = udp_client.SimpleUDPClient("127.0.0.1", 3000)  # MUST be 3000!
client.send_message(address, value)
