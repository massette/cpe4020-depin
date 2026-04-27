import ipaddress
from enum import Enum


############################################################ TIME SETTINGS ##
class Time:
    # How long validator waits for consensus
    TIMEOUT = 15.0

    # Polling speed for sockets
    POLL = 0.10


############################################################ MESSAGE TYPES ##
class Type(Enum):
    REQ = 1   # wallet → validator discovery request
    ACK = 3   # validator → wallet response
    TKN = 2   # mint request
    VAL = 6   # validator vote
    DON = 7   # final consensus message
    BAD = 0   # rejection

    def __str__(self):
        return "'" + self.name + "'"


############################################################ NETWORK CONFIG ##
class Address:
    # Raspberry Pi (sensor + validator V01)
    PI_HOST = ipaddress.ip_interface("10.167.29.157/24")
    PI_IP = str(PI_HOST.ip)

    # Your PC (validator V02)
    PC_HOST = ipaddress.ip_interface("10.167.29.34/24")
    PC_IP = str(PC_HOST.ip)

    # Network info (auto derived)
    NETWORK_IP = str(PI_HOST.network)
    BROADCAST_IP = str(PI_HOST.network.broadcast_address)

    ######################################################## VALIDATORS ##
    # These MUST match on BOTH machines
    VALIDATORS = {
        "V01": ("10.167.29.157", 6563),   # Raspberry Pi
        "V02": ("10.167.29.34", 6563),   # PC validator
    }

    ######################################################## WALLETS ##
    WALLETS = {
        "W01": (PI_IP, 6562),   # sensor wallet
    }

    ######################################################## DISCOVERY ##
    # UDP broadcast used for finding validators
    BROADCAST = (BROADCAST_IP, 6561)
