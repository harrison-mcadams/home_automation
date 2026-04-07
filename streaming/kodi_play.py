import sys
import argparse
import requests
from urllib.parse import urlparse, quote

# Import our new cleanly-exposed Python extraction logic!
from playwright_extract import extract_stream

# Kodi Configuration
KODI_HOST = "puck-server.tailcfee0c.ts.net" # Tailscale IP or Local Pi IP
KODI_PORT = "8080"
KODI_USER = "kodi"
KODI_PASS = "flyers2026"

def cast_to_kodi(stream_data):
    """
    Takes a stream dict (url, headers) and casts to Kodi via JSON-RPC.
    Handles Kodi's specific |Header=value format natively.
    """
    
    url = stream_data.get("url")
    headers = stream_data.get("headers", {})
    
    if not url:
        print("(!) Error: Empty stream URL provided to Kodi")
        return False
        
    ua = quote(headers.get('user-agent', 'Mozilla/5.0'))
    ref = quote(headers.get('referer', ''))
    origin = quote(headers.get('origin', ''))
    
    # Formats the string to standard Kodi |Header=val format automatically
    kodi_formatted_url = f"{url}|User-Agent={ua}&Referer={ref}&Origin={origin}"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "Player.Open",
        "params": {"item": {"file": kodi_formatted_url}},
        "id": 1
    }

    auth = (KODI_USER, KODI_PASS)
    rpc_url = f"http://{KODI_HOST}:{KODI_PORT}/jsonrpc"
    
    print(f"[*] Dispatching stream to Kodi...")
    try:
        response = requests.post(rpc_url, json=payload, auth=auth, timeout=10)
        response.raise_for_status()
        if response.json().get('result') == "OK":
            print("[+] Success: Playback command accepted by Kodi.")
            return True
            
    except requests.exceptions.ReadTimeout:
        # Expected behavior during HLS initial buffering
        print("[+] Success: Kodi accepted the request! (It took >10s to reply, likely because it is buffering the stream right now).")
        return True
        
    except Exception as e:
        print(f"(!) RPC Call Failed: {e}")
        
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Puck Automatic Stream Caster")
    parser.add_argument("--url", help="Direct HLS/M3U8 link to cast immediately")
    parser.add_argument("--game-url", help="Streamed.pk game URL to natively extract and cast")
    parser.add_argument("--team", help="Friendly team name to brute-force parse (e.g. 'new-jersey-devils')")
    
    args = parser.parse_args()

    if args.url:
        # If user passes direct, we assume no complex headers needed
        cast_to_kodi({"url": args.url, "headers": {}})
        
    elif args.game_url:
        print(f"[*] Discovery engine starting for: {args.game_url}")
        stream_data = extract_stream(args.game_url)
        if stream_data:
            print(f"[+] Extraction complete. URL: {stream_data['url']}")
            cast_to_kodi(stream_data)
        else:
            print("[-] Extraction failed.")
            
    elif args.team:
        print(f"[*] Target Discovery for '{args.team}'...")
        # Friendly URL guesser
        game_url_guess = f"https://streamed.pk/watch/ppv-{args.team}"
        stream_data = extract_stream(game_url_guess)
        if stream_data:
             cast_to_kodi(stream_data)
        else:
             print("[-] Extraction failed.")
             
    else:
        parser.print_help()
