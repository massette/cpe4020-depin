import ipaddress
from enum import Enum

class Time:
    TIMEOUT = 15.00
    POLL = 0.10

class Type(Enum):
    REQ = 1 # 001
    ACK = 3 # 011
    TKN = 2 # 010
    VAL = 6 # 110
    DON = 7 # 111
    MOV = 5 # 101

    BAD = 0 # 000

    def __str__(self):
        return "'" + self.name + "'"

class Address:
    # shared validator host
    VALIDATOR_HOST = ipaddress.ip_interface("10.100.153.11/18")
    VALIDATOR_IP = str(VALIDATOR_HOST.ip)

    # derived network information
    NETWORK_IP = str(VALIDATOR_HOST.network)
    BROADCAST_IP = str(VALIDATOR_HOST.network.broadcast_address)

    # assign ports to validators
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

    WALLETS = ( "W01", "W02" )
    BROADCAST = (BROADCAST_IP, 6560)
