# Raspberry Pi Installation Guide

Follow these steps to set up the Gesture Controller on a fresh Raspberry Pi.

## 1. Prerequisites

Ensure you are running **Raspberry Pi OS (64-bit)**.
32-bit is _not_ recommended for MediaPipe.

Update your system first:

```bash
sudo apt update && sudo apt upgrade -y
```

Install system dependencies for OpenCV and Audio:

```bash
# OpenCV dependencies
sudo apt install -y libgl1-mesa-glx
# Audio dependencies (for feedback beep)
sudo apt install -y alsa-utils
```

## 2. Clone the Repository

Navigate to your home directory and clone the code:

```bash
cd ~
git clone https://github.com/harrison-mcadams/home_automation.git
cd home_automation
```

## 3. Set Up Python Environment

Raspberry Pi OS now enforces managed environments. use a virtual environment (`venv`) to install packages safely.

1.  **Create the venv**:

    ```bash
    python3 -m venv venv
    ```

2.  **Activate the venv**:

    ```bash
    source venv/bin/activate
    ```

    _(You should see `(venv)` at the start of your line)_

3.  **Install Python Libraries**:

    ```bash
    # Upgrade pip first
    pip install --upgrade pip

    # Install requirements
    # Note: On Pi, we might need specific versions, but try standard first:
    pip install opencv-python mediapipe requests
    ```

    _If `mediapipe` fails, try `pip install mediapipe-rpi`._

## 4. Run the Controller

You are now ready to run the optimized background script.

**Command:**

```bash
python gesture_controller/main.py --source "http://<YOUR_PHONE_IP>:8080/video" --headless --fps 10 --complexity 0
```

- `--source`: Your IP Webcam URL.
- `--headless`: Runs without a window (saves CPU).
- `--fps 10`: Limits to 10 FPS (low CPU usage).
- `--complexity 0`: Uses the "Lite" model (fastest).

## 5. (Optional) Run on Startup

To have this run automatically when the Pi boots:

1.  Create a service file:

    ```bash
    sudo nano /etc/systemd/system/gesture.service
    ```

2.  Paste this content (edit the User and Path!):

    ```ini
    [Unit]
    Description=Gesture Control Service
    After=network.target

    [Service]
    User=pi
    WorkingDirectory=/home/pi/home_automation
    Environment="PATH=/home/pi/home_automation/venv/bin"
    ExecStart=/home/pi/home_automation/venv/bin/python gesture_controller/main.py --source "http://192.168.1.100:8080/video" --headless --fps 10 --complexity 0
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

3.  Enable and Start:

    ```bash
    sudo systemctl enable gesture.service
    sudo systemctl start gesture.service
    ```

4.  Check status:
    ```bash
    sudo systemctl status gesture.service
    ```
