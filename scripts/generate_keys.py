from lib.const import Address

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from cryptography.fernet import Fernet

import secrets

def make_sym(name):
    filename = "keys/{}.sym".format(name)
    key = Fernet.generate_key()

    with open(filename, "wb") as f:
        f.write(key)

def make_rsa(name):
    prv = "keys/{}.prv.pem".format(name)
    pub = "keys/{}.pub.pem".format(name)

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    with open(prv, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with open(pub, "wb") as f:
        f.write(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

if __name__ == "__main__":
    # validator keys
    make_rsa("validator")
    make_sym("validator")

    # wallet keys
    for w in Address.WALLETS:
        make_rsa(w)
