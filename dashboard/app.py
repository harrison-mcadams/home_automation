import os
import sys
import time
import socket
import json
import subprocess
import shutil
import argparse
from flask import Flask, jsonify, render_template, request

# Optional dependencies
try:
    import psutil
except ImportError:
    psutil = None

app = Flask(__name__, template_folder='templates', static_folder='static')

# Path configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config():
    """Load projects configuration."""
    if not os.path.exists(CONFIG_FILE):
        return {"projects": []}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {"projects": []}

def get_cpu_temp():
    """Get CPU temperature in Celsius (Pi specific, fallback for testing)."""
    try:
        # Raspberry Pi temperature file
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_raw = int(f.read().strip())
                return round(temp_raw / 1000.0, 1)
        # Alternate file path on some Pi environments
        elif os.path.exists("/sys/class/hwmon/hwmon0/temp1_input"):
            with open("/sys/class/hwmon/hwmon0/temp1_input", "r") as f:
                temp_raw = int(f.read().strip())
                return round(temp_raw / 1000.0, 1)
    except Exception:
        pass
    
    # Fallback to psutil on other Linux platforms
    if psutil and hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Find cpu or coretemp sensors
                for name, entries in temps.items():
                    if name in ['cpu_thermal', 'coretemp', 'cpu-thermal']:
                        return round(entries[0].current, 1)
        except Exception:
            pass

    # Windows debug fallback (sinusoidal simulation so it looks dynamic)
    if sys.platform.startswith('win'):
        t = time.time()
        import math
        return round(40.0 + 3.0 * math.sin(t / 60.0), 1)
    
    return None

def get_cpu_freq():
    """Get active CPU scaling frequency in GHz."""
    try:
        if os.path.exists("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"):
            with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
                freq_khz = int(f.read().strip())
                return round(freq_khz / 1000000.0, 2)  # GHz
    except Exception:
        pass
    
    if psutil:
        try:
            freq = psutil.cpu_freq()
            if freq:
                return round(freq.current / 1000.0, 2)
        except Exception:
            pass
            
    return 1.50  # Default Pi 4 clock speed mock

def get_throttled_info():
    """Get throttled state from vcgencmd (under-voltage, thermal throttling)."""
    # Bits interpretation:
    # Bit 0: Under-voltage detected now
    # Bit 1: Arm frequency capped now (throttling)
    # Bit 2: Currently throttled
    # Bit 3: Soft temperature limit active now
    # Bit 16: Under-voltage has occurred since last boot
    # Bit 17: Arm frequency capped has occurred since last boot
    # Bit 18: Throttling has occurred since last boot
    # Bit 19: Soft temperature limit has occurred since last boot
    try:
        res = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=1.0)
        if res.returncode == 0:
            line = res.stdout.strip()
            val_str = line.split("=")[1] if "=" in line else line
            val = int(val_str, 16)
            
            return {
                "raw": hex(val),
                "under_voltage_now": bool(val & 0x1),
                "arm_freq_capped_now": bool(val & 0x2),
                "throttled_now": bool(val & 0x4),
                "soft_temp_limit_now": bool(val & 0x8),
                "under_voltage_past": bool(val & 0x10000),
                "arm_freq_capped_past": bool(val & 0x20000),
                "throttled_past": bool(val & 0x40000),
                "soft_temp_limit_past": bool(val & 0x80000),
                "has_warnings": (val != 0)
            }
    except Exception:
        pass
    
    # Windows/non-Pi fallback
    return {
        "raw": "0x0",
        "under_voltage_now": False,
        "arm_freq_capped_now": False,
        "throttled_now": False,
        "soft_temp_limit_now": False,
        "under_voltage_past": False,
        "arm_freq_capped_past": False,
        "throttled_past": False,
        "soft_temp_limit_past": False,
        "has_warnings": False
    }

def get_wifi_info():
    """Parse WiFi signal quality from /proc/net/wireless."""
    try:
        if os.path.exists("/proc/net/wireless"):
            with open("/proc/net/wireless", "r") as f:
                lines = f.readlines()
                # Line 0 and 1 are headers
                for line in lines[2:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        iface = parts[0].replace(":", "")
                        quality_str = parts[2].replace(".", "")
                        level_str = parts[3].replace(".", "")
                        quality = int(quality_str)
                        level = int(level_str)
                        
                        # Typically quality is out of 70
                        percent = min(100, int((quality / 70.0) * 100))
                        return {
                            "interface": iface,
                            "quality": quality,
                            "level_dbm": level,
                            "percent": percent
                        }
    except Exception:
        pass
    return None

def get_load_averages():
    """Get system load averages."""
    try:
        if hasattr(os, "getloadavg"):
            return [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass
    
    if psutil and hasattr(psutil, "getloadavg"):
        try:
            return [round(x, 2) for x in psutil.getloadavg()]
        except Exception:
            pass
            
    return [0.15, 0.22, 0.18]

def get_tailscale_status():
    """Get Tailscale connection status."""
    try:
        res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=1.5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            backend_state = data.get("BackendState", "offline")
            self_node = data.get("Self", {})
            online = self_node.get("Online", False)
            ip = self_node.get("TailAddr", "")
            dns_name = self_node.get("DNSName", "").split('.')[0]
            
            return {
                "status": "online" if backend_state == "Running" else "offline",
                "backend_state": backend_state,
                "ip": ip,
                "dns_name": dns_name,
                "online": online,
                "enabled": True
            }
        else:
            return {
                "status": "offline",
                "backend_state": "Stopped/Disconnected",
                "enabled": True
            }
    except FileNotFoundError:
        return {
            "status": "offline",
            "backend_state": "Not Installed",
            "enabled": False
        }
    except Exception as e:
        return {
            "status": "offline",
            "backend_state": f"Error: {str(e)}",
            "enabled": True
        }

def get_system_uptime():
    """Get system uptime in seconds."""
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])
                return uptime_seconds
    except Exception:
        pass
        
    if psutil:
        try:
            return time.time() - psutil.boot_time()
        except Exception:
            pass
            
    return 0.0

def get_default_gateway():
    """Discover default network gateway IP."""
    try:
        if sys.platform.startswith('win'):
            res = subprocess.run("route print 0.0.0.0", capture_output=True, text=True, shell=True)
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == '0.0.0.0' and parts[1] == '0.0.0.0':
                    return parts[2]
        else:
            with open("/proc/net/route", "r") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == "00000000":
                        gw_hex = parts[2]
                        # Little endian hex conversion
                        b1 = int(gw_hex[6:8], 16)
                        b2 = int(gw_hex[4:6], 16)
                        b3 = int(gw_hex[2:4], 16)
                        b4 = int(gw_hex[0:2], 16)
                        return f"{b1}.{b2}.{b3}.{b4}"
    except Exception:
        pass
    return "192.168.1.1"

def get_local_ips():
    """Get IPv4 addresses of non-loopback network interfaces."""
    ips = {}
    # Try quick socket discovery for primary local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't connect/send, just opens socket locally to resolve routing
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and primary_ip != "127.0.0.1":
            ips["active"] = primary_ip
    except Exception:
        pass

    # Read interfaces on Linux
    try:
        if not sys.platform.startswith('win'):
            res = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 4:
                        iface = parts[1]
                        ip = parts[3].split('/')[0]
                        if ip != "127.0.0.1":
                            ips[iface] = ip
    except Exception:
        pass

    if not ips:
        ips["local"] = "127.0.0.1"
    return ips

def ping_latency(host, port=53):
    """Measure latency to a host using TCP socket connection (port 53 for internet/gateway) or ICMP ping as fallback."""
    # Try TCP connection first (no raw socket privilege needed, handles firewalls better)
    try:
        start_time = time.time()
        s = socket.create_connection((host, port), timeout=1.0)
        latency = int((time.time() - start_time) * 1000)
        s.close()
        return latency
    except Exception:
        pass

    # Fallback to ICMP ping (requires SUID/caps, may fail for standard user on some OS versions)
    param = '-n' if sys.platform.lower().startswith('win') else '-c'
    timeout_param = '-w' if sys.platform.lower().startswith('win') else '-W'
    timeout_val = '1000' if sys.platform.lower().startswith('win') else '1'
    
    cmd = ['ping', param, '1', timeout_param, timeout_val, host]
    try:
        start_time = time.time()
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.5)
        latency = int((time.time() - start_time) * 1000)
        return latency if res.returncode == 0 else None
    except Exception:
        return None

def check_http_status(url):
    """Check status of HTTP service endpoint."""
    try:
        import requests
        start_time = time.time()
        # Short timeout: we don't want the API poll to block long
        resp = requests.get(url, timeout=1.2)
        latency = int((time.time() - start_time) * 1000)
        # Any response (even error code, meaning server is online) is online
        return {
            "status": "online",
            "code": resp.status_code,
            "latency_ms": latency,
            "details": resp.json() if "application/json" in resp.headers.get("Content-Type", "") else resp.text[:100]
        }
    except Exception as e:
        return {
            "status": "offline",
            "error": str(e)
        }

def check_port_status(port):
    """Check if a port is open locally."""
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.8)
        result = sock.connect_ex(('127.0.0.1', int(port)))
        latency = int((time.time() - start_time) * 1000)
        sock.close()
        if result == 0:
            return {"status": "online", "latency_ms": latency}
        else:
            return {"status": "offline"}
    except Exception:
        return {"status": "offline"}

def check_systemd_status(service_name):
    """Check if systemd service is active."""
    if sys.platform.startswith('win'):
        # Mock checking systemd processes on Windows
        # Let's search running processes for dummy service logic or mock as online/offline
        if psutil:
            for p in psutil.process_iter(attrs=['name', 'cmdline']):
                try:
                    cmd = p.info.get('cmdline') or []
                    cmd_str = " ".join(cmd).lower()
                    if service_name.replace(".service", "").lower() in cmd_str:
                        return {"status": "online", "source": "process"}
                except Exception:
                    pass
        # Default mock
        return {"status": "offline", "note": "systemd unavailable (Windows)"}

    try:
        res = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True, timeout=1.0)
        status_text = res.stdout.strip()
        if status_text == "active":
            return {"status": "online"}
        else:
            return {"status": "offline", "details": status_text}
    except Exception as e:
        return {"status": "offline", "error": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    stats = {}
    
    # 1. Gather System Health
    cpu_percent = 0.0
    mem_used = 0.0
    mem_total = 0.0
    mem_percent = 0.0
    swap_used = 0.0
    swap_total = 0.0
    swap_percent = 0.0
    load_avg = [0.0, 0.0, 0.0]
    
    if psutil:
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            mem_used = round(mem.used / (1024**3), 2)
            mem_total = round(mem.total / (1024**3), 2)
            mem_percent = mem.percent
            
            swap = psutil.swap_memory()
            swap_used = round(swap.used / (1024**3), 2)
            swap_total = round(swap.total / (1024**3), 2)
            swap_percent = swap.percent
        except Exception:
            pass
    
    # Disk Usage
    try:
        disk = shutil.disk_usage("/")
        disk_used = round(disk.used / (1024**3), 1)
        disk_total = round(disk.total / (1024**3), 1)
        disk_percent = round((disk.used / disk.total) * 100, 1)
    except Exception:
        disk_used = 0.0
        disk_total = 0.0
        disk_percent = 0.0
        
    stats["system"] = {
        "cpu_percent": cpu_percent,
        "cpu_temp": get_cpu_temp(),
        "cpu_freq_ghz": get_cpu_freq(),
        "memory": {
            "used_gb": mem_used,
            "total_gb": mem_total,
            "percent": mem_percent
        },
        "swap": {
            "used_gb": swap_used,
            "total_gb": swap_total,
            "percent": swap_percent
        },
        "disk": {
            "used_gb": disk_used,
            "total_gb": disk_total,
            "percent": disk_percent
        },
        "load_average": get_load_averages(),
        "power_diagnostics": get_throttled_info(),
        "uptime_seconds": get_system_uptime(),
        "timestamp_ms": int(time.time() * 1000)
    }
    
    # 2. Gather Network Health
    gateway = get_default_gateway()
    stats["network"] = {
        "gateway_ip": gateway,
        "local_ips": get_local_ips(),
        "wifi": get_wifi_info(),
        "tailscale": get_tailscale_status(),
        "pings": {
            "gateway_ms": ping_latency(gateway),
            "internet_ms": ping_latency("8.8.8.8")
        }
    }
    
    # 3. Gather Projects Health
    config = load_config()
    projects_status = []
    
    for project in config.get("projects", []):
        proj_id = project["id"]
        proj_name = project["name"]
        proj_type = project["type"]
        proj_target = project["target"]
        proj_desc = project.get("description", "")
        
        status_data = {"id": proj_id, "name": proj_name, "description": proj_desc, "type": proj_type, "service_name": project.get("service_name")}
        
        if proj_type == "systemd":
            res = check_systemd_status(proj_target)
            status_data.update(res)
        elif proj_type == "http":
            res = check_http_status(proj_target)
            status_data.update(res)
        elif proj_type == "port":
            res = check_port_status(proj_target)
            status_data.update(res)
        elif proj_type == "dummy":
            status_data["status"] = project.get("status_override", "Not Configured")
            status_data["is_dummy"] = True
        else:
            status_data["status"] = "unknown"
            
        projects_status.append(status_data)
        
    stats["projects"] = projects_status
    
    return jsonify(stats)

@app.route('/api/control', methods=['POST'])
def api_control():
    """API endpoint to execute service restart, reboot, or shutdown."""
    data = request.json or {}
    action = data.get("action")
    target = data.get("target") # e.g. service id or name
    
    if not action:
        return jsonify({"status": "error", "message": "No action specified"}), 400
        
    # Reboot & Shutdown Action
    if action == "reboot":
        print("[SYSTEM COMMAND] REBOOT REQUESTED")
        if sys.platform.startswith('win'):
            return jsonify({"status": "success", "message": "Mock reboot command received (Windows)"})
        try:
            # Run asynchronously so we return HTTP response first
            subprocess.Popen(["sudo", "reboot"])
            return jsonify({"status": "success", "message": "System reboot initiated."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    elif action == "shutdown":
        print("[SYSTEM COMMAND] SHUTDOWN REQUESTED")
        if sys.platform.startswith('win'):
            return jsonify({"status": "success", "message": "Mock shutdown command received (Windows)"})
        try:
            subprocess.Popen(["sudo", "poweroff"])
            return jsonify({"status": "success", "message": "System shutdown initiated."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # Restart Service Action
    elif action == "restart_service":
        if not target:
            return jsonify({"status": "error", "message": "No target service specified"}), 400
            
        # Find project in config to validate target
        config = load_config()
        project = None
        for p in config.get("projects", []):
            if p["id"] == target:
                project = p
                break
                
        if not project:
            return jsonify({"status": "error", "message": f"Service '{target}' is not configured"}), 404
            
        service_name = project.get("service_name") or (project["target"] if project["type"] == "systemd" else None)
        if not service_name:
            return jsonify({"status": "error", "message": f"Service '{target}' does not support systemd restart"}), 400
        
        # Security sanity check: keep only alpha-numeric, dots, dashes, underscores
        clean_name = "".join(c for c in service_name if c.isalnum() or c in ".-_")
        if clean_name != service_name:
            return jsonify({"status": "error", "message": "Invalid service name syntax"}), 400
            
        print(f"Executing systemd restart for: {clean_name}")
        
        if sys.platform.startswith('win'):
            time.sleep(1.0) # Simulate lag
            return jsonify({"status": "success", "message": f"Mock restarted {clean_name} (Windows)"})
            
        try:
            # Run restart
            res = subprocess.run(["sudo", "systemctl", "restart", clean_name], capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0:
                return jsonify({"status": "success", "message": f"Successfully restarted {clean_name}"})
            else:
                return jsonify({"status": "error", "message": f"Failed to restart {clean_name}: {res.stderr.strip()}"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": f"Unknown action '{action}'"}), 400

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Raspberry Pi Status Dashboard Server")
    parser.add_argument('--port', type=int, default=8000, help="Port to bind Flask to (default 8000)")
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Host to bind Flask to (default 0.0.0.0)")
    args = parser.parse_args()
    
    # Initialize CPU polling interval on startup
    if psutil:
        psutil.cpu_percent(interval=None)
        
    print(f"Starting status dashboard server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
