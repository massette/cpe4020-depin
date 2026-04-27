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
    # your Raspberry Pi (sensor + validator V01)
    PI_HOST = ipaddress.ip_interface("10.167.29.157/24")
    PI_IP = str(PI_HOST.ip)

    # your computer (validator V02)
    PC_HOST = ipaddress.ip_interface("10.167.29.119/24")
    PC_IP = str(PC_HOST.ip)

    # network info
    NETWORK_IP = str(PI_HOST.network)
    BROADCAST_IP = str(PI_HOST.network.broadcast_address)

    # ✅ VALIDATORS (MUST MATCH ON BOTH MACHINES)
    VALIDATORS = {
        "V01": ("10.167.29.157", 6560),  # Pi
        "V02": ("10.167.29.34", 6560),  # your computer
    }

    # wallet (sensor node)
    WALLETS = {
        "W01": ("10.167.29.157", 6562),
    }

    # UDP broadcast for discovery
    BROADCAST = (BROADCAST_IP, 6561)
