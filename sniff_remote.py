#!/usr/bin/env python3

import argparse
import time
import json
import os
import sys
from rpi_rf import RFDevice

# Configuration
GPIO_RX = 27
BUTTONS = [
    "1 ON", "1 OFF", 
    "2 ON", "2 OFF", 
    "3 ON", "3 OFF", 
    "4 ON", "4 OFF", 
    "5 ON", "5 OFF"
]
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "remote_codes.json")

def capture_button(rfdevice, button_name):
    # We want to capture until we have a CONSISTENT set of data for Protocol 1
    valid_samples = []
    
    print(f"\n--- RECORDING: [{button_name}] ---")
    print(f"Please press the '{button_name}' button repeatedly (short presses)...")
    
    # Listen until we get 5 Good samples
    while len(valid_samples) < 5:
        if rfdevice.rx_code_timestamp:
            code = rfdevice.rx_code
            pulse = rfdevice.rx_pulselength
            proto = rfdevice.rx_proto
            
            # Reset timestamp to avoid re-reading same packet
            rfdevice.rx_code_timestamp = None
            
            # FILTER: Relaxed to accept what the remote ACTUALLY sends (Proto 5) 
            # or what it SHOULD send (Proto 1)
            
            # Case A: Ideal Etekcity (Proto 1, Short Pulse)
            if proto == 1 and 100 < pulse < 250:
                print(f"  ✅ Accepted (Ideal): Code={code} Pulse={pulse} Proto={proto}")
                valid_samples.append(code)
                
            # Case B: What your remote actually looks like to rpi-rf (Proto 5, Medium Pulse)
            elif proto == 5 and 350 < pulse < 550:
                print(f"  ✅ Accepted (Raw):   Code={code} Pulse={pulse} Proto={proto}")
                valid_samples.append(code)

            elif 100 < pulse < 600:
                 # Debug info for other things
                 # print(f"  ⚠️  Ignored:        Code={code} Pulse={pulse} Proto={proto}")
                 pass
        
        time.sleep(0.01)
    
    # Analyze - Find the MAX code (usually the most stable one in the +34 pair)
    # E.g. 225 vs 259. 259 is max.
    best_code = max(set(valid_samples), key=valid_samples.count)
    
    # Actually, let's take the NUMERICALLY higher one if there is a split, 
    # because typically the higher code (ending in 9 or 6) was the winner in our tests.
    unique_codes = list(set(valid_samples))
    unique_codes.sort()
    
    if len(unique_codes) > 1:
        print(f"  ℹ️  Saw multiple codes: {unique_codes}. Using highest: {unique_codes[-1]}")
        final_code = unique_codes[-1]
    else:
        final_code = unique_codes[0]

    result = {
        "code": final_code,
        "pulselength": 150, # FORCE 150 based on our findings
        "protocol": 1       # FORCE 1 based on our findings
    }
    print(f"💾 Locked in '{button_name}': {result}")
    time.sleep(1) 
    return result

def main():
    parser = argparse.ArgumentParser(description='Smart Sniffer for Etekcity.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_RX, help="GPIO pin (Default: 27)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_rx()
    
    codes_db = {}
    
    try:
        print("🚀 Etekcity Smart Sniffer Initialized.")
        print("We will ignore noise and focus on Protocol 1 / Pulse ~150.")
        
        for btn in BUTTONS:
            input(f"\nPress ENTER when ready to record [{btn}]...")
            # Clear buffer
            rfdevice.rx_code_timestamp = None 
            time.sleep(0.5)
            
            codes_db[btn] = capture_button(rfdevice, btn)
            
    except KeyboardInterrupt:
        print("\n\nStopping capture...")
    finally:
        rfdevice.cleanup()
    
    if codes_db:
        print(f"\nSaving codes to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(codes_db, f, indent=2)
        print("Done! You can now run mimic_remote.py straight away.")

if __name__ == "__main__":
    main()
