#!/usr/bin/env python3

import argparse
import time
import json
import os
import sys
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17
FILES_DIR = os.path.dirname(__file__)
CODES_FILE = os.path.join(FILES_DIR, "remote_codes.json")

# Verified settings (Button 1)
PROTO = 1
PULSE = 150

# We know Button 1 is at ~4478259.
# Sniffer saw Button 4 down at ~4474113.
# The "Safe Zone" seems to be 4470000 to 4480000.
# That is 10,000 codes.
# At 50 codes/sec, that is 200 seconds (~3 mins).

START_CODE = 4470000
END_CODE   = 4480000

def save_code(data, code, btn_hint="UNKNOWN"):
    # Save as a temporary finding
    key = f"FOUND_{code}"
    print(f"\n💾 Saving recovered code {code} as '{key}'...")
    
    # Try to guess which button it is based on user input?
    real_name = input(f"Which button did this activate? (e.g. '3 ON') [Default: {key}]: ").strip().upper()
    if real_name:
        key = real_name
        
    data[key] = {
        "code": code,
        "protocol": PROTO,
        "pulselength": PULSE
    }
    
    with open(CODES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description='Full Spectrum Sweep.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin")
    parser.add_argument('--start', type=int, default=START_CODE, help=f"Start Code (Def: {START_CODE})")
    parser.add_argument('--end', type=int, default=END_CODE, help=f"End Code (Def: {END_CODE})")
    args = parser.parse_args()
    
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    # Load existing to save correctly later
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {}

    print(f"🌌 FULL SPECTRUM SWEEP")
    print(f"Scanning from {args.start} to {args.end}")
    print(f"Est time: {(args.end - args.start) / 40 / 60:.1f} minutes.")
    print("ALL BUTTONS might activate. Watch EVERYTHING.")
    print("Press Ctrl+C IMMEDIATELY when ANY outlet clicks!")
    print("------------------------------------------------")
    
    last_sent = 0
    try:
        # High speed mode
        rfdevice.tx_repeat = 4 
        
        # We step by 1 to be thorough.
        for code in range(args.start, args.end + 1):
            last_sent = code
            if code % 100 == 0:
                 print(f"👉 Scanning: {code} ...", end='\r')
                 
            rfdevice.tx_code(code, PROTO, PULSE)
            # No sleep needed really if tx_repeat is small, the library takes time
            # But let's add tiny delay to breathe
            # time.sleep(0.005)
            
        print("\n❌ Completed sweep.")
        
    except KeyboardInterrupt:
        print(f"\n\n🛑 STOPPED at ~{last_sent}!")
        print("Entering FINE TUNE mode.")
        
        current_code = last_sent - 10 # Backtrack 
        
        print(" Controls:")
        print("  [a] -1")
        print("  [d] +1")
        print("  [s] FIRE")
        print("  [y] SAVE")
        
        while True:
            cmd = input(f"\rCurrent: {current_code} > ").strip().lower()
            if cmd == 'a': current_code -= 1
            elif cmd == 'd': current_code += 1
            elif cmd == 's': 
                rfdevice.tx_repeat = 15
                rfdevice.tx_code(current_code, PROTO, PULSE)
                print(" Fired.")
            elif cmd == 'y' or cmd == 'save':
                save_code(data, current_code)
                return
                
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
