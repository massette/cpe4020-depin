# Lock Monitor with DePIN
Final project for CPE4020 Spring 2026. This represents a proof of concept for a system of sensors and validators to aggregate and reward data on the status of a rotational locks for estimating occupancy and usage of public restrooms.

## Setup
For this project, mining scripts have been tested on a Raspberry Pi 5 with connected MPU6050 to produce sensor readings. Validator scripts have been tested primarily on Debian 13.4 and Windows 11.

The main entry points are [DEPIN_validator](DEPIN_validator.py) and [DEPIN_sensor](DEPIN_sensor.py), depending on whether a node is acting as a validator or a wallet.

### Validator
A validator node is started by the command:
`python DEPIN_validator.py <VALIDATOR ID>`

Where `<VALIDATOR ID>` is an ID associated with a network address in `Address.VALIDATORS` of [lib/const](lib/const.py).

By default, this is one of: `V01`, `V02`, `V03`.

**NOTE: Although consensus only requires a majority, all validators must be running *and reachable* to approve any addition to the ledger.**

### Wallet
A wallet node with a connected sensor is started by the command:
`python DEPIN_sensor.py <WALLET ID>`

Where `<WALLET ID>` is an identifier with an associated private key on the device *and* public key at the validators.

By default, this is one of: `W01`, `W02`.

Recognized wallet keys are stored in `Address.WALLETS` of [lib/const](lib/const.py).

### Other scripts
Two utility scripts have been included in the [scripts/](scripts/) directory:
- [generate_keys](scripts/generate_keys.py) will generate all validator keys and key-pairs for two wallets (W01, W02). These keys will only be generated on the device running this script, and any existing keys will be overwritten.
- [route](scripts/route.py) is used to echo network traffic from one network interface to another (e.g. Wifi to Ethernet) to account for any insufficiencies in the hardware side of the network.

## Keys
The network uses a shared RSA key-pair (Kv-, Kv+) to authorize any wallet-validator interaction, as well as a shared symmetric key (Kvv) for additional confidentiallity on validator-validator interactions. A new RSA key-pair (Kw-, Kw+) must be generated for each wallet on the network, where a hash of the public key is then treated as the public "address" of the wallet for balance transfers and other API requests.

For purposes of authorization and confidentiality, it is assumed that only authorized validators know Kv- and Kvv and that only the wallet holder knows Kw-. This is not reflected in the structure of the project, where all nodes have access to all keys, but the code does uphold these assumptions.

Each validator expects access to the private validator key, as an unecrypted PEM at [keys/validator.prv.pem](keys/validator.prv.pem) and the symmetric key cypher as raw bytes at [keys/validator.sym](keys/validator.sym). Additionally, they must have a wallet's public key for it to be able to mint on the network.

A list of known wallets is stored in [lib/const.py](lib/const.py), where the public key should then be stored at `keys/<WALLET_ID>.pub.pem`.

Any minting wallet then requires access to the both its own private key (`keys/<WALLET_ID>.prv.pem`) and the validator public key ([keys/validator.pub.pem](keys/validator.pub.pem)).

In an actual distributed deployment, all keys not required by a device to operate should be removed from that device.

**Note: Validator IDs are only used to tie validator processes to known addresses and attribute additions in the ledger, they have no cryptographic meaning.**

## Messaging
### Ledger API
Each validator hosts an HTTP server at port 6561 with the following endpoints.

**NOTE: For multiple validators on the same host, only one will host the server.**

#### (GET) /
Returns the [dashboard webpage](template/index.html), summarizing the current state of the network and any recent transactions.

#### (GET) /transactions
Returns the entire ledger in JSON format as an array of blocks.

#### (GET) /wallets
Returns the results of `/wallets/<addr>` for every wallet on the network.

#### (GET) /wallets/<addr>
Returns all transactions involving this wallet.

#### (GET) /validators
Returns the IDs of all validators on the network.

#### (POST) /mint
Attempts to mint a new token.

Request body should be a stream of raw bytes (`application/octet-stream`) representing the signed JSON payload, `M.Kw-(H(M))`.

### Validator Messaging
Communications between validators utilize a custom application-level messaging protocol built on top of raw TCP sockets.

Each message includes an arbitary number of fields separated by the ASCII ".". Because encrypted JSON data and encrypted byte streams may include the separator, they are always the last field of a message containing them.

Every message is prefixed with a 3-bit type indicating the context of the communication and the fields that follow.

#### Validator request (001, REQ)
`REQ.Kv+(R.PORT).Kw-(H(Kv+(R.PORT)))`

Received on port 6560.

Requests the address of a validator on the local network over UDP broadcast. *Only message that should be sent over a UDP socket.*

The message body is encrypted with the validator public key to ensure the response is coming from an authorized validator:
- R. A 32-bit nonce echoed in the responding ACK.
- PORT. TCP port to send the response on.

Additionally, there is a signed message digest for authentication and, incidentally, message integrity.

#### Acknowledge (011, ACK)
`ACK.Kw+(VALIDATOR_ID.R)`

Notifies node of a validator address. All subsequent wallet interaction with the validator should occur through the Ledger API.

Message body is encrypted with wallet key for confidentiality:
- VALIDATOR_ID. Internal ID of the responding validator.
- R. Nonce to mitigate replay attacks.

#### Mint request (010, TKN)
`TKN.Kvv(WALLET_ID.SESSION_ID.M.Kw-(H(M))`

Represents a packet of unvalidated data to mint a new token from.

Message body is encrypted with symmetric validator key to ensure both sender and receiver are authorized validators:
- WALLET_ID. ID of the public key to verify the signature with.
- SESSION_ID. Random integer used with wallet ID to uniquely identify request on all validators.
- M. JSON payload to be validated.

A signed message digest is included to authenticate the wallet and ensure message integrity.

**NOTE: Wallet ID is not the same as wallet address.**

#### Validator decision (110, VAL)
`VAL.Kvv(WALLET_ID.SESSION_ID.VALIDATOR_ID.DECISION)`

Represents an intermediate validator decision prior to consensus.

Message body is encrypted with symmetric validator key to ensure both sender and receiver are authorized validators:
- WALLET_ID. SESSION_ID. To identify the validator session this decision applies to.
- VALIDATOR_ID. Internal ID of the validator sending this decision.
- DECISION. A subtype representing whether the validator approved the action. BAD if validation was rejected, otherwise echoes the type of the requesting message.

#### Validator consensus (111, DON)
`DON.Kvv(WALLET_ID.SESSION_ID.VALIDATOR_ID.DECISION.TIMESTAMP)`

Represents a consensus at a remote validator.

Message body is encrypted with symmetric validator key to ensure both sender and receiver are authorized validators:
- Same form as VAL, with additional timestamp of consensus.

Once all validators have reached a consensus, the oldest decision is used to add a new block to the ledger.

#### Reject request (000, BAD)
`BAD`

Used exclusively to represent a rejected ledger action.
