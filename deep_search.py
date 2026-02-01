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

# Verified settings
PROTO = 1
PULSE = 150

def main():
    parser = argparse.ArgumentParser(description='Deep Search for lost RF buttons.')
    parser.add_argument('button', type=str, help="Button to search (e.g. '3 ON')")
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin")
    args = parser.parse_args()
    
    if not os.path.exists(CODES_FILE):
        print("Error: remote_codes.json not found.")
        sys.exit(1)
        
    with open(CODES_FILE, 'r') as f:
        data = json.load(f)
        
    key = args.button.upper()
    if key not in data:
        print(f"Button '{key}' not found in file.")
        sys.exit(1)
        
    sniffed_code = data[key]['code']
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    print(f"🕵️  DEEP SEARCH for [{key}]")
    print(f"Sniffed Center: {sniffed_code}")
    print(f"Settings: Proto {PROTO}, Pulse {PULSE}")
    print("------------------------------------------------")
    print("Searching wide range (+/- 2000)...")
    print("Press Ctrl+C IMMEDIATELY when the outlet reacts!")
    
    # Wide sweep
    start_code = sniffed_code - 2000
    end_code = sniffed_code + 2000
    
    step = 1
    # Optimization: Maybe step by 2 if we assume standard spacing? 
    # No, let's overlap to be sure.
    
    try:
        rfdevice.tx_repeat = 5 # Fast repeat to cover ground
        
        for code in range(start_code, end_code + 1, step):
            if code % 10 == 0:
                print(f"👉 Scanning: {code} (Offset: {code - sniffed_code:+d})", end='\r')
                
            rfdevice.tx_code(code, PROTO, PULSE)
            # Very short sleep - we relying on user reaction + backtracking
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 STOPPED at ~{code}!")
        print("Entering FINE TUNE mode to pinpoint it.")
        
        current_code = code - 50 # Backtrack 50 to cover reaction time
        
        print(" Controls:")
        print("  [a] -1  (Previous)")
        print("  [d] +1  (Next)")
        print("  [s] FIRE Current")
        print("  [w] Sweep Small (+/- 5)")
        print("  [y] SAVE this code")
        
        while True:
            cmd = input(f"\rCurrent: {current_code} > ").strip().lower()
            
            if cmd == 'a': current_code -= 1
            elif cmd == 'd': current_code += 1
            elif cmd == 's': 
                rfdevice.tx_repeat = 15
                rfdevice.tx_code(current_code, PROTO, PULSE)
                print(" Fired.")
            elif cmd == 'w':
                print(" Sweeping local...")
                for c in range(current_code-5, current_code+6):
                    rfdevice.tx_code(c, PROTO, PULSE)
                    time.sleep(0.1)
            elif cmd == 'y' or cmd == 'save':
                print(f"💾 Saving {current_code} for [{key}]...")
                data[key]['code'] = current_code
                with open(CODES_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                return
                
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
