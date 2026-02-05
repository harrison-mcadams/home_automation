#!/bin/bash

# Ensure we are in the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv"

echo "Setting up environment in: $VENV_DIR"

# 1. Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment exists."
fi

# 2. Activate and Install
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies..."
# mediapipe-rpi might be needed for older OS, but trying standard first as per PI_SETUP
pip install opencv-python "mediapipe==0.10.14" requests

# Verify installation
echo "Verifying installation..."
python -c "import cv2; print('OpenCV version:', cv2.__version__)"

if [ $? -eq 0 ]; then
    echo "✅ Setup Complete!"
    echo "You can now restart the service with: sudo systemctl restart gesture.service"
else
    echo "❌ OpenCV install failed. You might need system dependencies:"
    echo "sudo apt install -y libgl1-mesa-glx"
fi
