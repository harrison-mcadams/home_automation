#!/bin/bash

# Get the absolute path of the current directory
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
USER_NAME=$(whoami)

# Detect the current Python interpreter (allows virtualenv)
PYTHON_BIN=$(which python)
PYTHON_DIR=$(dirname "$PYTHON_BIN")

# Check if we are using system Python
if [[ "$PYTHON_BIN" == /usr/bin/* ]]; then
    echo "WARNING: Detected system Python at $PYTHON_BIN."
    echo "If you meant to use a virtual environment, make sure it is activated."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Detailed Configuration:"
echo "----------------------"
echo "Project Root: $PROJECT_ROOT"
echo "User:         $USER_NAME"
echo "Python Bin:   $PYTHON_BIN"
echo "Python Dir:   $PYTHON_DIR"

SERVICE_FILE="rf_bridge_service.service"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: $SERVICE_FILE not found!"
    exit 1
fi

echo "Updating $SERVICE_FILE with detected configuration..."

# Create a temporary file
cp "$SERVICE_FILE" "${SERVICE_FILE}.tmp"

# Escape paths for sed using | delimiter
ESCAPED_ROOT=$(echo "$PROJECT_ROOT" | sed 's/\//\\\//g')

# Update User
sed -i "s/^User=.*/User=$USER_NAME/" "${SERVICE_FILE}.tmp"

# Update WorkingDirectory
sed -i "s/^WorkingDirectory=.*/WorkingDirectory=$ESCAPED_ROOT/" "${SERVICE_FILE}.tmp"

# Update Environment PATH to match Python Dir
sed -i "s|^Environment=.*|Environment=\"PATH=$PYTHON_DIR\"|" "${SERVICE_FILE}.tmp"

# Update ExecStart to use detected Python binary
sed -i "s|^ExecStart=.*|ExecStart=$PYTHON_BIN rf_bridge_service.py|" "${SERVICE_FILE}.tmp"

echo "Installing service..."
sudo cp "${SERVICE_FILE}.tmp" "/etc/systemd/system/$SERVICE_FILE"
rm "${SERVICE_FILE}.tmp"

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling service..."
sudo systemctl enable "$SERVICE_FILE"

echo "Starting service..."
sudo systemctl restart "$SERVICE_FILE"

echo "Done! Status:"
sudo systemctl status "$SERVICE_FILE" --no-pager
