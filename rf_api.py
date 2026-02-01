from flask import Flask, jsonify, request
import subprocess
import os

app = Flask(__name__)

# CONFIGURATION
# The path to your python executable (in the virtual environment)
PYTHON_EXEC = "/home/spoon/new_puck/.venv/bin/python"
# The path to the pico mimic script
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mimic_pico.py")

@app.route('/')
def home():
    return "RF Pico API is running! 📡⚡️"

@app.route('/api/control', methods=['POST'])
def control_outlet():
    """
    Expects JSON data: { "button": "1 ON" }
    Sends command to Pi Pico Bridge.
    """
    data = request.json
    button_name = data.get('button')
    
    if not button_name:
        return jsonify({"error": "No button specified"}), 400
    
    print(f"📡 Received request: {button_name}")
    
    # Construct the command
    # python rf_testing/mimic_remote.py "1 ON"
    cmd = [PYTHON_EXEC, SCRIPT_PATH, button_name]
    
    try:
        # Run the mimic script
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            print(f"✅ Success: {result.stdout.strip()}")
            return jsonify({"status": "success", "message": f"Sent {button_name}", "output": result.stdout.strip()})
        else:
            print(f"❌ Error: {result.stderr.strip()}")
            return jsonify({"status": "error", "message": "Script failed", "detail": result.stderr.strip()}), 500
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Host='0.0.0.0' allows access from other devices on the network (like your watch)
    app.run(host='0.0.0.0', port=5000)
