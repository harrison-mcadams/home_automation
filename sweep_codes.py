#!/usr/bin/env python3

import argparse
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

# KNOWN GOOD SETTINGS
PROTO = 1
PULSE = 150

# Range to sweep
# 1 OFF Sniffed: 4478244
# 1 ON Sniffed:  4478259
# 1 OFF Old:     4478212
# We'll sweep 4478200 to 4478300 to capture everything in this cluster.
START_CODE = 4478200
END_CODE   = 4478300

def main():
    parser = argparse.ArgumentParser(description='Sweep RF Codes.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin (Default: 17)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    # Fast repeats to cover ground, but enough to register
    rfdevice.tx_repeat = 15

    print(f"🧹 Sweeping Codes {START_CODE} -> {END_CODE}")
    print(f"Using Verified Settings: Proto {PROTO}, Pulse {PULSE}")
    print("Press Ctrl+C IMMEDIATELY when the light turns OFF!")
    print("------------------------------------------------")

    try:
        for code in range(START_CODE, END_CODE + 1):
            print(f"👉 Sending: {code}", end='\r')
            rfdevice.tx_code(code, PROTO, PULSE)
            # Short sleep to distinguish events
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 STOPPED!")
        print("The last code printed (or one very close to it) is the WINNER.")
        
    finally:
        rfdevice.cleanup()
        print("\nDone.")

if __name__ == "__main__":
    main()
