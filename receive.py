#!/usr/bin/env python3

import argparse
import signal
import sys
import time
import logging
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 27 (Physical Pin 13)
GPIO_RX = 27

def main():
    parser = argparse.ArgumentParser(description='Receives a 433MHz RF decimal code.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_RX,
                        help="GPIO pin (Default: 27)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_rx()
    
    timestamp = None
    logging.info(f"Listening for codes on GPIO {args.gpio}...")

    try:
        while True:
            if rfdevice.rx_code_timestamp != timestamp:
                timestamp = rfdevice.rx_code_timestamp
                print(f"Received: {rfdevice.rx_code} [Pulse: {rfdevice.rx_pulselength}, Proto: {rfdevice.rx_proto}]")
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
