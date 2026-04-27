from flask import Flask, jsonify, render_template, request
import time
import random

app = Flask(__name__)


wallets = [
    {"address": "node1", "balance": 50},
    {"address": "node2", "balance": 20}
]

transactions = []
activity_log = []

validators = ["V01", "V02", "V03"]


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/wallets")
def get_wallets():
    return jsonify(wallets)

@app.route("/transactions")
def get_transactions():
    return jsonify(transactions)

@app.route("/activity")
def get_activity():
    return jsonify(activity_log)

@app.route("/validators")
def get_validators():
    return jsonify(validators)


@app.route("/mint", methods=["POST"])
def mint():
    data = request.json

    # pick validator (simulated consensus)
    validator = random.choice(validators)

    # create transaction
    tx = {
        "from": data["from"],
        "to": data["to"],
        "amount": data["amount"],
        "timestamp": time.time(),
        "validator": validator
    }
    transactions.insert(0, tx)

    # update wallet
    found = False
    for w in wallets:
        if w["address"] == data["to"]:
            w["balance"] += data["amount"]
            found = True

    if not found:
        wallets.append({
            "address": data["to"],
            "balance": data["amount"]
        })

    # activity log
    activity_log.insert(0, f"{validator} approved mint → {data['amount']} coins to {data['to']}")

    return {"status": "ok"}

# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
