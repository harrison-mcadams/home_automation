#!/usr/bin/env python3

import argparse
import logging
import time
import random
from rpi_rf import RFDevice

# PREFERRED PIN: GPIO 17 (Physical Pin 11)
GPIO_TX = 17

def main():
    parser = argparse.ArgumentParser(description='Sends a 433MHz RF decimal code.')
    parser.add_argument('-g', '--gpio', dest='gpio', type=int, default=GPIO_TX,
                        help="GPIO pin (Default: 17)")
    parser.add_argument('-p', '--pulselength', dest='pulselength', type=int, default=350,
                        help="Pulselength (Default: 350)")
    parser.add_argument('-t', '--protocol', dest='protocol', type=int, default=1,
                        help="Protocol (Default: 1)")
    args = parser.parse_args()

    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_repeat = 10

    logging.info(f"Transmitting on GPIO {args.gpio} [Protocol: {args.protocol}, Pulse: {args.pulselength}]")

    try:
        while True:
            # Generate a random code to send (simulating a sensor data, or button press)
            code = random.randint(1000, 9999) 
            
            print(f"Sending code: {code}")
            rfdevice.tx_code(code, args.protocol, args.pulselength)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        rfdevice.cleanup()

if __name__ == "__main__":
    main()
