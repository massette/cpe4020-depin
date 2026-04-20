from lib.const import Type, Address
from lib.error import BadMessageException

import json
import struct
import socket
from enum import Enum

def next_sep(raw, separator=b"."):
    try:
        return raw.index(separator)
    except ValueError:
        return len(raw)

class Message:
    def __init__(self, s):
        try:
            try:
                if s.type == socket.SOCK_STREAM:
                    self.raw = s.recv(1024)
                    self.address = s.getpeername()
                else:
                    (self.raw, self.address) = s.recvfrom(1024)
            except TimeoutError:
                return BadMessageException(s, None, "No message.")
                pass
        except ValueError:
            raise BadMessageException(s)

        self.socket = s
        self.body = self.raw
        self.type = self.get_field(Type)

    def as_json(self):
        return json.loads(self.body.decode())

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
        except (ValueError, struct.error):
            raise self.error("Malformed message body.")

    def get_fields(self, *types):
        return tuple(self.get_field(typ) for typ in types)

    def error(self, message):
        return BadMessageException(self.socket, self.address, message)
