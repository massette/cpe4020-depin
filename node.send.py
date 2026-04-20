from lib.keys import Public, Private
from lib.const import Time, Type, Address
from lib.bytes import concat
from lib.parse import Message
from lib.error import AppException

import time
import socket
import select
from secrets import randbits

import sys

TIMEOUT = 15.00

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

    pending[tcp] = {
        "session": r,
        "data": data,
        "start": time.time(),
        "ack": 0
    }

    # broadcast REQ (258 bytes)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        address = tcp.getsockname()

        req = concat(
            Type.REQ,
            keys["validator"].encrypt(NODE_ID, r, address[1])
        )

        udp.sendto(req, Address.BROADCAST)

def handle_channel(tcp):
    ch = pending[tcp]
    (tcp_connect, _) = tcp.accept()

    with tcp_connect:
        m = Message(tcp_connect).as_type(Type.ACK, Type.DON) 
        
        if m.type == Type.ACK:
            ch["ack"] += 1

            # parse ACK
            m.apply(keys["self"].decrypt)
            (validator_id, r) = m.get_fields(str, int)

            # check nonce
            if r != ch["session"]:
                raise m.error("Bad session.")

            # send TKN
            ack = concat(
                Type.TKN,
                keys["self"].sign(keys["validator"].encrypt(ch["data"]))
            )

            tcp_connect.send(ack)
        elif m.type == Type.DON:
            tcp.close()
            pending.pop(tcp)
            
            print("Message #{} fulfilled.".format(ch["session"]))

def fulfill():
    global pending

    try:
        while len(pending) > 0:
            (ready, _, _) = select.select(pending.keys(), [], [], 0)

            for tcp in ready:
                handle_channel(tcp)

            now = time.time()

            for tcp in list(pending.keys()):
                ch = pending[tcp]

                if (now - ch["start"]) > Time.TIMEOUT:
                    tcp.close()
                    pending.pop(tcp)

                    print(
                        "Message #{} timeout! Found {} validators.".format(
                            ch["session"], ch["ack"]
                        )
                    )

                time.sleep(Time.POLL)

    except AppException as e:
        print(e)

def close():
    for tcp in pending:
        tcp.close()

if __name__ == "__main__":
    try:
        while True:
            data = input("> ")

            if data == "":
                break
            else:
                send({ "test": data })
                fulfill()
    finally:
        close()
