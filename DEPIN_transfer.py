import sys
import time
import requests

from lib.const import Address
from lib.keys import Public, Private

REQUEST_TIMEOUT = 5.0

######################################################################## ARGS ##
# parse arguments
if len(sys.argv) != 4:
    print("USAGE: python {} <WALLET ID> <TO_ADDRESS> <AMOUNT>".format(sys.argv[0]))
    print()

    sys.exit(1)

(NODE_ID, to_address, amount) = sys.argv[1:]

# check NODE ID
if NODE_ID not in Address.WALLETS:
    print(
        "Invalid ID {}, expected one of: {}".format(
            sys.argv[1], ", ".join(Address.WALLETS)
        )
    )
    print()

    sys.exit(1)

# check address
for w in Address.WALLETS:
    if to_address == Public("keys/{}.pub.pem".format(NODE_ID)).reveal():
        if NODE_ID == w:
            print("Circular transfer. Address should refer to a different wallet from the authorizing wallet.")
            print()

            sys.exit(1)

# check amount
try:
    amount = int(amount)

    if amount < 1:
        print("Amount must be positive.")
        print()

        sys.exit(1)
except ValueError:
    print("Transfer amount should be a positive integer.")

################################################################ SEND REQUEST ##
from send import request_validator

key = Private("keys/{}.prv.pem".format(NODE_ID))
addr = request_validator() # Address.VALIDATORS["V01"][0]
uri = "http://{}:6561/move".format(addr)

# generate payload
payload = {
    "node_id": NODE_ID,
    "timestamp": time.time(),
    "recipient": to_address,
    "amount": amount,
}
payload = key.sign(payload)

# send request
resp = requests.post(
    uri,
    data=payload,
    headers={"Content-Type": "application/octet-stream"},
    timeout=REQUEST_TIMEOUT
)
