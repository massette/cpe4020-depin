from lib.keys import Public, Private, Symmetric
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
keys["decision"] = Symmetric("keys/validator.sym")

for w in Address.WALLETS:
    keys[w] = Public("keys/{}.pub.pem".format(w))

# SOCKETS
channels = {}

# FUNCTIONS
def handle_request(s):
    # parse REQ (258 bytes)
    m = (
        Message(s)
            .parse_type(Type.REQ)
            .apply(keys["self"].decrypt)
    )

    (node_id, r, address) = m.get_fields(str, int, Address)

    # start dedicated channel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind((NODE_ADDR[0], 0))
    tcp.connect(address)
    tcp.settimeout(0)

    channels[tcp] = {
        "session": (node_id, r),
    }
    
    # send ACK (258 bytes)
    ack = concat(
        Type.ACK,
        keys[node_id].encrypt(NODE_ID, r)
    )

    tcp.send(ack)

    # return dedicated channel
    return tcp

def send_all(msg):
    for v in Address.VALIDATORS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            tcp_v = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_v.connect(Address.VALIDATORS[v])
            tcp_v.send(msg)

def handle_channel(tcp):
    with tcp:
        ch = channels[tcp]

        # parse TKN
        m = (
            Message(tcp)
                .parse_type(Type.TKN)
                .apply(keys[ch["session"][0]].unsign)
                .apply(keys["self"].decrypt)
        )

        data = json.loads(m.body.decode())

        # validate data
        print(ch["session"][0], data)

        # send VAL to validator network
        val = concat(
            Type.VAL,
            keys["decision"].encrypt(
                Type.TKN, NODE_ID, ch["session"][0], ch["session"][1]
            )
        )

        send_all(val)

        # check for consensus

def handle_decision(tcp):
        (v_tcp, _) = tcp.accept()

        with v_tcp:
            m = (
                Message(v_tcp)
                    .parse_type(Type.VAL, Type.DON)
                    .apply(keys["decision"].decrypt)
            )

            print(m.type)
            print(m.get_fields(Type, str, str, int))
            print()

            # TODO! Fix race condition
            # may receive decision before creating session
            # may even finish session before receiving data

            # check for consensus

def poll():
    sockets = []

    try:
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.settimeout(0)
        tcp.bind(NODE_ADDR)
        tcp.listen()

        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.settimeout(0)
        udp.bind(Address.BROADCAST)

        sockets.append(tcp)
        sockets.append(udp)

        while True:
            try:
                (read_ready, _, _) = select.select(sockets, [], [])

                for s in read_ready:
                    if s == udp:
                        new_tcp = handle_request(udp)
                        sockets.append(new_tcp)
                    elif s in channels:
                        handle_channel(s)
                        sockets.remove(s)
                        channels.pop(s)
                    else:
                        handle_decision(s)

            except AppException as e:
                print(e)
    finally:
        for s in sockets:
            s.close()

if __name__ == "__main__":
    poll()
