from lib.const import Type, Address
from lib.error import BadMessageException

import json
import struct
from enum import Enum

def next_sep(raw, separator=b"."):
    try:
        return raw.index(separator)
    except ValueError:
        return len(raw)

class Message:
    def __init__(self, socket):
        try:
            (self.raw, self.address) = socket.recvfrom(1024)
        except ValueError:
            raise BadMessageException(socket)

        self.socket = socket
        self.body = self.raw
        self.type = self.get_field(Type)

    def parse_type(self, *types):
        if self.type not in types:
            raise self.error("Type {} not allowed.".format(self.type))

        return self

    def apply(self, fn):
        self.body = fn(self.body)

        return self

    def get_field(self, typ):
        n = next_sep(self.body)
        (raw, self.body) = self.body[:n], self.body[n+1:]

        try:
            if typ == bytes:
                return raw
            elif typ == str:
                return raw.decode()
            elif issubclass(typ, Enum):
                return typ(struct.unpack(">B", raw)[0])
            elif typ == int:
                return struct.unpack(">I", raw)[0]
            elif typ == Address:
                parts = struct.unpack(">BBBBI", raw)
                address = ".".join(str(b) for b in parts[:4])
                port = parts[4]

                return (address, port)
        except (ValueError, struct.error):
            raise self.error("Malformed message body.")

    def get_fields(self, *types):
        return tuple(self.get_field(typ) for typ in types)

    def error(self, message):
        return BadMessageException(self.socket, self.address, message)
