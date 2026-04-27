#add this to import ledger "from ledger import add_block"
import json
import os

from lib.keys import hash

LEDGER_FILE = "ledger.json"


def load_ledger():
    if not os.path.exists(LEDGER_FILE):
        return []

    with open(LEDGER_FILE, "r") as f:
        return json.load(f)


def save_ledger(ledger):
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=4)


def hash_block(block):
    block_string = json.dumps(block_copy, sort_keys=True)
    return hash(block_string)


def add_block(timestamp, from_wallet, to_wallet, validator_id, data, amount=1):
    ledger = load_ledger()

    block = {
        "index": len(ledger) + 1,
        "timestamp": timestamp,
        "from": str(from_wallet),
        "to": str(to_wallet),
        "validator": validator_id,
        "amount": amount,
        "data": data,

        "previous_hash": pledger[-1]["hash"] if ledger else hash("GENESIS")
    }

    block["hash"] = hash_block(block)

    ledger.append(block)
    save_ledger(ledger)

    print("Block added to ledger.json")
    return block
