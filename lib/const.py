from enum import Enum

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
    BROADCAST = ("127.0.0.255", 6560)

    VALIDATORS = {
        "V01": ("127.0.0.1", 6561),
        "V02": ("127.0.0.1", 6562),
        "V03": ("127.0.0.1", 6563),
    }

    WALLETS = {
        "W01": ("127.0.0.1", 0),
    }
