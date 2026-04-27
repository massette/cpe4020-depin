import time
import json
import requests
import os
from pathlib import Path
from datetime import datetime
import math
import sys
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# Pi 5 uses smbus2 directly instead of board/busio
import smbus2
import adafruit_mpu6050
import busio
import board

# --- CONFIG STUFF ---
# change the URL or literally nothing works lol
VALIDATOR_URL = "placeholder"  # set real URL
# how many coins we get per shake/rotation event, free money basically
COINS_PER_EVENT = 10
# cooldown between events so we can't just spam it and get infinite coins
MIN_EVENT_GAP = 3.0                # seconds
# how many degrees the lock needs to rotate to count as a "real" move
# too low = false positives from just breathing near it
ROTATION_THRESHOLD_MIN = 30        # degrees
ROTATION_THRESHOLD_MAX = 180
# where we save our crypto wallet key so we don't lose our money on reboot
WALLET_PATH = Path("wallet.pem")
# how long to wait if i2c dies before trying again
I2C_RETRY_DELAY = 2.0
# dont wait forever for the server to respond
REQUEST_TIMEOUT = 5.0

# Pi 5 uses bus 1, dont change this unless you know what ur doing
I2C_BUS = 1
MPU6050_ADDR = 0x68  # default address for the sensor, look it up

# --- WALLET CLASS ---
# this handles our crypto keys so we can prove its actually us sending the coin requests
# basically if you delete wallet.pem you lose your identity, don't do that
class PiWallet:
    def __init__(self, path: Path = WALLET_PATH):
        self.path = path
        # if we already have a key saved, just load it back up
        if self.path.exists():
            with open(self.path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(f.read(), password=None)
            print("Loaded existing Pi wallet key.")
        else:
            # first time running - gotta make a brand new key pair
            self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            # save the key to disk so we don't lose it on restart
            with open(self.path, "wb") as f:
                f.write(pem)
            try:
                # make it so only we can read the key file, security 101
                os.chmod(self.path, 0o600)
            except Exception:
                pass  # windows probably, whatever
            print(f"Created new Pi wallet and saved key to {self.path}")

        # derive the public key from the private key (math magic)
        self.public_key = self.private_key.public_key()
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        # hash the public key to get our "address" - like a username but cryptographic
        h = hashes.Hash(hashes.SHA256())
        h.update(pub_bytes)
        self.address = h.finalize().hex()
        self.pub_pem = pub_bytes.decode('utf-8')
        print(f"Pi Wallet Address: {self.address}")

    def sign_message(self, message_dict):
        # turn the dict into bytes so we can sign it
        # sort_keys=True so the signature is always the same for same data
        message_bytes = json.dumps(message_dict, sort_keys=True).encode('utf-8')
        # sign it with our private key - proves it came from us
        signature = self.private_key.sign(
            message_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return signature

# --- SENSOR SETUP ---
# try to connect to the gyroscope/accelerometer and die loudly if we can't
# no point running the program without the sensor lmao
def init_mpu_or_exit():
    try:
        # Pi 5 needs explicit I2C bus initialization (Pi 4 was different, found out the hard way)
        i2c = busio.I2C(board.SCL, board.SDA)

        # gotta wait for the i2c bus to actually be available before we grab it
        timeout = time.time() + 5.0
        while not i2c.try_lock():
            if time.time() > timeout:
                raise RuntimeError("I2C bus lock timeout")
            time.sleep(0.01)
        i2c.unlock()

        mpu = adafruit_mpu6050.MPU6050(i2c)

        # sensor needs a sec to chill out after waking up
        time.sleep(0.5)

        print("MPU6050 initialized.")
        return mpu
    except Exception as e:
        # something went wrong, print helpful stuff and just exit
        print(f"Failed to initialize MPU6050: {e}")
        print("Tips:")
        print("  1. Check I2C is enabled: sudo raspi-config -> Interface Options -> I2C")
        print("  2. Check wiring: SDA->Pin3, SCL->Pin5, VCC->Pin1, GND->Pin6")
        print("  3. Check sensor detected: i2cdetect -y 1 (should show 68)")
        sys.exit(1)

# --- MATH HELPERS ---
# convert raw accelerometer x/y into an angle in degrees (0-360)
# basically asking "which way is gravity pulling" = which way is it tilted
def accel_to_angle(ax, ay):
    ang = math.degrees(math.atan2(ay, ax)) % 360
    return ang

# figure out the shortest angle between two directions
# needed because going from 350° to 10° is only 20°, not 340°
def angular_diff(a, b):
    return abs((a - b + 180) % 360 - 180)

# wrapper to just get the current angle in one line
def get_current_angle(mpu):
    ax, ay, az = mpu.acceleration
    return accel_to_angle(ax, ay)

# --- MAIN LOOP ---
print("Starting mamabeanie on Raspberry Pi 5...")

# boot up the sensor, exits the whole program if it fails
mpu = init_mpu_or_exit()
wallet = PiWallet()

# take 8 readings at startup and average them for a stable baseline angle
# one reading can be noisy, 8 is better
SAMPLES_INIT = 8
angles = []
for _ in range(SAMPLES_INIT):
    angles.append(get_current_angle(mpu))
    time.sleep(0.05)
prev_angle = sum(angles) / len(angles)
print(f"Initial angle set to {prev_angle:.1f}°")

last_event_time = 0.0
print("Waiting for lock rotation...")

# infinite loop, this runs forever until you ctrl+c it
while True:
    try:
        current_angle = get_current_angle(mpu)
    except Exception as e:
        # sensor glitched out, just wait and try again instead of crashing
        print(f"Sensor read error: {e}")
        print("Retrying in 2 seconds...")
        time.sleep(I2C_RETRY_DELAY)
        continue  # skip the rest of the loop and try again

    diff = angular_diff(current_angle, prev_angle)
    now = time.time()

    # check if the rotation is big enough AND we're past the cooldown
    if (ROTATION_THRESHOLD_MIN <= diff <= ROTATION_THRESHOLD_MAX and
        (now - last_event_time) > MIN_EVENT_GAP):

        print(f"Lock rotation detected! Change: {diff:.1f}° (prev {prev_angle:.1f} -> now {current_angle:.1f})")

        # build the payload we're gonna send to the validator
        # includes all the juicy data about what happened + who we are
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

        # sign the payload so the server knows it's legit and not spoofed
        signature = wallet.sign_message(payload)
        payload["signature"] = signature.hex()

        # try to send it up to 3 times with exponential backoff
        # because networks are trash sometimes
        try_count = 0
        max_tries = 3
        backoff = 1.0  # wait 1s, then 2s, then 4s between retries
        sent_ok = False
        while try_count < max_tries and not sent_ok:
            try:
                resp = requests.post(VALIDATOR_URL, json=payload, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    # we got paid let's gooo
                    print(f"Mint request accepted; requested {COINS_PER_EVENT} coins.")
                    last_event_time = now
                    sent_ok = True
                else:
                    # server said no for some reason, log it and retry
                    print(f"Validator rejected: [{resp.status_code}] {resp.text}")
                    try_count += 1
                    time.sleep(backoff)
                    backoff *= 2  # wait longer each time
            except Exception as e:
                # network died or timed out
                print(f"Network error sending to validator: {e}")
                try_count += 1
                time.sleep(backoff)
                backoff *= 2
        if not sent_ok:
            # gave up after 3 tries, oh well, maybe next rotation
            print("Failed to send mint request after retries.")

    # update the baseline angle every loop tick
    prev_angle = current_angle
    # poll 10 times per second, don't need faster than that
    time.sleep(0.1)
