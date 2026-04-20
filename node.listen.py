from lib.keys import Public, Private, Symmetric
from lib.const import Time, Type, Address
from lib.bytes import concat
from lib.parse import Message
from lib.error import AppException, BadMessageException

import socket
import select

import sys
import time

# KEYS
keys = {}
keys["self"] = Private("keys/validator.prv.pem")
keys["decision"] = Symmetric("keys/validator.sym")

for w in Address.WALLETS:
    keys[w] = Public("keys/{}.pub.pem".format(w))

# SOCKETS
sessions = {}
channels = {}

votes = {}
done = set()

# FUNCTIONS
def send_all(msg):
    for v in Address.VALIDATORS:
        if v == NODE_ID:
            continue

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_v:
                tcp_v.connect(Address.VALIDATORS[v])
                tcp_v.send(msg)
        except ConnectionRefusedError:
            print("Connection rejected on node {}!".format(v))

def handle_request(s):
    # parse REQ (258 bytes)
    m = (
        Message(s)
            .as_type(Type.REQ)
            .apply(keys["self"].decrypt)
    )

    (node_id, r, port) = m.get_fields(str, int, int)
    address = (m.address[0], port)

    # start dedicated channel
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.settimeout(Time.TIMEOUT)
    tcp.bind((NODE_ADDR[0], 0))
    tcp.connect(address)

    sessions[tcp] = (node_id, r)
    channels[(node_id, r)] = address
    
    # send ACK (258 bytes)
    ack = concat(
        Type.ACK,
        keys[node_id].encrypt(NODE_ID, r)
    )

    tcp.send(ack)

    # return dedicated channel
    return tcp

def handle_vote(session, node_id, action):
    if session not in votes:
        votes[session] = {
            Type.TKN: 0,
            Type.BAD: 0,
        }
    
    votes[session][action] += 1

    for result in votes[session]:
        if (session in channels) and (votes[session][result] > len(Address.VALIDATORS) / 2): 
            print("INTERNAL CONSENSUS")
            done.add(session)

            # send "sealed" consensus to validator network
            don = concat(
                Type.DON,
                keys["decision"].encrypt(action, NODE_ID, *session)
            )

            send_all(don)

            # send "open" consensus to requesting node
            don = concat(
                Type.DON,
                keys["self"].sign(action, NODE_ID, *session)
            )

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.settimeout(Time.TIMEOUT)
                tcp.bind((NODE_ADDR[0], 0))
                tcp.connect(channels[session])

                tcp.send(don)

            return result

    return None

def handle_channel(tcp):
    with tcp:
        session = sessions[tcp]
        (node_id, r) = session

        if session in done:
            return

        # parse TKN
        m = (
            Message(tcp)
                .as_type(Type.TKN)
                .apply(keys[node_id].unsign)
                .apply(keys["self"].decrypt)
        )

        data = m.as_json()

        # validate data
        print(node_id, data)

        action = Type.TKN

        # check for consensus
        consensus = handle_vote(session, NODE_ID, action)
        
        if consensus == None:
            # send VAL to validator network
            val = concat(
                Type.VAL,
                keys["decision"].encrypt(
                    action, NODE_ID, node_id, r
                )
            )

            send_all(val)

def handle_peer(tcp):
        try:
            (v_tcp, _) = tcp.accept()
        except TimeoutError:
            raise BadMessageException(tcp, None, "No message")

        with v_tcp:
            m = (
                Message(v_tcp)
                    .as_type(Type.VAL, Type.DON)
                    .apply(keys["decision"].decrypt)
            )
            
            (action, validator_id, session) = m.get_fields(
                Type, str, (str, int)
            )

            if session in done:
                return

            if m.type == Type.DON:
                print("EXTERNAL CONSENSUS")
                done.add(session)
            elif m.type == Type.VAL:
                # update consensus
                consensus = handle_vote(session, validator_id, action)

def poll():
    sockets = []

    try:
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.settimeout(Time.TIMEOUT)
        tcp.bind(NODE_ADDR)
        tcp.listen()

        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.settimeout(Time.TIMEOUT)
        udp.bind(Address.BROADCAST)

        sockets.append(tcp)
        sockets.append(udp)

        while True:
            try:
                (read_ready, _, _) = select.select(sockets, [], [], 0)

                for s in read_ready:
                    if s == udp:
                        new_tcp = handle_request(udp)
                        sockets.append(new_tcp)
                    elif s in sessions:
                        handle_channel(s)
                        sockets.remove(s)
                        sessions.pop(s)
                    else:
                        handle_peer(s)

                time.sleep(Time.POLL)
            except AppException as e:
                print(e)
    finally:
        for s in sockets:
            s.close()

if __name__ == "__main__":
    # NODE INFO
    NODE_ID = sys.argv[1]
    NODE_ADDR = Address.VALIDATORS[NODE_ID]

    poll()
