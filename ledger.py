import json
import os

from lib.keys import hash


############################################################ FILE LOCATION ##
# Ledger is stored locally as JSON
LEDGER_FILE = "ledger.json"

# Special source used for minting (not a real wallet)
MINT_SOURCE = "MINT"


############################################################ LOAD LEDGER ##
def load_ledger():
    # If no ledger exists yet, return empty list
    if not os.path.exists(LEDGER_FILE):
        return []

    # Read existing ledger from file
    with open(LEDGER_FILE, "r") as f:
        return json.load(f)


############################################################ SAVE LEDGER ##
def save_ledger(ledger):
    # Write ledger to file with readable formatting
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=4)


############################################################ JSON SAFETY ##
def make_json_safe(value):
    """
    Convert values that JSON cannot handle (like bytes)
    into safe formats (hex strings).
    """

    # Convert raw bytes → hex string
    if isinstance(value, bytes):
        return value.hex()

    # Recursively fix dictionaries
    if isinstance(value, dict):
        return {k: make_json_safe(v) for k, v in value.items()}

    # Recursively fix lists
    if isinstance(value, list):
        return [make_json_safe(v) for v in value]

    return value


############################################################ HASH BLOCK ##
def hash_block(block):
    """
    Create a hash of the block for blockchain integrity.
    """
    block_string = json.dumps(block, sort_keys=True)
    return hash(block_string)


############################################################ ADD BLOCK ##
def add_block(timestamp, from_wallet, to_wallet, validator_id, data, amount=10):
    """
    Add a new block to the ledger after consensus.
    """

    ledger = load_ledger()

    # Create new block structure
    block = {
        "index": len(ledger) + 1,
        "timestamp": timestamp,

        # Who sent tokens (MINT for sensor events)
        "from": make_json_safe(from_wallet),

        # Who receives tokens
        "to": make_json_safe(to_wallet),

        # Validator that finalized the block
        "validator": make_json_safe(validator_id),

        # Token amount
        "amount": amount,

        # Raw signed sensor data
        "data": make_json_safe(data),

        # Link to previous block (blockchain)
        "previous_hash": ledger[-1]["hash"] if ledger else hash("GENESIS"),
    }

    # Generate block hash
    block["hash"] = hash_block(block)

    # Append to ledger and save
    ledger.append(block)
    save_ledger(ledger)

    print("Block added to ledger.json")
    return block


############################################################ BALANCES ##
def get_balances():
    """
    Compute wallet balances from ledger history.
    """

    ledger = load_ledger()
    balances = {}

    for block in ledger:
        from_wallet = block.get("from")
        to_wallet = block.get("to")
        amount = block.get("amount", 0)

        # Ensure receiving wallet exists
        if to_wallet not in balances:
            balances[to_wallet] = 0

        # Subtract only if not minting
        if from_wallet not in (MINT_SOURCE, "4d494e54"):
            if from_wallet not in balances:
                balances[from_wallet] = 0
            balances[from_wallet] -= amount

        # Add to receiver
        balances[to_wallet] += amount

    return balances
