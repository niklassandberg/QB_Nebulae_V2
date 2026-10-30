from pythonosc import udp_client
import argparse

parser = argparse.ArgumentParser(description='Send an OSC Message.')
parser.add_argument('address',help='like "pitch"')
parser.add_argument('value',help='the value of parameter, like 0..1.')
args = parser.parse_args()

ip_address = "127.0.0.1"
port = 3000

full_address = "/neb/"+args.address

print(full_address)
print(args.value)

client = udp_client.SimpleUDPClient(ip_address, port)
client.send_message(full_address, float(args.value))