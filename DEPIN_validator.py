import sys
import time
import socket
import select
import secrets
from threading import Thread, Event
from flask import Flask, jsonify, render_template, request
from cryptography.exceptions import InvalidSignature

from lib.const import Time, Type, Address
from lib.keys import Public
from lib.parse import Message
from lib.bytes import concat

from ledger import load_ledger

app = Flask(__name__)

# initialize validators
validators = list(Address.VALIDATORS.keys())

# initialize wallets
wallets = {}
keys = {}

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

################################################################ NODE DETAILS ##
# parse arguments
if len(sys.argv) < 2:
    print("USAGE: python {} <VALIDATOR ID>".format(sys.argv[0]))
    print()

    sys.exit(1)
elif sys.argv[1] not in validators:
    print(
        "Invalid ID {}, expected one of: {}".format(
            sys.argv[1], ", ".join(validators)
        )
    )
    print()

    sys.exit(1)

NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]

################################################################ POLL SOCKETS ##
from listen import poll, send_all, pending

# run on separate thread
sockets_thread = Thread(target=poll, args=(NODE_ADDR,))
sockets_thread.start()

###################################################################### ROUTES ##
@app.route("/")
def home():
    return render_template("index.html")

@app.post("/mint")
def post_transaction():
    payload = request.data

    # check signature against each wallet key
    wallet_id = None

    for w in Address.WALLETS:
        try:
            keys[w].unsign(payload)
            wallet_id = w
            break
        except InvalidSignature:
            # wrong key, try again
            continue

    # fail if no key matched
    if wallet_id == None:
        return "Could not verify signature.", 400

    # generate unique session id
    session_id = secrets.randbits(32)

    while (wallet_id, session_id) in pending:
        session_id = secrets.randbits(32)

    # wait for response on other thread
    pending[wallet_id, session_id] = Event()

    # format signed mint request as TKN
    tkn = concat(
        Type.TKN,
        keys["validators"].encrypt(wallet_id, session_id, payload)
    )

    # echo TKN to all validators
    send_all(tkn)

    # await end of session
    is_done = pending[wallet_id, session_id].wait(Time.TIMEOUT)
    pending.pop((wallet_id, session_id))

    if is_done:
        update_transactions()
        return jsonify(transactions[-1]), 200
    else:
        return "Request timed out.", 408

@app.route("/wallets")
def get_wallets():
    return jsonify(wallets)

@app.route("/wallets/<addr>")
def get_wallet(addr):
    if addr in wallets:
        return wallets[addr], 200
    else:
        return "Wallet not found.", 404

@app.route("/transactions")
def get_transactions():
    return jsonify(transactions)

@app.route("/validators")
def get_validators():
    return jsonify(validators)

############################################################### LAUNCH SERVER ##
if __name__ == "__main__":
    app.run(debug=True, host=Address.VALIDATOR_IP, port=6561)
