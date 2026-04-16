from lib.keys import Public, Private
from lib.const import Type, Address
from lib.bytes import concat
from lib.parse import Message
from lib.error import AppException

import json
import socket
import select
from secrets import randbits

import sys

# NODE INFO
NODE_ID = sys.argv[1]
NODE_ADDR = Address.WALLETS[NODE_ID]

# KEYS
keys = {}
keys["self"] = Private("keys/{}.prv.pem".format(NODE_ID))
keys["validator"] = Public("keys/validator.pub.pem")

# CONNECTIONS
pending = {}

# FUNCTIONS
def send(data):
    # create dedicated channel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(NODE_ADDR)
    tcp.listen()

    # generate new session id
    r = randbits(32)

    while r in pending:
        r = randbits(32)

    address = tcp.getsockname()
    pending[tcp] = {
        "session": r,
        "data": json.dumps(data).encode(),
        "ack": 0
    }

    # broadcast REQ (258 bytes)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        req = concat(
            Type.REQ,
            keys["validator"].encrypt(NODE_ID, r, tcp.getsockname())
        )

        udp.sendto(req, Address.BROADCAST)

def handle_channel(tcp):
    ch = pending[tcp]
    (tcp_connect, _) = tcp.accept()

    with tcp_connect:
        m = Message(tcp_connect)
        
        if m.type == Type.ACK:
            ch["ack"] += 1

            # parse ACK
            m.apply(keys["self"].decrypt)
            (validator_id, r) = m.get_fields(str, int)

            # check nonce
            if r != ch["session"]:
                raise m.error("Wrong channel.")

            # send TKN
            ack = concat(
                Type.TKN,
                keys["self"].sign(keys["validator"].encrypt(ch["data"]))
            )

            tcp_connect.send(ack)

    # close port when all responses have been received
    if ch["ack"] >= len(Address.VALIDATORS):
        pending.pop(tcp)
        tcp.close()

def poll():
    try:
        while len(pending) > 0:
            (read_ready, _, _) = select.select(pending.keys(), [], [])

            for tcp in read_ready:
                handle_channel(tcp)
    except AppException as e:
        print(e)

def close():
    for s in pending:
        s.close()

if __name__ == "__main__":
    try:
        send({ "test": True })
        poll()
    finally:
        close()
