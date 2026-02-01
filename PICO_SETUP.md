# Pi Pico RF Bridge: Setup Guide

Welcome to the world of microcontrollers! The Pico is different from the Pi 4 because it doesn't have an operating system. You don't "log in" to it; you just give it a single script and it runs it forever.

## 1. Physical Wiring

Most 433MHz transmitters have 3 or 4 pins. Look at the labels on your transmitter board and connect them to these specific spots on the Pico:

| Transmitter Pin | Pico Physical Pin Number | Function |
| :--- | :--- | :--- |
| **VCC** (or V+) | **Pin 40** (Top Right) | 5V Power (from USB) |
| **GND** | **Pin 38** (Bottom Right area) | Ground |
| **DATA** (or ATAD) | **Pin 20** (Bottom Left) | Signal (GP15) |

### Pinout Reference:
If you hold the Pico with the USB port at the **TOP**:
- **Pin 40 (VBUS)** is the very first pin on the **top right**.
- **Pin 20 (GP15)** is the very last pin on the **bottom left**.
- **Pin 38 (GND)** is the third pin up from the **bottom right**.

---

## 2. Software (Getting the code on the Pico)

1. **Plug the Pico into your computer/Pi 4** using a micro-USB cable.
2. **Download Thonny:** If you are on your laptop, download the [Thonny IDE](https://thonny.org/). It's the standard for Pico.
3. **Connect in Thonny:** 
   - Look at the bottom right corner of Thonny. It should say "MicroPython (Raspberry Pi Pico)". If it doesn't, click it and select that option.
   - If it asks to "Install MicroPython", say **Yes**. This puts the "brain" on the Pico.
4. **Save the Script:**
   - Copy the code from `rf_testing/pico_bridge.py` (the one I created for you earlier).
   - Paste it into a new file in Thonny.
   - Go to **File > Save As...**
   - Choose **Raspberry Pi Pico**.
   - **CRITICAL:** Name the file exactly **`main.py`**. 
   - *Why?* When the Pico starts up, it looks for a file with that exact name to run.

---

## 3. Deployment

1. Unplug the Pico from your computer.
2. Plug it into one of the **USB ports on your Raspberry Pi 4**.
3. The Pico is now powered and running its logic!
4. From your Pi 4 terminal, run:
   ```bash
   python rf_testing/mimic_pico.py "1 ON"
   ```

The Pi 4 sends the command over the USB cable, and the Pico handles the precision timing of the RF signal!
