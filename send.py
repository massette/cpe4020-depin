import sys
import socket
import secrets
import requests
import json

from lib.const import Type, Address
from lib.error import AppException
from lib.keys import Private, Public
from lib.parse import Message
from lib.bytes import concat

################################################################ NODE DETAILS ##
NODE_ID = sys.argv[1]
NODE_ADDR = Address.WALLETS[NODE_ID]

############################################################# ENCRYPTION KEYS ##
keys = {}
keys["self"] = Private("keys/{}.prv.pem".format(NODE_ID))
keys["validator"] = Public("keys/validator.pub.pem")

################################################################### FUNCTIONS ##
# get address of some validator in the network
def request_validator():
    # generate nonce
    r = secrets.randbits(32)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        # create TCP channel to listen for response
        tcp.bind(Address.WALLETS[NODE_ID])
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.listen()

        # make REQ
        (_, port) = tcp.getsockname()

        req = concat(
            Type.REQ,
            keys["self"].sign(
                keys["validator"].encrypt(r, port)
            )
        )

        # broadcast REQ to LAN
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.sendto(req, Address.BROADCAST)

        # parse ACK
        (tcp_ack, _) = tcp.accept()
        ack = Message.from_socket(tcp_ack).as_type(Type.ACK)
        ack.apply(keys["self"].decrypt)

        # check nonce
        validator_id, r_ack = ack.get_fields(str, int)

        if r != r_ack:
            raise ack.error("Bad nonce.")

        # return responding address
        return ack.address

################################################################# TEST SCRIPT ##
# when run as a standalone script,
# echo any input from stdin to the /mint endpoint
if __name__ == "__main__":
    addr = request_validator()
    mint_uri = "http://{}:6561/mint".format(addr)

    while True:
        raw = input("> ")
        
        if raw.strip() == "":
            break

        data = json.dumps({ "test": raw })
        payload = keys["self"].sign(data)

        requests.post(mint_uri, payload)
