from flask import Flask, jsonify, render_template, request
import time
import random

from lib.const import Address
from lib.keys import Public

from ledger import load_ledger

app = Flask(__name__)

# initialize validators
validators = Address.VALIDATORS.keys()

# initialize wallets
wallets = {}

for w in Address.WALLETS:
    addr = Public("keys/{}.pub.pem".format(w)).reveal()
    wallets[addr] = 0

# load previous transactions
def update_transactions():
    global transactions = load_ledger()

    for block in transactions:
        if block["from"] != "MINT":
            wallets[block["from"]] -= block["amount"]
        
        wallets[block["to"]] += block["amount"]


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
        update_transactions()
        return jsonify(transactions[-1]), 200
    else:
        return "Request timed out.", 408

@app.route("/wallets")
def get_wallets():
    return jsonify(wallets)

@app.route("/transactions")
def get_transactions():
    return jsonify(transactions)

@app.route("/validators")
def get_validators():
    return jsonify(validators)

# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
