from lib.keys import Public, Private
from lib.const import Type, Address
from lib.bytes import concat
from lib.parse import Message
from lib.error import AppException, BadMessageException

import json
import socket
import select

import sys

# NODE INFO
NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]

# KEYS
keys = {}
keys["self"] = Private("keys/validator.prv.pem")

for w in Address.WALLETS:
    keys[w] = Public("keys/{}.pub.pem".format(w))

# SOCKETS
pending = {}

# FUNCTIONS
def handle_request(s):
    # parse REQ (258 bytes)
    m = (
        Message(s)
            .parse_type(Type.REQ)
            .apply(keys["self"].decrypt)
    )

    (node_id, session, address) = m.get_fields(str, int, Address)

    # start dedicated channel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind((NODE_ADDR[0], 0))
    tcp.connect(address)
    tcp.settimeout(0)

    pending[tcp] = {
        "id": node_id,
        "session": session,
    }
    
    # send ACK (258 bytes)
    ack = concat(
        Type.ACK,
        keys[node_id].encrypt(NODE_ID, session)
    )

    tcp.send(ack)

    # return dedicated channel
    return tcp

def handle_channel(tcp):
    with tcp:
        ch = pending[tcp]

        # parse TKN
        m = (
            Message(tcp)
                .apply(keys[ch["id"]].unsign)
                .apply(keys["self"].decrypt)
        )

        data = json.loads(m.body.decode())

        # validate data
        print(ch["id"], data)

        # send VAL to validator network

        # check for consensus

def poll():
    sockets = []

    try:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.settimeout(0)
        udp.bind(NODE_ADDR)

        sockets.append(udp)

        while True:
            try:
                (read_ready, _, _) = select.select(sockets, [], [])

                for s in read_ready:
                    if s == udp:
                        tcp = handle_request(udp)
                        sockets.append(tcp)
                    else:
                        handle_channel(s)
                        sockets.remove(s)
                        pending.pop(s)

            except AppException as e:
                print(e)
    finally:
        for s in sockets:
            s.close()

if __name__ == "__main__":
    poll()
