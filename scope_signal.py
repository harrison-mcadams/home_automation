#!/usr/bin/env python3

import argparse
import time
import sys
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 27 (RX)
GPIO_RX = 27

def main():
    parser = argparse.ArgumentParser(description='Raw RF Signal Scope.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_RX, help="GPIO pin (Default: 27)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_rx()
    
    print(f"🔬 RF SIGNAL SCOPE (GPIO {args.gpio})")
    print("Capturing EVERYTHING. No Filters. No Logic.")
    print("Press your remote button repeatedly.")
    print("------------------------------------------------")
    print(f"{'TIMESTAMP':<15} | {'CODE':<10} | {'PROTO':<5} | {'PULSE':<5} | {'LENGTH':<5}")
    
    last_time = 0
    
    try:
        while True:
            if rfdevice.rx_code_timestamp:
                timestamp = rfdevice.rx_code_timestamp
                # Simple ensure we don't print duplicates too fast
                if timestamp != last_time:
                    code = rfdevice.rx_code
                    proto = rfdevice.rx_proto
                    pulse = rfdevice.rx_pulselength
                    
                    # Highlight if it looks like Etekcity (Pulse ~150-500)
                    highlight = ""
                    if 100 < pulse < 550:
                        highlight = " <--"
                        
                    print(f"{timestamp:<15} | {code:<10} | {proto:<5} | {pulse:<5} | {rfdevice.rx_bitlength:<5}{highlight}")
                    
                    last_time = timestamp
            time.sleep(0.005)
            
    except KeyboardInterrupt:
        print("\nScope stopped.")
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
