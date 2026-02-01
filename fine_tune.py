#!/usr/bin/env python3

import argparse
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

# Using both codes again just to be safe
CODES = [4478225, 4478259]
OFF_CODE = 4478212

VERIFIED_PULSE = 150

def main():
    parser = argparse.ArgumentParser(description='Validate Protocol 1 vs 2.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin (Default: 17)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_repeat = 20

    print(f"🎯 Validating PROTOCOL at Pulse {VERIFIED_PULSE}...")
    print("One of these sets should make it blink.")
    print("------------------------------------------------")

    try:
        while True:
            # TRY PROTOCOL 1
            print(f"👉 Testing PROTOCOL 1 ...", end='\r')
            for c in CODES:
                rfdevice.tx_code(c, 1, VERIFIED_PULSE) # Proto 1
            
            time.sleep(1)
            rfdevice.tx_code(OFF_CODE, 1, VERIFIED_PULSE) # Off Proto 1
            time.sleep(1)

            # TRY PROTOCOL 2
            print(f"👉 Testing PROTOCOL 2 ...", end='\r')
            for c in CODES:
                rfdevice.tx_code(c, 2, VERIFIED_PULSE) # Proto 2
            
            time.sleep(1)
            rfdevice.tx_code(OFF_CODE, 2, VERIFIED_PULSE) # Off Proto 2
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 STOPPED!")
        
    finally:
        rfdevice.cleanup()
        print("\nDone.")

if __name__ == "__main__":
    main()
