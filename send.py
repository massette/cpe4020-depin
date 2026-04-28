import sys
import socket
import secrets
import requests
import json
from datetime import datetime, UTC

from lib.const import Time, Type, Address
from lib.error import AppException
from lib.keys import Private, Public
from lib.parse import Message
from lib.bytes import concat

################################################################ NODE DETAILS ##
NODE_ID = sys.argv[1]

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
        tcp.settimeout(Time.TIMEOUT)
        tcp.listen()

        # make REQ
        _, port = tcp.getsockname()

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
            print("SEND REQ")
            udp.sendto(req, Address.BROADCAST)

        # parse ACK
        tcp_ack, _ = tcp.accept()

        with tcp_ack:
            ack = Message.from_socket(tcp_ack).as_type(Type.ACK)
        
        # check nonce
        ack.apply(keys["self"].decrypt)
        validator_id, r_ack = ack.get_fields(str, int)

        if r != r_ack:
            raise ack.error("Bad nonce.")

        # return first address to respond
        return ack.address

################################################################# TEST SCRIPT ##
# when run as a standalone script,
# echo any input from stdin to the /mint endpoint
if __name__ == "__main__":
    addr = request_validator()
    mint_uri = "http://{}:6561/mint".format(addr)

    data = json.dumps({
        "node_id": NODE_ID,
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "lock_rotation",

        "angle_change_deg": 20,
        "prev_angle_deg": 40,
        "angle_deg": 60,
    })

    payload = keys["self"].sign(data)
    requests.post(mint_uri, payload)

#    while True:
#        raw = input("> ")
#        
#        if raw.strip() == "":
#            break
#
#        data = json.dumps({ "test": raw })
#        payload = keys["self"].sign(data)
#
#        requests.post(mint_uri, payload)
