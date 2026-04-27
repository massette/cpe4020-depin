import sys
import time
import socket
import select

from lib.const import Time, Type, Address
from lib.error import AppException
from lib.keys import Symmetric, Public, Private
from lib.parse import Message
from lib.bytes import concat
from ledger import add_block


################################################################ NODE DETAILS ##
# Which validator this instance is
NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]


############################################################# ENCRYPTION KEYS ##
# Load validator private key + shared validator key
keys = {}
keys["self"] = Private("keys/validator.prv.pem")
keys["validators"] = Symmetric("keys/validator.sym")

# Load all wallet public keys
for wallet_id in Address.WALLETS:
    keys[wallet_id] = Public("keys/{}.pub.pem".format(wallet_id))


############################################################# SESSION STORAGE ##
# pending = sessions waiting for HTTP response
pending = {}

# sessions = active validator consensus sessions
sessions = {}

# done = completed sessions
done = set()


################################################################ SESSION CLASS ##
class Session:
    def __init__(self, *session):
        self.session = session  # (wallet_id, session_id)
        self.data = None

        # Track validator votes
        self.val_received = set()
        self.counts = {
            Type.TKN: 0,
            Type.BAD: 0,
        }

        # Track consensus confirmations
        self.don_received = set()
        self.consensus = None
        self.timestamp = None

    ############################################################ SET DATA ##
    def set_data(self, data):
        if self.data:
            print("WARN! Data already set on {}#{}!".format(*self.session))
            return

        self.data = data

        # If consensus already reached, finalize
        if len(self.don_received) == len(Address.VALIDATORS):
            self.resolve()

    ######################################################## ADD DECISION ##
    def add_decision(self, validator_id, decision):
        # Prevent duplicate votes
        if validator_id in self.val_received:
            print("WARN! Repeated validator on {}#{} (VAL)!".format(*self.session))
            return

        self.counts[decision] += 1
        self.val_received.add(validator_id)

        # Check for majority vote
        if not self.consensus:
            for result in self.counts:
                if self.counts[result] > len(Address.VALIDATORS) / 2:
                    print("Local consensus on {}#{}.".format(*self.session))
                    self.add_consensus(NODE_ID, result, time.time())

    ######################################################## ADD CONSENSUS ##
    def add_consensus(self, validator_id, decision, timestamp):
        if validator_id in self.don_received:
            print("WARN! Repeated validator on {}#{} (DON)!".format(*self.session))
            return

        # Keep earliest timestamp
        if not self.timestamp:
            self.timestamp = timestamp
        elif timestamp < self.timestamp:
            self.timestamp = timestamp

        # First consensus reached
        if not self.consensus:
            self.consensus = decision
            self.don_received.add(NODE_ID)

            # Broadcast DON (final consensus message)
            don = concat(
                Type.DON,
                keys["validators"].encrypt(
                    *self.session,
                    NODE_ID,
                    self.consensus,
                    self.timestamp,
                ),
            )

            send_others(don)

        elif decision != self.consensus:
            self.reject()
            raise AppException("Split consensus on {}#{}!".format(*self.session))

        self.don_received.add(validator_id)

        print(
            "Consensus {} ({}) on {}#{}.".format(
                len(self.don_received),
                validator_id,
                *self.session,
            )
        )

        # If all validators agreed, finalize
        if self.data and len(self.don_received) == len(Address.VALIDATORS):
            self.resolve()

    ############################################################ REJECT ##
    def reject(self):
        self.consensus = Type.BAD
        self.resolve()

    ############################################################ RESOLVE ##
    def resolve(self):
        print()
        print("=======================================")
        print("CONSENSUS:", self.consensus.name)
        print("TIME:", self.timestamp)
        print("SESSION:", self.session)
        print("=======================================")
        print(self.data)
        print("=======================================")
        print()

        # If accepted → add block to ledger
        if self.consensus == Type.TKN:
            add_block(
                self.timestamp,
                "MINT",
                keys[self.session[0]].reveal(),
                NODE_ID,
                self.data,
                amount=10,
            )

        # Clean up session
        sessions.pop(self.session, None)
        done.add(self.session)

        # Notify HTTP thread
        if self.session in pending:
            pending[self.session].set()


############################################################ SESSION HELPERS ##
def get_session(*session):
    if session not in sessions:
        sessions[session] = Session(*session)
    return sessions[session]


############################################################ HANDLE REQUEST ##
def handle_request(udp):
    req = Message.from_socket(udp).as_type(Type.REQ)

    wallet_id = None

    # Identify wallet by signature
    for w in Address.WALLETS:
        try:
            req.apply(keys[w].unsign)
            wallet_id = w
            break
        except Exception:
            continue

    if wallet_id is None:
        return

    # Decrypt request
    req.apply(keys["self"].decrypt)
    r, port = req.get_fields(int, int)

    ack_address = req.address, port

    # Send ACK back
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_ack:
        tcp_ack.settimeout(Time.TIMEOUT)
        tcp_ack.bind((NODE_ADDR[0], 0))

        try:
            tcp_ack.connect(ack_address)

            ack = concat(
                Type.ACK,
                keys[wallet_id].encrypt(NODE_ID, r),
            )

            tcp_ack.send(ack)

        except Exception:
            return


############################################################ HANDLE VALIDATOR ##
def handle_validator(tcp):
    tcp_val, _ = tcp.accept()

    with tcp_val:
        msg = Message.from_socket(tcp_val)
        msg.apply(keys["validators"].decrypt)

    wallet_id, session_id = msg.get_fields(str, int)

    if (wallet_id, session_id) in done:
        return

    session = get_session(wallet_id, session_id)

    ######################################################## HANDLE TKN ##
    if msg.type == Type.TKN:
        tkn = msg.as_type(Type.TKN)
        session.set_data(tkn.body)

        tkn.apply(keys[wallet_id].unsign)
        data = tkn.as_json()

        decision = Type.TKN

        now = time.time()
        delta = data["timestamp"] - now

        # Validate timestamp
        if delta < -30 or delta > 30:
            print("Reject! Bad timestamp.")
            decision = Type.BAD

        # Validate rotation math
        else:
            expected_diff = abs(
                (data["angle_deg"] - data["prev_angle_deg"] + 180) % 360 - 180
            )

            if abs(expected_diff - data["angle_change_deg"]) > 2:
                print("Reject! Angles do not match.")
                decision = Type.BAD

        session.add_decision(NODE_ID, decision)

        # Send vote to other validators
        if not session.consensus:
            val = concat(
                Type.VAL,
                keys["validators"].encrypt(
                    wallet_id,
                    session_id,
                    NODE_ID,
                    decision,
                ),
            )
            send_others(val)

    ######################################################## HANDLE VAL ##
    elif msg.type == Type.VAL:
        val = msg.as_type(Type.VAL)
        validator_id, decision = val.get_fields(str, Type)
        session.add_decision(validator_id, decision)

    ######################################################## HANDLE DON ##
    elif msg.type == Type.DON:
        don = msg.as_type(Type.DON)
        validator_id, decision, timestamp = don.get_fields(str, Type, float)
        session.add_consensus(validator_id, decision, timestamp)


############################################################ NETWORK SEND ##
def send_all(msg):
    for v in Address.VALIDATORS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_v:
                tcp_v.connect(Address.VALIDATORS[v])
                tcp_v.send(msg)
        except Exception:
            pass


def send_others(msg):
    for v in Address.VALIDATORS:
        if v == NODE_ID:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_v:
                tcp_v.connect(Address.VALIDATORS[v])
                tcp_v.send(msg)
        except Exception:
            pass


############################################################ MAIN POLL LOOP ##
def poll(address):
    # UDP socket (sensor discovery)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        udp.bind(Address.BROADCAST)
    except OSError:
        # Windows fix
        udp.bind(("0.0.0.0", Address.BROADCAST[1]))

    # TCP socket (validator communication)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(address)
    tcp.listen()

    sockets = [udp, tcp]

    while True:
        try:
            ready, _, _ = select.select(sockets, [], [], 0)

            for s in ready:
                if s == udp:
                    handle_request(udp)
                else:
                    handle_validator(tcp)

            time.sleep(Time.POLL)

        except AppException as e:
            print(e)


if __name__ == "__main__":
    poll(NODE_ADDR)
