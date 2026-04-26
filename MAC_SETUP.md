# Turbo Bridge macOS Setup

This guide explains how to make the **Turbo Bridge** (`stream_bridge.py`) start automatically when you log into your MacBook.

## 1. Installation

1.  Open **Terminal** on your MacBook.
2.  Navigate to your `home_automation` directory.
3.  If you use a specific environment (Conda or venv), **activate it first**.
4.  Run the installer:
    ```bash
    chmod +x streaming/install_mac_service.sh
    ./streaming/install_mac_service.sh
    ```

## 2. Managing the Service

Once installed, the bridge runs in the background. You don't need to keep a terminal window open.

### Check Status
To see if the service is loaded:
```bash
launchctl list | grep turbo
```

### View Logs
If things aren't working, check the logs:
```bash
tail -f ~/Library/Logs/turbo_bridge.log
```

### Manual Restart
```bash
launchctl unload ~/Library/LaunchAgents/com.turbo.bridge.plist
launchctl load ~/Library/LaunchAgents/com.turbo.bridge.plist
```

### Disable Auto-Start
If you want to stop it from starting on login:
```bash
launchctl unload ~/Library/LaunchAgents/com.turbo.bridge.plist
rm ~/Library/LaunchAgents/com.turbo.bridge.plist
```

## 3. Configuration
The bridge runs on port **5050** by default. You can access the UI at:
`http://localhost:5050`
