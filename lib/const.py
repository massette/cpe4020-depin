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
    BROADCAST = ("11.31.7.255", 6561)

    VALIDATORS = {
        "V01": ("127.0.0.1", 6562),
        "V02": ("127.0.0.1", 6563),
        "V03": ("127.0.0.1", 6564),
    }

    WALLETS = {
        "W01": ("127.0.0.1", 0),
        "W02": ("127.0.0.1", 0),
    }
