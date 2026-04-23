import sys
import os
import subprocess
import signal
import time
from flask import Flask, request, render_template_string, jsonify

# Configuration
PORT = 5050
ACTIVE_STREAM_PROC = None

app = Flask(__name__)

# Premium Dark-Mode UI with Glassmorphism
BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turbo Stream Bridge</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0a0c;
            --glass: rgba(255, 255, 255, 0.05);
            --accent: #8a2be2;
            --accent-glow: rgba(138, 43, 226, 0.4);
            --text: #e0e0e6;
        }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg);
            background: radial-gradient(circle at top right, #1a0b2e 0%, #0a0a0c 60%);
            color: var(--text);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            overflow: hidden;
        }
        .container {
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 3rem;
            border-radius: 24px;
            box-shadow: 0 24px 48px rgba(0,0,0,0.5);
            width: 100%;
            max-width: 500px;
            text-align: center;
            animation: fadeIn 0.8s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        h1 {
            font-weight: 600;
            margin-bottom: 0.5rem;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #fff, #a259ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p { opacity: 0.6; font-size: 0.9rem; margin-bottom: 2rem; }
        .input-group {
            margin-bottom: 1.5rem;
            position: relative;
        }
        input {
            width: 100%;
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 1rem 1.5rem;
            border-radius: 12px;
            color: white;
            font-size: 1rem;
            box-sizing: border-box;
            transition: all 0.3s ease;
        }
        input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 15px var(--accent-glow);
        }
        button {
            width: 100%;
            background: var(--accent);
            color: white;
            border: none;
            padding: 1rem;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 8px 16px var(--accent-glow);
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 24px var(--accent-glow);
            filter: brightness(1.1);
        }
        button:active { transform: translateY(0); }
        .kill-btn {
            background: #ff4757;
            box-shadow: 0 8px 16px rgba(255, 71, 87, 0.3);
            margin-top: 1rem;
        }
        .status {
            margin-top: 1.5rem;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4cd137;
            box-shadow: 0 0 8px #4cd137;
        }
        .dot.idle { background: #7f8c8d; box-shadow: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Turbo Bridge</h1>
        <p>Send a stream link to your MacBook</p>
        <div class="input-group">
            <input type="text" id="streamUrl" placeholder="Paste ntv.cx link here..." autocomplete="off">
        </div>
        <button onclick="launch()">Launch Stream</button>
        <button class="kill-btn" onclick="kill()">Stop Current</button>
        
        <div class="status">
            <div id="statusDot" class="dot {{ 'idle' if not active else '' }}"></div>
            <span id="statusText">{{ 'Streaming Active' if active else 'Idle / Ready' }}</span>
        </div>
    </div>

    <script>
        async function launch() {
            const url = document.getElementById('streamUrl').value;
            if (!url) return;
            
            const btn = document.querySelector('button');
            const originalText = btn.innerText;
            btn.innerText = 'Initializing...';
            btn.disabled = true;

            try {
                const resp = await fetch('/play', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url})
                });
                const data = await resp.json();
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (e) {
                alert('Connection failed');
            } finally {
                btn.innerText = originalText;
                btn.disabled = false;
            }
        }

        async function kill() {
            const resp = await fetch('/kill', {method: 'POST'});
            location.reload();
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    active = ACTIVE_STREAM_PROC is not None and ACTIVE_STREAM_PROC.poll() is None
    return render_template_string(BASE_TEMPLATE, active=active)

@app.route('/play', methods=['POST', 'GET'])
def play():
    global ACTIVE_STREAM_PROC
    
    # Support both GET (for simple shortcuts) and POST (for dashboard)
    url = None
    if request.method == 'POST':
        data = request.get_json()
        url = data.get('url')
    else:
        url = request.args.get('url')

    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    # Kill existing stream if running
    if ACTIVE_STREAM_PROC and ACTIVE_STREAM_PROC.poll() is None:
        try:
            # On Windows, we use taskkill to ensure the whole process tree (including Chrome) dies
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(ACTIVE_STREAM_PROC.pid)], check=False)
        except: pass

    try:
        # Launch turbo_stream.py
        # We use a new process group to ensure cleanup works
        script_path = os.path.join(os.path.dirname(__file__), "turbo_stream.py")
        ACTIVE_STREAM_PROC = subprocess.Popen([sys.executable, script_path, url])
        
        return jsonify({"success": True, "message": "Stream initiated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/kill', methods=['POST'])
def kill():
    global ACTIVE_STREAM_PROC
    if ACTIVE_STREAM_PROC and ACTIVE_STREAM_PROC.poll() is None:
        try:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(ACTIVE_STREAM_PROC.pid)], check=False)
            ACTIVE_STREAM_PROC = None
        except: pass
    return jsonify({"success": True})

if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on the local network
    app.run(host='0.0.0.0', port=PORT, debug=False)
