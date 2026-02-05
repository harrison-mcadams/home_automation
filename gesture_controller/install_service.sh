#!/bin/bash

# Get the absolute path of the current directory (assumed to be home_automation/gesture_controller)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
USER_NAME=$(whoami)

echo "Detected Project Root: $PROJECT_ROOT"
echo "Detected User: $USER_NAME"

SERVICE_FILE="gesture.service"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: $SERVICE_FILE not found!"
    exit 1
fi

echo "Updating $SERVICE_FILE with correct paths..."

# Create a temporary file
cp "$SERVICE_FILE" "${SERVICE_FILE}.tmp"

# Escape paths for sed using | delimiter
ESCAPED_ROOT=$(echo "$PROJECT_ROOT" | sed 's/\//\\\//g')

# Update User
sed -i "s/^User=.*/User=$USER_NAME/" "${SERVICE_FILE}.tmp"

# Update WorkingDirectory
sed -i "s/^WorkingDirectory=.*/WorkingDirectory=$ESCAPED_ROOT/" "${SERVICE_FILE}.tmp"

# Update Environment PATH
sed -i "s|^Environment=.*|Environment=\"PATH=$PROJECT_ROOT/venv/bin\"|" "${SERVICE_FILE}.tmp"

# Update ExecStart
# Note: Keeping the arguments, just updating the python path
sed -i "s|^ExecStart=.*|ExecStart=$PROJECT_ROOT/venv/bin/python gesture_controller/main.py --source \"http://192.168.1.100:8080/video\" --headless --fps 10 --complexity 0|" "${SERVICE_FILE}.tmp"

echo "Installing service..."
sudo cp "${SERVICE_FILE}.tmp" "/etc/systemd/system/$SERVICE_FILE"
rm "${SERVICE_FILE}.tmp"

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling service..."
sudo systemctl enable "$SERVICE_FILE"

echo "Starting service..."
sudo systemctl start "$SERVICE_FILE"

echo "Done! Check status with: sudo systemctl status $SERVICE_FILE"
