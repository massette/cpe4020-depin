import sys
import time
import socket
import select
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request
from random import shuffle

from lib.const import Time, Type, Address
from lib.error import AppException
from lib.keys import Symmetric, Public, Private
from lib.parse import Message
from lib.bytes import concat

from ledger import load_ledger, add_block

################################################################ NODE DETAILS ##
NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]

############################################################# ENCRYPTION KEYS ##
keys = {}
keys["self"] = Private("keys/validator.prv.pem")
keys["validators"] = Symmetric("keys/validator.sym")

# initialize wallets
wallets = {}

for w in Address.WALLETS:
    keys[w] = Public("keys/{}.pub.pem".format(w))
    addr = keys[w].reveal()
    wallets[addr] = 0

# load previous transactions
def update_transactions():
    global transactions
    transactions = load_ledger()

    for block in transactions:
        if block["from"] != "MINT":
            wallets[block["from"]] -= block["amount"]
        
        wallets[block["to"]] += block["amount"]

update_transactions()

############################################################# SESSION DETAILS ##
class Session:
    def __init__(self, *session):
        self.session = session

        # local decision
        self.data = None

        self.val_received = set()
        self.counts = {
            Type.TKN: 0,
            Type.BAD: 0,
        }

        # remote decisions
        self.don_received = set()
        self.consensus = None
        self.timestamp = None

    def set_data(self, data):
        # check if data has already been set
        if self.data:
            print("WARN! Data already set on {}#{}!".format(*self.session))
            return
        
        # update data
        self.data = data

        # check for final consensus
        if len(self.don_received) == len(Address.VALIDATORS):
            self.resolve()

    def add_decision(self, validator_id, decision):
        # check if validator has already responded
        if validator_id in self.val_received:
            print("WARN! Repeated validator on {}#{} (VAL)!".format(
                *self.session)
            )

            return

        # update counts
        self.counts[decision] += 1
        self.val_received.add(validator_id)

        # check for majority
        if not self.consensus:
            for result in self.counts:
                if self.counts[result] > len(Address.VALIDATORS) / 2:
                    print("Local consensus on {}#{}.".format(
                        *self.session
                    ))

                    timestamp = time.time()
                    self.add_consensus(NODE_ID, result, timestamp)
    
    def add_consensus(self, validator_id, decision, timestamp):
        # check if validator has already responded
        if validator_id in self.don_received:
            print("WARN! Repeated validator on {}#{} (DON)!".format(
                *self.session)
            )
            return
        
        # check timestamp
        if not self.timestamp:
            self.timestamp = timestamp
        elif timestamp != self.timestamp:
            print("WARN! Multiple consensus on {}#{}!".format(*self.session))
            
            if timestamp < self.timestamp:
                self.timestamp = timestamp

        # check against local consensus
        if not self.consensus:
            if validator_id != NODE_ID:
                print("Remote consensus ({}) on {}#{}.".format(
                    validator_id, *self.session
                ))
                print("Consensus 1 ({}) on {}#{}.".format(
                    NODE_ID, *self.session
                ))

            # update local consensus if none exists
            self.consensus = decision
            self.don_received.add(NODE_ID)

            # send DON to connected validators
            don = concat(
                Type.DON,
                keys["validators"].encrypt(
                    *self.session, NODE_ID, self.consensus, self.timestamp
                )
            )
            
            send_others(don)
        elif decision != self.consensus:
            self.reject()
            raise AppException("Split consensus on {}#{}!".format(*self.session))

        # update consensus list
        self.don_received.add(validator_id)
        print("Consensus {} ({}) on {}#{}.".format(
            len(self.don_received), validator_id, *self.session
        ))

        # check for final consensus
        if self.data and (len(self.don_received) == len(Address.VALIDATORS)):
            self.resolve()

    def reject(self):
        self.consensus = Type.BAD
        self.resolve()

    def resolve(self):
        print()
        print("======================================= {} ! ==".format(
            self.consensus.name
        ))
        print("TIME=", self.timestamp)
        print("SELL=", b"MINT")
        print("BUY =", keys[self.session[0]].reveal())
        print("-------------------------------------------------")
        print(self.data)
        print("=================================================")
        print()

        # mint token
        if self.consensus == Type.TKN:
            add_block(
                self.timestamp,
                b"MINT",
                keys[self.session[0]].reveal(),
                NODE_ID,
                self.data
            )

        # mark session complete
        sessions.pop(self.session)
        done.add(self.session)

        if self.session in pending:
            pending[self.session].set()

pending = {}
sessions = {}
done = set()

# fetch an existing session or initialize a new one if it does not exist
def get_session(*session):
    if session not in sessions:
        sessions[session] = Session(*session)

    return sessions[session]

################################################################### FUNCTIONS ##
# handle anonymous validation request
def handle_request(udp):
    # parse REQ
    req = Message.from_socket(udp).as_type(Type.REQ)
    
    # check signature against each wallet key
    wallet_id = None

    for w in Address.WALLETS:
        try:
            req.apply(keys[w].unsign)
            wallet_id = w
            break
        except:
            # wrong key, try again
            continue

    # fail if no key matched
    if wallet_id == None:
        return

    # finish parse REQ
    req.apply(keys["self"].decrypt)
    r, port = req.get_fields(int, int)

    # reply on dedicated TCP channel
    ack_address = req.address, port
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_ack:
        tcp_ack.settimeout(Time.TIMEOUT)
        tcp_ack.bind((NODE_ADDR[0], 0))

        try:
            # attempt connect
            tcp_ack.connect(ack_address)
            
            # send ACK
            ack = concat(
                Type.ACK, 
                keys[wallet_id].encrypt(NODE_ID, r)
            )

            tcp_ack.send(ack)
        except ConnectionRefusedError:
            # ignore connection refused,
            # another validator has already responded
            return

# handle message from validator
def handle_validator(tcp):
    # record time at start of transaction
    now = datetime.now()

    # establish connection
    (tcp_val, _) = tcp.accept()

    with tcp_val:
        # receive message
        msg = Message.from_socket(tcp_val)
        msg.apply(keys["validators"].decrypt)
        
    # parse session
    wallet_id, session_id = msg.get_fields(str, int)

    if (wallet_id, session_id) in done:
        # ignore any message on previous sessions
        print("WARN! {} after end of session {}#{}!".format(
            msg.type, wallet_id, session_id)
        )

        return

    session = get_session(wallet_id, session_id)

    # parse message
    if msg.type == Type.TKN:
        # parse TKN, new data to validate
        tkn = msg.as_type(Type.TKN)
        
        # store signed data
        session.set_data(tkn.body)

        # validate data
        tkn.apply(keys[wallet_id].unsign)
        data = tkn.as_json()

        # default accept mint
        decision = Type.TKN

        # check for invalid data
        if (("node_id" not in data)
            or ("event" not in data)
            or ("timestamp" not in data)):
            print("Reject! Missing required field.")
            decision = Type.BAD
        else:
            start_time = datetime.fromisoformat(data["timestamp"])
            delta = start_time - now

            if ((delta < timedelta(seconds=0))
                or (delta > timedelta(seconds=30))):
                print("Reject! Bad timestamp.")

            elif data["event"] == "lock_rotation":
                if (("angle_change_deg" not in data)
                    or ("prev_angle_deg" not in data)
                    or ("angle_deg" not in data)):
                    print("Reject! Missing event-specific field.")
                    decision = Type.BAD

                elif ((data["angle_deg"] < 0)
                      or (data["angle_deg"] > 360)):
                    print("Reject! Bad angle.")
                    decision = Type.BAD

                else:
                    expected = data["prev_angle_deg"] + data["angle_change_deg"]

                    if data["angle_deg"] != expected:
                        print("Reject! Angles do not add up.")
                        decision = Type.BAD
                    else:
                        print("Transfer approved.")

            else:
                print("Reject! Invalid sensor event.")
                decision = Type.BAD

        # update session
        session.add_decision(NODE_ID, decision)

        # if no consensus, send VAL to connected validators
        if not session.consensus:
            val = concat(
                Type.VAL,
                keys["validators"].encrypt(
                    wallet_id, session_id, NODE_ID, decision
                )
            )

            send_others(val)

    elif msg.type == Type.MOV:
        # parse TKN, new data to validate
        mov = msg.as_type(Type.MOV)
        
        # store signed data
        session.set_data(mov.body)

        # validate data
        mov.apply(keys[wallet_id].unsign)
        data = mov.as_json()
        #checking for correct formatting
        if (("node_id" not in data)
            or ("recipient" not in data)
            or ("timestamp" not in data)
            or ("amount" not in data)):
            print("Reject! Missing required field.")
            decision = Type.BAD

        else:
            #checking the timestamp
            start_time = datetime.fromisoformat(data["timestamp"])
            delta = start_time - now

            if ((delta < timedelta(seconds=0))
                or (delta > timedelta(seconds=5))):
                print("Reject! Bad timestamp.")

               # Check recipient exists
            elif data["recipient"] not in wallets:
                print("Reject! Recipient wallet does not exist.")
                decision = Type.BAD            

            # Check amount is valid
            elif data["amount"] <= 0:
                print("Reject! Invalid amount.")
                decision = Type.BAD  

            else:
                addr = keys[wallet_id].reveal()

                # Check sender has enough funds
                if wallets[addr] < data["amount"]:
                    print("Reject! Insufficient funds.")
                    decision = Type.BAD
                else:
                    print("Transfer approved.")

    elif msg.type == Type.VAL:
        # parse VAL, intermediate validator decision
        val = msg.as_type(Type.VAL)
        validator_id, decision = val.get_fields(str, Type)

        session.add_decision(validator_id, decision)

    elif msg.type == Type.DON:
        # parse DON, final validator decision
        don = msg.as_type(Type.DON)
        validator_id, decision, timestamp = don.get_fields(str, Type, float)

        session.add_consensus(validator_id, decision, timestamp)

        # warn! race condition
        # if minting multiple tokens at once across the network,
        #   different validators may resolve them in a different order
        #   resulting in different copies of the ledger, compromising the chain

# send a message to all connected validators
def send_all(msg):
    # validators = list(Address.VALIDATORS.keys())
    # shuffle(validators)

    for v in Address.VALIDATORS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_v:
                tcp_v.connect(Address.VALIDATORS[v])
                tcp_v.send(msg)
        except ConnectionRefusedError:
            print("Connection rejected on node {}!".format(v))

        # time.sleep(0.2)

# send a message to all connected validators (except this one)
def send_others(msg):
    for v in Address.VALIDATORS:
        if v == NODE_ID:
            continue

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_v:
                tcp_v.connect(Address.VALIDATORS[v])
                tcp_v.send(msg)
        except ConnectionRefusedError:
            print("Connection rejected on node {}!".format(v))

# poll sockets
def poll(address):
    # udp socket for initial anonymous validation requests
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.settimeout(Time.TIMEOUT)
    udp.bind(Address.BROADCAST)

    # tcp socket for communications with other validators
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.settimeout(Time.TIMEOUT)
    tcp.bind(address)
    tcp.listen()

    # list of all sockets
    sockets = [ udp, tcp ]

    try:
        # poll loop until
        while True:
            try:
                (ready, _, _) = select.select(sockets, [], [], 0)

                for s in ready:
                    if s == udp:
                        handle_request(udp)
                    else:
                        handle_validator(tcp)

                time.sleep(Time.POLL)
            except AppException as e:
                print(e)
    finally:
        udp.close()
        tcp.close()

################################################################# TEST SCRIPT ##
# when run as a standalone script,
# poll for any TCP validator messages
if __name__ == "__main__":
    poll(NODE_ADDR)
