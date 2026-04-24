#mamabeanie
import time
import json
import requests
import os
from pathlib import Path
from datetime import datetime
import math
import sys


import board
import busio
import adafruit_mpu6050

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# Config
VALIDATOR_URL = "placeholder"  # set real URL
COINS_PER_EVENT = 10
MIN_EVENT_GAP = 3.0                # seconds
ROTATION_THRESHOLD_MIN = 30        # degrees (tunable)
ROTATION_THRESHOLD_MAX = 180
WALLET_PATH = Path("wallet.pem")
I2C_RETRY_DELAY = 2.0
REQUEST_TIMEOUT = 5.0

# Wallet with persistent RSA key
class PiWallet:
    def __init__(self, path: Path = WALLET_PATH):
        self.path = path
        if self.path.exists():
            with open(self.path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(f.read(), password=None)
            print("Loaded existing Pi wallet key.")
        else:
            self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            with open(self.path, "wb") as f:
                f.write(pem)
            try:
                os.chmod(self.path, 0o600)
            except Exception:
                pass
            print(f"Created new Pi wallet and saved key to {self.path}")

        self.public_key = self.private_key.public_key()
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        h = hashes.Hash(hashes.SHA256())
        h.update(pub_bytes)
        self.address = h.finalize().hex()[:16]
        self.pub_pem = pub_bytes.decode('utf-8')
        print(f"Pi Wallet Address: {self.address}")

    def sign_message(self, message_dict):
        message_bytes = json.dumps(message_dict, sort_keys=True).encode('utf-8')
        signature = self.private_key.sign(
            message_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return signature

# Initialize MPU6050
def init_mpu_or_exit():
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        
        t0 = time.time()
        while not i2c.try_lock() and (time.time() - t0) < 1.0:
            time.sleep(0.01)
        try:
            i2c.unlock()
        except Exception:
            pass
        mpu = adafruit_mpu6050.MPU6050(i2c)
        print("MPU6050 initialized.")
        return mpu
    except Exception as e:
        print(f"Failed to initialize MPU6050: {e}")
        sys.exit(1)

def accel_to_angle(ax, ay):
    ang = math.degrees(math.atan2(ay, ax)) % 360
    return ang
def angular_diff(a, b):
    return abs((a - b + 180) % 360 - 180)

def get_current_angle(mpu):
    ax, ay, az = mpu.acceleration
    return accel_to_angle(ax, ay)
mpu = init_mpu_or_exit()
wallet = PiWallet()
SAMPLES_INIT = 8
angles = []
for _ in range(SAMPLES_INIT):
    angles.append(get_current_angle(mpu))
    time.sleep(0.05)
prev_angle = sum(angles) / len(angles)
print(f"Initial angle set to {prev_angle:.1f}°")

last_event_time = 0.0

print("Waiting for lock rotation...")

while True:
    try:
        current_angle = get_current_angle(mpu)
    except Exception as e:
        print(f"Sensor read error: {e}")
       
        sys.exit(1)

    diff = angular_diff(current_angle, prev_angle)
    now = time.time()

    if (ROTATION_THRESHOLD_MIN <= diff <= ROTATION_THRESHOLD_MAX and
        (now - last_event_time) > MIN_EVENT_GAP):

        print(f"Lock rotation detected! Change: {diff:.1f}° (prev {prev_angle:.1f} -> now {current_angle:.1f})")

        payload = {
            "type": "mint",
            "from": "sensor_node",
            "to": wallet.address,
            "amount": COINS_PER_EVENT,
            "data": {
                "event": "lock_rotation",
                "angle_change_deg": round(diff, 1),
                "prev_angle_deg": round(prev_angle, 1),
                "angle_deg": round(current_angle, 1),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "timestamp": now,
            "pubkey_pem": wallet.pub_pem
        }

        signature = wallet.sign_message(payload)
        payload["signature"] = signature.hex()


        try_count = 0
        max_tries = 3
        backoff = 1.0
        sent_ok = False
        while try_count < max_tries and not sent_ok:
            try:
                resp = requests.post(VALIDATOR_URL, json=payload, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    print(f"Mint request accepted; requested {COINS_PER_EVENT} coins.")
                    last_event_time = now
                    sent_ok = True
                else:
                    print(f"Validator rejected: [{resp.status_code}] {resp.text}")
                    try_count += 1
                    time.sleep(backoff)
                    backoff *= 2
            except Exception as e:
                print(f"Network error sending to validator: {e}")
                try_count += 1
                time.sleep(backoff)
                backoff *= 2
        if not sent_ok:
            print("Failed to send mint request after retries.")

    prev_angle = current_angle
    time.sleep(0.1)
