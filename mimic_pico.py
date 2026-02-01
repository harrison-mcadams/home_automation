import serial
import time
import sys
import json
import os
import argparse

# Config
DEFAULT_PICO_PORT = "/dev/ttyACM0"
FILES_DIR = os.path.dirname(__file__)
CODES_FILE = os.path.join(FILES_DIR, "remote_codes.json")

def main():
    parser = argparse.ArgumentParser(description='Send RF codes via Pi Pico bridge')
    parser.add_argument('button', type=str, help="Button to fire (e.g. '1 ON')")
    parser.add_argument('-p', '--port', default=DEFAULT_PICO_PORT, help="Serial port of the Pico")
    args = parser.parse_args()

    # 1. Load the database
    if not os.path.exists(CODES_FILE):
        print(f"Error: {CODES_FILE} not found.")
        return

    with open(CODES_FILE, 'r') as f:
        codes_db = json.load(f)

    btn_key = args.button.upper()
    if btn_key not in codes_db:
        print(f"Error: Button '{btn_key}' not in database.")
        print(f"Available: {list(codes_db.keys())}")
        return

    data = codes_db[btn_key]
    code = data['code']
    proto = data.get('protocol', 1)
    pulse = data.get('pulselength', 150)

    # 2. Connect to Pico
    try:
        print(f"Connecting to Pico on {args.port}...")
        ser = serial.Serial(args.port, 115200, timeout=1)
        time.sleep(1) # Wait for handshake
        
        # 3. Send the command
        cmd = f"{code},{proto},{pulse}\n"
        print(f"🚀 Sending to Pico: {cmd.strip()}")
        ser.write(cmd.encode())
        
        # Wait for feedback
        response = ser.read_until(b"Done.").decode()
        print(f"Pico says: {response.strip()}")
        
        ser.close()
    except Exception as e:
        print(f"Serial Error: {e}")
        print("Tip: Is the Pico plugged in? Is /dev/ttyACM0 correct?")

if __name__ == "__main__":
    main()
