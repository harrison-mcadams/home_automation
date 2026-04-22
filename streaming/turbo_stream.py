import sys
import subprocess
import os
import platform
import shutil
from playwright_extract import extract_stream

def find_player():
    """
    Finds a suitable native player on the system.
    Prioritizes mpv, then vlc.
    """
    players = []
    
    if platform.system() == "Windows":
        # Common Windows paths
        players.append(shutil.which("mpv"))
        players.append(shutil.which("vlc"))
        
        # fallback paths if not in PATH
        potential_paths = [
            r"C:\Program Files\mpv\mpv.exe",
            r"C:\tools\mpv\mpv.exe",
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        for p in potential_paths:
            if os.path.exists(p):
                players.append(p)
    else:
        # Mac/Linux paths
        players.append(shutil.which("mpv"))
        players.append(shutil.which("vlc"))
        
        potential_paths = [
            "/usr/local/bin/mpv",
            "/opt/homebrew/bin/mpv",
            "/Applications/mpv.app/Contents/MacOS/mpv",
            "/Applications/VLC.app/Contents/MacOS/VLC",
        ]
        for p in potential_paths:
            if os.path.exists(p):
                players.append(p)

    # Filter out None and return the first valid one
    valid_players = [p for p in players if p]
    return valid_players[0] if valid_players else None

def play_native(stream_data):
    """
    Main playback logic. Prioritizes Streamlink as an engine, 
    then fallbacks to direct player launch.
    """
    url = stream_data.get("url")
    headers = stream_data.get("headers", {})
    
    if not url:
        print("(!) Error: No stream URL provided.")
        return False

    # 1. Try Streamlink (Most robust for 403/CDN bypass)
    if shutil.which("streamlink"):
        if play_with_streamlink(stream_data):
            return True
            
    # 2. Fallback to direct player
    return play_direct(stream_data)

def play_with_streamlink(stream_data):
    """
    Uses streamlink to proxy headers and session, resolving 403 issues.
    """
    url = stream_data.get("url")
    headers = stream_data.get("headers", {})
    
    print("[*] Launching via Streamlink engine (robust mode)...")
    
    cmd = ["streamlink"]
    
    # Map headers to streamlink format
    exclude_headers = ["content-type", "content-length", "host", "frame_url", "connection", "accept-encoding"]
    for k, v in headers.items():
        if k.lower() not in exclude_headers:
            # Streamlink uses KEY=VALUE format for http-header
            cmd.extend(["--http-header", f"{k}={v}"])
            
    # Use hls:// prefix for m3u8 to force HLS plugin
    stream_url = f"hls://{url}" if ".m3u8" in url.lower() else url
    cmd.extend([stream_url, "best"])
    
    # If we found a player, tell streamlink to use it
    player_path = find_player()
    if player_path:
        cmd.extend(["--player", player_path])
        
    print(f"[*] Command: {' '.join(cmd)}")
    try:
        subprocess.Popen(cmd)
        print("[+] Streamlink started successfully.")
        return True
    except Exception as e:
        print(f"(!) Streamlink failed: {e}")
        return False

def play_direct(stream_data):
    """
    Original direct player launch logic (fallback).
    """
    url = stream_data.get("url")
    headers = stream_data.get("headers", {})
    
    player_path = find_player()
    if not player_path:
        print("(!) Error: No native player (mpv/vlc) found on this system.")
        print(f"Captured Stream URL: {url}")
        print(f"Headers: {headers}")
        return False

    print(f"[*] Found player: {player_path}")
    
    is_mpv = "mpv" in player_path.lower()
    
    cmd = [player_path, url]
    
    if is_mpv:
        # mpv --http-header-fields="Referer: ..., User-Agent: ..."
        header_strings = []
        for k, v in headers.items():
            # Filter headers that mpv might not like or doesn't need
            if k.lower() in ["referer", "user-agent", "origin", "cookie"]:
                header_strings.append(f"{k}: {v}")
        
        if header_strings:
            cmd.append(f"--http-header-fields={','.join(header_strings)}")
            
        # Optimization for MacBook/Strong PC
        cmd.append("--cache=yes")
        cmd.append("--demuxer-max-bytes=100M")
        cmd.append("--demuxer-max-back-bytes=50M")
        
    else:
        # vlc --http-referrer="..." --http-user-agent="..."
        if headers.get("referer"):
            cmd.append(f"--http-referrer={headers['referer']}")
        if headers.get("user-agent"):
            cmd.append(f"--http-user-agent={headers['user-agent']}")

    print(f"[*] Launching: {' '.join(cmd)}")
    try:
        # Use Popen to launch without blocking the Python script
        subprocess.Popen(cmd)
        print("[+] Player launched successfully.")
        return True
    except Exception as e:
        print(f"(!) Failed to launch player: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python turbo_stream.py <web_url>")
        # Default test URL if none provided
        test_url = "https://ntv.cx/watch/kobra/buffalo-sabres-vs-boston-bruins-2465704"
        print(f"No URL provided. Testing with default: {test_url}")
        target_url = test_url
    else:
        target_url = sys.argv[1]

    print(f"[*] Starting Turbo Extraction for: {target_url}")
    # Force headful mode for "Turbo" version if on a strong machine
    # We can detect horsepower or just default to False (headless) for performance, 
    # but the user wanted to "take advantage of horse power".
    # I'll keep it headless by default in the extractor but we could override.
    
    stream_results = extract_stream(target_url)
    
    if stream_results:
        print("[+] Extraction successful!")
        play_native(stream_results)
    else:
        print("[-] Extraction failed. See debug_pi_view.png for details.")
