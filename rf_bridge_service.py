import json
import os
import serial
import time
import sys
from flask import Flask, jsonify, request

# Configuration
# We expect remote_codes.json to be in the same directory as this script
CODES_FILE = "remote_codes.json"
PICO_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200

app = Flask(__name__)

# Global serial connection
ser = None

def load_codes():
    """Load the RF codes from the JSON file."""
    if not os.path.exists(CODES_FILE):
        print(f"Error: {CODES_FILE} not found.")
        return {}
    try:
        with open(CODES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading codes: {e}")
        return {}

def init_serial():
    """Initialize the persistent serial connection."""
    global ser
    try:
        print(f"Connecting to Pico on {PICO_PORT}...")
        ser = serial.Serial(PICO_PORT, BAUD_RATE, timeout=1)
        # Wait a moment for the connection to settle
        time.sleep(2)
        print("Serial connection established successfully.")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not connect to Pico: {e}")
        ser = None

@app.route('/api/control', methods=['POST'])
def control_outlet():
    global ser
    
    # 1. Parse Request
    data = request.json
    button_name = data.get('button')
    
    if not button_name:
        return jsonify({"error": "No button specified"}), 400
    
    # 2. Lookup Code
    # Reload codes every time? Or just once? 
    # Let's reload to allow user to update json without restarting service
    codes_db = load_codes()
    
    # Try case-insensitive lookup, but prefer exact match
    btn_key = button_name # keep original casing first
    if btn_key not in codes_db:
        # Try upper case
        btn_key = button_name.upper()
    
    if btn_key not in codes_db:
        return jsonify({
            "error": f"Button '{button_name}' not found",
            "available_buttons": list(codes_db.keys())
        }), 404
        
    data = codes_db[btn_key]
    code = data['code']
    proto = data.get('protocol', 1)
    pulse = data.get('pulselength', 150)
    
    # 3. Send to Pico
    if ser is None:
        # Try to reconnect if connection was lost or never established
        print("Serial connection is down. Attempting to reconnect...")
        init_serial()
        if ser is None:
            return jsonify({"error": "Serial connection unavailable"}), 500

    try:
        # Send command: code,protocol,pulselength
        cmd = f"{code},{proto},{pulse}\n"
        print(f"🚀 Sending: {cmd.strip()}")
        ser.write(cmd.encode())
        
        # Read response (optional, but good for confirmation)
        # Pico should send back "Done." or similar
        # We use strict timeout here to not block if Pico is silent
        response = ser.read_until(b"Done.").decode().strip()
        print(f"Pico says: {response}")
        
        return jsonify({
            "status": "success",
            "message": f"Sent {button_name}", 
            "pico_response": response
        })
        
    except Exception as e:
        print(f"Serial Write Error: {e}")
        # Force reconnection next time
        try:
            ser.close()
        except:
            pass
        ser = None
        return jsonify({"error": f"Failed to send command: {str(e)}"}), 500

@app.route('/health')
def health_check():
    status = "healthy" if ser and ser.is_open else "unhealthy"
    return jsonify({"status": status, "serial_connected": ser is not None})

if __name__ == '__main__':
    # Initialize serial on startup
    init_serial()
    # Run Flask
    app.run(host='0.0.0.0', port=5000)
