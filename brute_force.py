#!/usr/bin/env python3

import argparse
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

# Codes to try (The ones we saw in the logs)
CODES = [4478225, 4478259]

def main():
    parser = argparse.ArgumentParser(description='Brute force RF codes.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin (Default: 17)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_repeat = 15 # Standard repeat

    print("🚀 Starting Brute Force Sequence...")
    print("Press Ctrl+C immediately when the outlet turns ON!")
    print("------------------------------------------------")

    try:
        # Loop through Pulse Lengths (Common ones first)
        # Etekcity is usually ~189. We saw ~455. 
        # range(start, stop, step)
        pulses = list(range(150, 600, 10)) 
        
        protocols = [1, 2, 3, 4, 5]
        
        for pulse in pulses:
            for proto in protocols:
                for code in CODES:
                    print(f"Testing: Proto={proto} | Pulse={pulse} | Code={code}", end='\r')
                    rfdevice.tx_code(code, proto, pulse)
                    # Tiny sleep to let the outlet react
                    time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\n\n🛑 STOPPED!")
        print("The last combination printed above is likely the winner (or close to it).")
        
    finally:
        rfdevice.cleanup()
        print("\nDone.")

if __name__ == "__main__":
    main()
