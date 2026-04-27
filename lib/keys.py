from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key, Encoding, PublicFormat

from cryptography.fernet import Fernet

from lib.bytes import concat

# hash a list of byte-like objects with SHA256
def hash(*parts):
    message = concat(*parts)

    digest = hashes.Hash(hashes.SHA256())
    digest.update(message)

    return digest.finalize()

class Public:
    # load and manage the public key of an RSA key pair
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = load_pem_public_key(f.read())

    # convert the public key to a user-facing format
    def reveal(self):
        return hash(
            self.key.public_bytes(
                encoding=Encoding.PEM,
                format=PublicFormat.SubjectPublicKeyInfo
            )
        ).hex()

    # encrypt a list of byte-like objects with the key
    def encrypt(self, *parts):
        return self.key.encrypt(
            concat(*parts),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    # verify and consume a signature for a message in the form M . K-(H(M))
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
    # load and manage the private key of an RSA key pair
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = load_pem_private_key(
                f.read(),
                password=None
            )

    # encrypt and hash a list of byte-like objects and append to the message
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

    # decrypt a byte string with the key
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
    # load and manage a symmetric key with the Fernet module
    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.key = f.read()

        self.cipher = Fernet(self.key)

    # encrypt a list of byte-like objects with the key
    def encrypt(self, *parts):
        return self.cipher.encrypt(concat(*parts))

    # decrypt a byte string with the key
    def decrypt(self, ciphertext):
        return self.cipher.decrypt(ciphertext)

