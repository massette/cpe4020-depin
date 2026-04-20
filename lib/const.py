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
    HOST = ipaddress.ip_interface("11.24.7.244/21")
    HOST_IP = str(HOST.ip)
    HOST_NETWORK = str(HOST.network)
    HOST_BROADCAST = str(HOST.network.broadcast_address)

    VALIDATORS = {
        "V01": (HOST_IP, 6562),
        "V02": (HOST_IP, 6563),
        "V03": (HOST_IP, 6564),
    }

    WALLETS = {
        "W01": (HOST_IP, 0),
        "W02": (HOST_IP, 0),
    }

    BROADCAST = (HOST_BROADCAST, 6561)
