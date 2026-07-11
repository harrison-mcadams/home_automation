#!/bin/bash
# Activate Terminal and launch the gesture controller in headless mode
osascript -e 'tell application "Terminal" to activate'
sleep 0.5
osascript -e 'tell application "Terminal" to do script "cd ~/Desktop/home_automation && source venv/bin/activate && python gesture_controller/main.py --usb --headless"'
