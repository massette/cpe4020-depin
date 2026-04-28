import json
import sys
import os

from lib.keys import hash

LEDGER_PATH = "ledger.{}.json".format(sys.argv[1])

def load_ledger():
    if not os.path.exists(LEDGER_PATH):
        return []

    with open(LEDGER_PATH, "r") as f:
        return json.load(f)

def load_by_wallet(address):
    transactions = load_ledger()

    return [block for block in transactions
            if (block["to"] == address) or (block["from"] == address)]

def save_ledger(ledger):
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f)

def hash_block(block):
    block_string = json.dumps(block, sort_keys=True)
    return hash(block_string)

def add_block(timestamp, from_wallet, to_wallet, validator_id, data, amount=10):
    ledger = load_ledger()

    block = {
        "index": len(ledger) + 1,
        "timestamp": timestamp,
        "from": from_wallet,
        "to": to_wallet,
        "validator": validator_id,
        "amount": amount,
        "data": hash(data).hex(),

        "previous_hash": (
            (hash_block(ledger[-1]) if ledger else hash("GENESIS")).hex()
        ),
    }

    ledger.append(block)
    save_ledger(ledger)

    print("Block added to ledger.json")
    return block
