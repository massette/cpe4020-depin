import sys
import time
import socket
import select
from datetime import datetime, timedelta, UTC
from threading import Thread
from flask import Flask, request
from random import shuffle

from lib.const import Time, Type, Address
from lib.error import AppException
from lib.keys import Symmetric, Public, Private
from lib.parse import Message
from lib.bytes import concat

from ledger import add_block

################################################################ NODE DETAILS ##
NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]

############################################################# ENCRYPTION KEYS ##
keys = {}
keys["self"] = Private("keys/validator.prv.pem")
keys["validators"] = Symmetric("keys/validator.sym")

# derive wallet addresses from keys
wallets = set()

for w in Address.WALLETS:
    keys[w] = Public("keys/{}.pub.pem".format(w))
    wallets.add(keys[w].reveal())

############################################################# SESSION DETAILS ##
class Session:
    def __init__(self, *session):
        self.session = session # (wallet_id, session_id)
        self.data = None

        # votes towards a local consensus
        self.val_received = set()
        self.counts = {
            Type.TKN: 0,
            Type.BAD: 0,
        }

        # aggregate network consensus across network
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

        # when all validators have agreed, end session
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
        
        # keep earliest timestamp
        if not self.timestamp:
            self.timestamp = timestamp
            self.consensus_from = validator_id
        elif timestamp != self.timestamp:
            print("WARN! Multiple consensus on {}#{}!".format(*self.session))
            
            if timestamp < self.timestamp:
                self.timestamp = timestamp
                self.consensus_from = validator_id

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

        # if all validator have agreed, end session
        if self.data and (len(self.don_received) == len(Address.VALIDATORS)):
            self.resolve()

    def reject(self):
        self.consensus = Type.BAD
        self.resolve()

    def resolve(self):
        print()

        # if accepted, add block to ledger
        if self.consensus == Type.TKN:
            add_block(
                self.timestamp,
                "MINT",
                keys[self.session[0]].reveal(),
                self.consensus_from,
                self.data
            )

            print("======================================== TKN ! ==")
            print("TIME=", self.timestamp)
            print("FROM=", b"MINT")
            print("TO  =", keys[self.session[0]].reveal())
            print("-------------------------------------------------")
            print(self.data)
            print("=================================================")
            print()
        elif self.consensus == Type.MOV:
            # add_block

            print()
            print("======================================== MOV ! ==")
            print("TIME=", self.timestamp)
            print("FROM=", b"MINT")
            print("TO  =", keys[self.session[0]].reveal())
            print("-------------------------------------------------")
            print(self.data)
            print("=================================================")
            print()
        else:
            print()
            print("======================================== {} ! ==".format(
                self.consensus.name
            ))
            print("TIME=", self.timestamp)
            print("-------------------------------------------------")
            print(self.data)
            print("=================================================")
            print()

        # mark session complete
        sessions.pop(self.session)
        results[self.session] = self.consensus

        # notify HTTP thread
        if self.session in pending:
            pending[self.session].set()

# on-going validator sessions seeking network consensus
sessions = {}

# sessions which have been resovled to a single decision
results = {}

# http responses by session awaiting action
pending = {}

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

    # establish connection
    (tcp_val, _) = tcp.accept()

    # receive message, unknown type
    with tcp_val:
        msg = Message.from_socket(tcp_val)
        
    # parse session information
    msg.apply(keys["validators"].decrypt)
    wallet_id, session_id = msg.get_fields(str, int)

    if (wallet_id, session_id) in results:
        # ignore any message on previous sessions
        print("WARN! {} after end of session {}#{}!".format(
            msg.type, wallet_id, session_id)
        )

        return

    session = get_session(wallet_id, session_id)

    # parse message
    if (msg.type == Type.TKN) or (msg.type == Type.MOV):
        # validate data
        msg.apply(keys[wallet_id].unsign)

        session.set_data(msg.body.decode())
        data = msg.as_json()

        # choose validation logic based on action
        if msg.type == Type.TKN:
            decision = validate_mint(data)
        else:
            decision = validate_move(data)

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

    else:
        print("WARN! Unexpected message type {}.".format(msg.type))

# time constants
MIN_DELTA = timedelta(seconds=0)
MAX_DELTA = timedelta(seconds=15)

# run validation on mint data
def validate_mint(data):
    # check for required fields
    if any(key not in data for key in ("node_id", "timestamp", "event")):
        print("Reject! Missing required field.")
        return Type.BAD
    
    # check timestamp
    start_time = datetime.fromisoformat(data["timestamp"])
    delta = datetime.now(UTC) - start_time

    if (delta < MIN_DELTA) or (delta > MAX_DELTA):
        print("Reject! Bad timestamp.")
        return Type.BAD
    
    # check event
    if data["event"] == "lock_rotation":
        # check for more required fields
        if any(key not in data for key in ("angle_change_deg", "prev_angle_deg",
                                           "angle_deg")):
            print("Reject! Missing event-specific field.")
            return Type.BAD

        # check angles
        if (data["angle_deg"] < 0) or (data["angle_deg"] > 360):
            print("Reject! Bad angle.")
            decision = Type.BAD

        delta = abs(data["angle_deg"] - data["prev_angle_deg"])
        if delta - data["angle_change_deg"] < 0.1:
            print("Reject! Angles do not add up.")
            decision = Type.BAD
        
    else:
        print("Reject! Invalid sensor event.")
        return Type.BAD
    
    # otherwise, accept mint
    return Type.TKN

# run validation on transfer data
def validate_move(data):
    # check for required fields
    if any(key not in data for key in ("node_id", "timestamp",
                                       "recipient", "amount")):
        print("Reject! Missing required field.")
        return Type.BAD

    # check timestamp
    start_time = datetime.fromisoformat(data["timestamp"])
    delta = datetime.now(UTC) - start_time

    if (delta < MIN_DELTA) or (delta > MAX_DELTA):
        print("Reject! Bad timestamp.")
        return Type.BAD

    # check for recipient
    if data["recipient"] not in wallets:
        print("Reject! Recipient wallet does not exist.")
        return Type.BAD

    # check amount
    if data["amount"] <= 0:
        print("Reject! Invalid amount.")
        return Type.BAD
    
    if wallets[data["recipient"]] < data["amount"]:
        print("Reject! Insufficient funds.")
        return Type.BAD
    
    # otherwise, accept move
    return Type.MOV
    
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

    try:
        udp.bind(Address.BROADCAST)
    except OSError:
        # windows fix ?
        udp.bind(("0.0.0.0", Address.BROADCAST[1]))

    # tcp socket for communications with other validators
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.settimeout(Time.TIMEOUT)
    tcp.bind(address)
    tcp.listen()

    # list of all sockets
    sockets = [ udp, tcp ]

    try:
        # poll sockets until interrupted
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
