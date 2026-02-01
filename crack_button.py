#!/usr/bin/env python3

import argparse
import time
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

def main():
    parser = argparse.ArgumentParser(description='Crack Protocol/Pulse for a specific Code.')
    parser.add_argument('code', type=int, help="Code to crack (e.g. 4478209)")
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX, help="GPIO pin")
    args = parser.parse_args()
    
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    
    print(f"🔨 CRACKING Code: {args.code}")
    print("Sweeping Pulse Lengths 100-600 across Protocols 1-5.")
    print("Press Ctrl+C IMMEDIATELY when the outlet reacts!")
    print("------------------------------------------------")
    
    # Priority Order: 
    # 1. Protocol 1 (Verified for Button 1)
    # 2. Protocol 5 (Reported by Sniffer)
    # 3. Protocol 2 (Brute force verified briefly)
    protocols = [1, 5, 2, 3, 4]
    
    # Pulse Range: 100 to 300 is the sweet spot for Etekcity, but we'll go up to 550 just in case.
    pulses = list(range(120, 300, 5)) + list(range(300, 600, 10))
    
    try:
        for pulse in pulses:
            for proto in protocols:
                print(f"👉 Testing: Proto={proto} | Pulse={pulse} ...", end='\r')
                
                # Send with hefty repeat to ensure it catches
                rfdevice.tx_repeat = 25
                rfdevice.tx_code(args.code, proto, pulse)
                
                # Small delay
                time.sleep(0.05)
                
        print("\n❌ Exhausted all combinations.")
        
    except KeyboardInterrupt:
        print(f"\n\n🛑 STOPPED!")
        print("Likely Winner:")
        print(f"Code: {args.code}")
        print(f"Pulse: ~{pulse}")
        print(f"Proto: {proto}")
        print("\nTry running mimic_remote with these settings!")
        
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
