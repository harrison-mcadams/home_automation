#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17
CODES_FILE = os.path.join(os.path.dirname(__file__), "remote_codes.json")

def main():
    parser = argparse.ArgumentParser(description='Mimic an RF remote button press.')
    parser.add_argument('button', type=str, help="Button name (e.g., '1 ON', '3 OFF')")
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX,
                        help="GPIO pin (Default: 17)")
    parser.add_argument('-r', '--repeat', dest='repeat', type=int, default=20,
                        help="Repeat count (Default: 20)")
    parser.add_argument('--blast', dest='blast', action='store_true',
                        help="Send a blast of signals with varying pulse lengths to ensure reception.")
    args = parser.parse_args()

    # Load codes
    if not os.path.exists(CODES_FILE):
        print(f"Error: Codes file not found at {CODES_FILE}")
        print("Please run sniff_remote.py first.")
        sys.exit(1)

    with open(CODES_FILE, 'r') as f:
        codes_db = json.load(f)

    # Normalize input
    btn_key = args.button.upper() 
    if btn_key not in codes_db:
        matches = [k for k in codes_db.keys() if k.upper() == btn_key]
        if matches:
            btn_key = matches[0]
        else:
            print(f"Error: Button '{args.button}' not found in database.")
            print("Available buttons:", ", ".join(sorted(codes_db.keys())))
            sys.exit(1)

    data = codes_db[btn_key]
    
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    code = data['code']
    # PRECISE TRANSMISSION MODE
    # The user has calibrated the codes using calibrate_codes.py.
    # We trust the JSON file contains the exact integer needed.
    # No blasts. No sweeps. Just the sniper shot.
    
    if args.blast:
        print(f"⚠️  Note: Blast mode requested, but we are using PRECISE CALIBRATED CODE.")
        rfdevice.tx_repeat = 30 # Extra repeats just for reliability
    else:
        rfdevice.tx_repeat = 15 # Standard
        
    logging.info(f"Sending [{btn_key}]...")
    print(f"📡 Transmitting: Code={code}, Pulse=150, Proto=1, Repeat={rfdevice.tx_repeat}")
    
    # Verified: Protocol 1, Pulse 150
    rfdevice.tx_code(code, 1, 150)
    
    rfdevice.cleanup()
    print("Done.")

if __name__ == "__main__":
    main()
