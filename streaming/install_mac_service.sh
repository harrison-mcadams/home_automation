#!/bin/bash

# Turbo Bridge macOS Service Installer
# This script configures and installs the LaunchAgent for stream_bridge.py

# 1. Path Discovery
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Assuming script is in /streaming, project root is one level up
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
USER_HOME="$HOME"

# 2. Python Detection
PYTHON_BIN=$(which python3)
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN=$(which python)
fi

# Check for active venv or conda
if [[ "$VIRTUAL_ENV" != "" ]]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [[ "$CONDA_PREFIX" != "" ]]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python"
fi

PYTHON_DIR=$(dirname "$PYTHON_BIN")

echo "--- Turbo Bridge Installer ---"
echo "Project Root: $PROJECT_ROOT"
echo "Python Bin:   $PYTHON_BIN"
echo "Log Path:     $USER_HOME/Library/Logs/turbo_bridge.log"
echo "------------------------------"

# 3. Create/Update Plist
PLIST_NAME="com.turbo.bridge.plist"
TEMPLATE="$SCRIPT_DIR/$PLIST_NAME"
TARGET="$USER_HOME/Library/LaunchAgents/$PLIST_NAME"

if [ ! -f "$TEMPLATE" ]; then
    echo "Error: Template $TEMPLATE not found!"
    exit 1
fi

echo "[*] Generating $PLIST_NAME..."

# Escaping paths for sed
ESCAPED_ROOT=$(echo "$PROJECT_ROOT" | sed 's/\//\\\//g')
ESCAPED_PYTHON=$(echo "$PYTHON_BIN" | sed 's/\//\\\//g')
ESCAPED_PYDIR=$(echo "$PYTHON_DIR" | sed 's/\//\\\//g')
ESCAPED_HOME=$(echo "$USER_HOME" | sed 's/\//\\\//g')

sed -e "s/{{PROJECT_ROOT}}/$ESCAPED_ROOT/g" \
    -e "s/{{PYTHON_BIN}}/$ESCAPED_PYTHON/g" \
    -e "s/{{PYTHON_DIR}}/$ESCAPED_PYDIR/g" \
    -e "s/{{HOME}}/$ESCAPED_HOME/g" \
    "$TEMPLATE" > "$PLIST_NAME.tmp"

# 4. Installation
echo "[*] Installing to $TARGET..."
mkdir -p "$USER_HOME/Library/LaunchAgents"
cp "$PLIST_NAME.tmp" "$TARGET"
rm "$PLIST_NAME.tmp"

# 5. Launch
echo "[*] Loading service..."
# Unload first if exists
launchctl unload "$TARGET" 2>/dev/null
launchctl load "$TARGET"

echo "[*] Done! Turbo Bridge is now set to start on login."
echo "[*] To check logs: tail -f ~/Library/Logs/turbo_bridge.log"
echo "[*] Status: launchctl list | grep turbo"
