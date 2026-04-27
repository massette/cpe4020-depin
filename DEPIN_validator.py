import sys
import time
from datetime import datetime, timedelta
import socket
import select
import secrets
from threading import Thread, Event
from flask import Flask, request
from cryptography.exceptions import InvalidSignature

from lib.const import Time, Type, Address
from lib.parse import Message
from lib.bytes import concat

app = Flask(__name__)

################################################################ NODE DETAILS ##
# parse arguments
if len(sys.argv) < 2:
    print("USAGE: python {} <VALIDATOR ID>".format(sys.argv[0]))
    print()

    sys.exit(1)
elif sys.argv[1] not in Address.VALIDATORS:
    print(
        "Invalid ID {}, expected one of: {}".format(
            sys.argv[1],
            ", ".join(Address.VALIDATORS.keys())
        )
    )
    print()

    sys.exit(1)

NODE_ID = sys.argv[1]
NODE_ADDR = Address.VALIDATORS[NODE_ID]

################################################################ POLL SOCKETS ##
from listen import poll, send_all, keys, pending

# run on separate thread
sockets_thread = Thread(target=poll, args=(NODE_ADDR,))
sockets_thread.start()

###################################################################### ROUTES ##
@app.get("/")
def get_dashboard():
    return "dashboard :)", 200

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

    # 
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
        return "TKN", 200
    else:
        return "Request timed out.", 408

@app.get("/transactions")
def get_transactions():
    return {"data": "<the whole ledger>"}, 200

@app.get("/wallets")
def get_wallets():
    return {"data": "<list of all wallets>"}, 200

@app.get("/wallets/<key>")
def get_wallet(key):
    return {"data": "<list of everything owned by the wallet>"}, 200

############################################################### LAUNCH SERVER ##
app.run(host=Address.HOST_IP, port=6561)
