from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key, Encoding, PublicFormat

from cryptography.fernet import Fernet

from lib.bytes import concat

class Public:
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = load_pem_public_key(f.read())

    def reveal(self):
        return self.key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )

    def encrypt(self, *parts):
        return self.key.encrypt(
            concat(*parts),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def unsign(self, message):
        signature = message[-256:]
        message = message[:-257]

        self.key.verify(
            signature, message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        return message

class Private:
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = load_pem_private_key(
                f.read(),
                password=None
            )

    def sign(self, *parts):
        message = concat(*parts)
        
        return concat(
            message,
            self.key.sign(
                message, padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        )

    def decrypt(self, ciphertext):
        return self.key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

class Symmetric:
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = f.read()

        self.cipher = Fernet(self.key)

    def encrypt(self, *parts):
        return self.cipher.encrypt(concat(*parts))

    def decrypt(self, ciphertext):
        return self.cipher.decrypt(ciphertext)
