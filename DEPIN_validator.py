import sys
import time
import socket
import select
import secrets
from threading import Thread, Event
from flask import Flask, jsonify, render_template, request
from cryptography.exceptions import InvalidSignature

from lib.const import Time, Type, Address
from lib.bytes import concat

app = Flask(
    __name__,
    template_folder="template",
    static_folder="static"
)

# initialize validators
validators = list(Address.VALIDATORS.keys())

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
from listen import (
    poll, send_all, # functions
    wallets, keys, pending, results # shared data
)

from ledger import load_ledger, load_by_wallet

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
        decision = results[wallet_id, session_id]

        if decision == Type.BAD:
            return "Invalid mint!", 500
        else:
            transaction = load_ledger()[-1]
            return jsonify(transaction), 200
    else:
        return "Timed out!", 408

@app.post("/move")
def post_move():
    payload = request.data

    # identify which wallet signed it
    wallet_id = None

    for w in Address.WALLETS:
        try:
            keys[w].unsign(payload)
            wallet_id = w
            break
        except InvalidSignature:
            continue

    if wallet_id is None:
        return "Could not verify signature.", 400

    # create session
    session_id = secrets.randbits(32)

    while (wallet_id, session_id) in pending:
        session_id = secrets.randbits(32)

    pending[wallet_id, session_id] = Event()

    # send EXACT payload to validators (just like mint)
    mov = concat(
        Type.MOV,
        keys["validators"].encrypt(wallet_id, session_id, payload)
    )

    send_all(mov)

    is_done = pending[wallet_id, session_id].wait(Time.TIMEOUT)
    pending.pop((wallet_id, session_id))

    if is_done:
        decision = results.pop(wallet_id, session_id)
        
        if decision == Type.BAD:
            return "Invalid move!", 500
        else:
            transaction = load_ledger()[-1]
            return jsonify(transaction), 200
    else:
        return "Timed out!", 408

@app.route("/wallets")
def get_wallets():
    transactions = {addr: load_by_wallet(addr) for addr in wallets}
    return jsonify(transactions)

@app.route("/wallets/<addr>")
def get_wallet(addr):
    if addr in wallets:
        return load_by_wallet(addr), 200
    else:
        return "Wallet not found.", 404

@app.route("/transactions")
def get_transactions():
    transactions = load_ledger()
    return jsonify(transactions)

@app.route("/validators")
def get_validators():
    return jsonify(validators)

############################################################### LAUNCH SERVER ##
# for multiple validators at the same address,
# only the first will host the http server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6561)
