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

def save_code(btn_key, code, data):
    print(f"💾 Saving [{btn_key}] with verified code: {code}")
    data[btn_key]['code'] = code
    data[btn_key]['protocol'] = PROTO
    data[btn_key]['pulselength'] = PULSE
    
    with open(CODES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def calibrate_button(rfdevice, btn_key, data):
    sniffed_code = data[btn_key]['code']
    print(f"\n🎯 Calibrating [{btn_key}] (Sniffed: {sniffed_code})")
    print("Press Ctrl+C IMMEDIATELY when the device reacts!")
    print("------------------------------------------------")
    
    # Sweep Range: Sniffed - 50 to Sniffed + 100
    # We found OFF was +23, ON was +34. But let's cover more ground.
    start_code = sniffed_code - 50
    end_code = sniffed_code + 100
    
    last_sent_code = None
    
    try:
        rfdevice.tx_repeat = 10 # Good repeat for reliable triggering
        
        for code in range(start_code, end_code + 1):
            last_sent_code = code
            print(f"👉 Testing: {code} (Offset: {code - sniffed_code:+d})", end='\r')
            rfdevice.tx_code(code, PROTO, PULSE)
            time.sleep(0.25) # Slow enough to react
            
        print("\n❌ Reached end of range without user interrupt.")
        return False
        
    except KeyboardInterrupt:
        print(f"\n\n🛑 STOPPED at {last_sent_code}!")
        
        print(f"\n\n🛑 STOPPED at ~{last_sent_code}!")
        print("Entering FINE TUNE mode.")
        print("-----------------------")
        print(" Controls:")
        print("  [a] -1  (Previous Code)")
        print("  [d] +1  (Next Code)")
        print("  [s] FIRE Current Code")
        print("  [w] Auto-Fire (Toggle)")
        print("  [Enter] SAVE and Exit")
        print("-----------------------")
        
        current_code = last_sent_code
        # Backtrack slightly by default since reaction time usually means we overshot
        current_code -= 2 
        
        auto_fire = False
        
        while True:
            # If auto_fire is on, send pulses repeatedly
            if auto_fire:
                rfdevice.tx_code(current_code, PROTO, PULSE)
                status = "🔥 FIRING"
                time.sleep(0.1)
            else:
                status = "  Ready"
                
            print(f"\rCurrent: {current_code} | {status} | Cmd [a/d/s/w/Enter]: ", end='', flush=True)
            
            # Non-blocking input is hard in standard python without curses/termios
            # We will stick to blocking input for reliability, user triggers 's' to fire.
            # But wait, user asked to "continue to serve codes".
            # Let's make 's' fire a burst of 5 times.
            
            cmd = input().strip().lower()
            
            if cmd == 'a':
                current_code -= 1
            elif cmd == 'd':
                current_code += 1
            elif cmd == 's':
                print(f" -> Sending {current_code}...", end='', flush=True)
                rfdevice.tx_repeat = 10
                rfdevice.tx_code(current_code, PROTO, PULSE)
                print(" Sent.")
            elif cmd == 'w':
                # Since we use blocking input, toggle won't work well for "continuous"
                # Instead, let's make 'w' a "Sweep small range"
                print(f" -> Sweeping {current_code-2} to {current_code+2}...")
                for c in range(current_code-2, current_code+3):
                    rfdevice.tx_code(c, PROTO, PULSE)
                    time.sleep(0.2)
            elif cmd == '':
                # Enter check - actually checking for empty string might be annoying
                # We'll rely on an explicit save command? OR just 'save'
                pass
            elif cmd == 'save' or cmd == 'y':
                save_code(btn_key, current_code, data)
                return True
            elif cmd == 'exit' or cmd == 'n':
                return False
                
            # If user just hit enter hoping to save...
            # We need a robust way.
            # Let's stick to standard input loop.


def main():
    parser = argparse.ArgumentParser(description='Calibrate RF codes interactively.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin")
    parser.add_argument('button', type=str, nargs='?', help="Button to calibrate (e.g. '1 ON'). If empty, lists all.")
    args = parser.parse_args()
    
    if not os.path.exists(CODES_FILE):
        print("Error: remote_codes.json not found.")
        sys.exit(1)
        
    with open(CODES_FILE, 'r') as f:
        data = json.load(f)
        
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    try:
        if args.button:
            key = args.button.upper()
            if key in data:
                calibrate_button(rfdevice, key, data)
            else:
                print(f"Button '{key}' not found.")
        else:
            print("Select button to calibrate:")
            keys = sorted(data.keys())
            for i, k in enumerate(keys):
                print(f"{i+1}. {k}")
            
            choice = input(f"Enter number (1-{len(keys)}) or 'all': ")
            if choice.lower() == 'all':
                for k in keys:
                    if not calibrate_button(rfdevice, k, data):
                        print("Skipping to next...")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(keys):
                        calibrate_button(rfdevice, keys[idx], data)
                except ValueError:
                    print("Invalid selection.")
                    
    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
