import json
import requests
import os
import math
import sys
import time

# Pi 5 uses smbus2 directly instead of board like vro really...
import smbus2
import adafruit_mpu6050
import busio
import board

from lib.const import Address

# CONFIG STUFF goober
# how many coins we get per rotation event, free money basically
COINS_PER_EVENT = 10
# cooldown between events so we can't just spam it and get infinite coins
MIN_EVENT_GAP = 3.0                # seconds
# how many degrees the lock needs to rotate to count as a "real" move
# too low = false positives from just breathing near it
ROTATION_THRESHOLD_MIN = 30        # degrees
ROTATION_THRESHOLD_MAX = 180
# how long to wait if i2c dies before trying again
I2C_RETRY_DELAY = 2.0
# dont wait forever for the server to respond
REQUEST_TIMEOUT = 5.0

################################################################ NODE DETAILS ##
# parse arguments
if len(sys.argv) < 2:
    print("USAGE: python {} <WALLET ID>".format(sys.argv[0]))
    print()

    sys.exit(1)
elif sys.argv[1] not in Address.WALLETS:
    print(
        "Invalid ID {}, expected one of: {}".format(
            sys.argv[1], ", ".join(validators)
        )
    )
    print()

    sys.exit(1)

NODE_ID = sys.argv[1]

from send import request_validator

###################################################################### SENSOR ##
# Pi 5 uses bus 1, dont change this unless you know what ur doing
I2C_BUS = 1
MPU6050_ADDR = 0x68  # default address for the sensor, look it up

# WALLET KEY
from lib.keys import Private
key = Private("keys/{}.prv.pem".format(NODE_ID))

# SENSOR SETUP
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
        # something went wrong, print helpful stuff and just exit, need anymore assistance look youtube video with a indian guy
        print(f"Failed to initialize MPU6050: {e}")
        print("Tips:")
        print("  1. Check I2C is enabled: sudo raspi-config -> Interface Options -> I2C")
        print("  2. Check wiring: SDA->Pin3, SCL->Pin5, VCC->Pin1, GND->Pin6")
        print("  3. Check sensor detected: i2cdetect -y 1 (should show 68)")
        sys.exit(1)

# MATH STUFF
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

# MAIN LOOP
print("Starting mamabeanie on Raspberry Pi 5...")

# boot up the sensor, exits the whole program if it fails
mpu = init_mpu_or_exit()
# wallet = PiWallet()

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
        payload = {
            "node_id": NODE_ID,
            "event": "lock_rotation",
            "angle_change_deg": round(diff, 2),
            "prev_angle_deg": round(prev_angle, 2),
            "angle_deg": round(current_angle, 2),
            "timestamp": time.time(),
        }

        # sign the payload so the server knows it's legit and not spoofed
        payload = key.sign(payload)

        # try to send it up to 3 times with exponential backoff
        try_count = 0
        max_tries = 3
        backoff = 1.0
        sent_ok = False

        while try_count < max_tries and not sent_ok:
            try:
                addr = request_validator() # Address.VALIDATORS["V01"][0]
                mint_uri = "http://{}:6561/mint".format(addr)

                # FIX: use data=payload
                resp = requests.post(
                    mint_uri,
                    data=payload,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=REQUEST_TIMEOUT
                )

                if resp.status_code == 200:
                    print(f"Mint request accepted; requested {COINS_PER_EVENT} coins.")
                    last_event_time = now
                    sent_ok = True
                else:
                    print(f"Validator rejected: [{resp.status_code}] {resp.text}")

                    if resp.status_code == 400:
                        break
                    else
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
