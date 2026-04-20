import json
import struct
import socket
from enum import Enum

def to_bytes(part):
    if isinstance(part, bytes):
        return part
    elif isinstance(part, str):
        return part.encode()
    elif isinstance(part, Enum):
        return struct.pack(">B", part.value)
    elif isinstance(part, int):
        return struct.pack(">I", part)
    elif isinstance(part, dict):
        return json.dumps(part).encode()
    else:
        raise ValueError("Failed to convert part to bytes: " + str(part))

def concat(*parts, separator=b"."):
    return separator.join(tuple(to_bytes(part) for part in parts))

