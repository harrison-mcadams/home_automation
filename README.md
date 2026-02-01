# RF Testing

This folder contains scripts to test your SMAKN 433MHz RF Transmitter and Receiver kit.

## Wiring (Fan-Safe Version)

### Transmitter (Square Board)
- **VCC** -> **Pin 2** (5V)
- **GND** -> **Pin 14** (GND)
- **DATA** -> **Pin 11** (GPIO 17)

### Receiver (Rectangular Board)
- **VCC** -> **Pin 1** (3.3V)
- **DATA** -> **Pin 13** (GPIO 27)
- **GND** -> **Pin 9** (GND)

## Usage

### 1. Verification
Test basic sending and receiving:
- Terminal 1: `python3 receive.py`
- Terminal 2: `python3 send.py`

### 2. Learn Remote Codes
Run the sniffer to capture your physical remote's signals:
```bash
python3 sniff_remote.py
```
This saves codes to `remote_codes.json`.

### 3. Mimic Remote
Replay a specific button press:
```bash
# Quote the button name if it has spaces
python3 mimic_remote.py "1 ON"
python3 mimic_remote.py "1 OFF"
```

## Troubleshooting
If you get `RuntimeError: Failed to add edge detection`, you need the newer GPIO library:
```bash
pip3 uninstall RPi.GPIO
sudo apt install liblgpio-dev swig -y
pip3 install rpi-lgpio
```
