import ipaddress
from enum import Enum

class Time:
    TIMEOUT = 15.00
    POLL = 0.10

class Type(Enum):
    REQ = 1
    ACK = 3
    TKN = 2
    VAL = 6
    DON = 7

    BAD = 0

    def __str__(self):
        return "'" + self.name + "'"

class Address:
    # address of pi miner
    PI_HOST = ipaddress.ip_interface("10.167.29.119/24")
    PI_IP = str(PI_HOST.ip)

    # address of other wallet
    OTHER_HOST = ipaddress.ip_interface("10.167.29.119/24")
    OTHER_IP = str(OTHER_HOST.ip)

    # shared address of validators
    VALIDATOR_HOST = ipaddress.ip_interface("10.100.153.11/18")
    VALIDATOR_IP = str(VALIDATOR_HOST.ip)

    # derived network information
    NETWORK_IP = str(VALIDATOR_HOST.network)
    BROADCAST_IP = str(VALIDATOR_HOST.network.broadcast_address)

    VALIDATORS = {
        "V01": (VALIDATOR_IP, 6562),
        "V02": (VALIDATOR_IP, 6563),
        "V03": (VALIDATOR_IP, 6564),
#        "V04": (VALIDATOR_IP, 6565),
#        "V05": (VALIDATOR_IP, 6566),
#        "V06": (VALIDATOR_IP, 6567),
#        "V07": (VALIDATOR_IP, 6568),
#        "V08": (VALIDATOR_IP, 6569),
    }

    WALLETS = {
        "W01": (PI_IP, 0),
        "W02": (OTHER_IP, 0),
    }

    BROADCAST = (BROADCAST_IP, 6560)
