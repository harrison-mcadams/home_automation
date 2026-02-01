#!/usr/bin/env python3

import argparse
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

# Verified settings
PROTO = 1
PULSE = 150

def main():
    parser = argparse.ArgumentParser(description='Heavy Hammer: High Repetition Code Tester.')
    parser.add_argument('center_code', type=int, help="Center code to target (e.g. 4478209)")
    parser.add_argument('--range', type=int, default=20, help="Range +/- around center (Default: 20)")
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin")
    args = parser.parse_args()
    
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    start_code = args.center_code - args.range
    end_code = args.center_code + args.range
    
    print(f"🔨 HEAVY HAMMER targeting {args.center_code} (+/- {args.range})")
    print(f"Scanning {start_code} to {end_code}")
    print(f"Settings: Proto {PROTO}, Pulse {PULSE}, Repeat=50")
    print("This will be SLOW. Be patient.")
    print("Press Ctrl+C IMMEDIATELY when the outlet reacts!")
    print("------------------------------------------------")
    
    try:
        for code in range(start_code, end_code + 1):
            print(f"👉 Hammering: {code} ...", end='\r')
            
            # Send HUGE burst
            rfdevice.tx_repeat = 50
            rfdevice.tx_code(code, PROTO, PULSE)
            
            # Send it AGAIN just to be sure
            time.sleep(0.1)
            rfdevice.tx_code(code, PROTO, PULSE)
            
            # Sleep a bit to let the receiver recover/reset if needed
            time.sleep(0.2)
            
        print("\n❌ Completed hammer run.")
        
    except KeyboardInterrupt:
        print(f"\n\n🛑 STOPPED at {code}!")
        print(f"Valid Code is likely: {code}")
        
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
