import sys
import secrets
from threading import Thread, Event

from flask import Flask, request
from cryptography.exceptions import InvalidSignature

# ✅ cleaned import (combined)
from lib.const import Time, Type, Address

from lib.bytes import concat
from ledger import load_ledger, get_balances

app = Flask(__name__)


################################################################ NODE DETAILS ##
# Must run as:
#   python3 DEPIN_validator.py V01
#   python  DEPIN_validator.py V02
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
# Import after NODE_ID exists because listen.py also reads sys.argv[1]
from listen import poll, send_all, keys, pending

# Start validator TCP/UDP network listener in background
sockets_thread = Thread(target=poll, args=(NODE_ADDR,))
sockets_thread.daemon = True
sockets_thread.start()


###################################################################### ROUTES ##
@app.get("/")
def get_dashboard():
    return """
    <h1>DePIN Validator Dashboard</h1>
    <p>Validator is running.</p>
    <ul>
        <li><a href="/transactions">Transactions</a></li>
        <li><a href="/wallets">Wallet Balances</a></li>
    </ul>
    """, 200


@app.post("/mint")
def post_transaction():
    # Raw signed payload from sensor/wallet
    payload = request.data

    # Check signature against known wallet public keys
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

    # Create a unique validation session
    session_id = secrets.randbits(32)

    while (wallet_id, session_id) in pending:
        session_id = secrets.randbits(32)

    pending[wallet_id, session_id] = Event()

    # Package the signed mint request as a validator token message
    tkn = concat(
        Type.TKN,
        keys["validators"].encrypt(wallet_id, session_id, payload)
    )

    # Send token request to all validators: V01 and V02
    send_all(tkn)

    # Wait until validator consensus finishes
    is_done = pending[wallet_id, session_id].wait(Time.TIMEOUT)

    # Clean up pending request
    pending.pop((wallet_id, session_id), None)

    if is_done:
        return "TKN", 200
    else:
        return "Request timed out.", 408


@app.get("/transactions")
def get_transactions():
    return {"data": load_ledger()}, 200


@app.get("/wallets")
def get_wallets():
    return {"data": get_balances()}, 200


@app.get("/wallets/<key>")
def get_wallet(key):
    balances = get_balances()
    return {
        "wallet": key,
        "balance": balances.get(key, 0)
    }, 200


############################################################### LAUNCH SERVER ##
# Flask dashboard/API port
# Each machine can use 6561 because each has a different IP.
app.run(host="0.0.0.0", port=6561)
