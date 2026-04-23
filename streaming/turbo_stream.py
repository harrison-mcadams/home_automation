import sys
import os
import json
import subprocess
import shutil
import time
import threading
import urllib.parse
import queue
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from playwright_extract import extract_stream

# Global state
_persistence_handles = []
_proxy_work_queue = queue.Queue()

class StreamProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        target_url = query.get('url', [None])[0]

        if not target_url:
            self.send_response(400)
            self.end_headers()
            return

        resp_q = queue.Queue()
        _proxy_work_queue.put({'url': target_url, 'response_queue': resp_q})
        
        try:
            result = resp_q.get(timeout=30)
            if 'error' in result: raise Exception(result['error'])
                
            self.send_response(result['status'])
            for k, v in result['headers'].items():
                k_low = k.lower()
                if k_low not in ['content-length', 'content-encoding', 'transfer-encoding', 'connection', 'content-type']:
                    self.send_header(k, v)
            
            if 'content-type' in result['headers']:
                 self.send_header('Content-Type', result['headers']['content-type'])
            elif ".m3u8" in target_url.lower():
                 self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            
            body = result['body']
            if ".m3u8" in target_url.lower():
                try:
                    content = body.decode('utf-8', errors='ignore')
                    new_lines = []
                    base_url = target_url.rsplit('/', 1)[0] + '/'
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith('#'):
                            seg_url = urllib.parse.urljoin(base_url, line)
                            new_lines.append(f"http://127.0.0.1:{self.server.server_port}/proxy?url={urllib.parse.quote(seg_url)}")
                        else: new_lines.append(line)
                    body = "\n".join(new_lines).encode('utf-8')
                except: pass

            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"(!) Proxy Error: {e}", file=sys.stderr)
            self.send_response(500)
            self.end_headers()

def start_proxy_server():
    server = HTTPServer(('127.0.0.1', 0), StreamProxyHandler)
    port = server.server_port
    print(f"[*] Proxy Server started on port {port}", file=sys.stderr)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port

def main_loop(page):
    """
    Pinned to the main thread to perform fetches via the browser window.
    Searches for the correct iframe to bypass CORS.
    """
    print("[*] Nuclear Proxy active. Using browser-native fetch.", file=sys.stderr)
    
    while True:
        try:
            task = _proxy_work_queue.get(timeout=0.1)
            url = task['url']
            q = task['response_queue']
            
            try:
                # Find the best frame for fetching (the one on the authorized origin)
                target_frame = page.main_frame
                for frame in page.frames:
                    if "pooembed" in frame.url or "modifiles" in frame.url:
                        target_frame = frame
                        break
                
                # Perform the fetch INSIDE the found frame
                result = target_frame.evaluate('''async (targetUrl) => {
                    try {
                        const resp = await fetch(targetUrl, { mode: 'cors' });
                        const buf = await resp.arrayBuffer();
                        const headers = {};
                        resp.headers.forEach((v, k) => headers[k] = v);
                        
                        const uint8 = new Uint8Array(buf);
                        let binary = '';
                        const len = uint8.byteLength;
                        for (let i = 0; i < len; i += 8192) {
                            binary += String.fromCharCode.apply(null, uint8.subarray(i, i + 8192));
                        }
                        
                        return {
                            status: resp.status,
                            headers: headers,
                            bodyBase64: btoa(binary)
                        };
                    } catch (e) {
                        return { error: e.toString() };
                    }
                }''', url)
                
                if 'error' in result:
                    q.put({'error': result['error']})
                else:
                    q.put({
                        'status': result['status'],
                        'headers': result['headers'],
                        'body': base64.b64decode(result['bodyBase64'])
                    })
            except Exception as e:
                q.put({'error': str(e)})
        except queue.Empty: pass
        except KeyboardInterrupt: break
        time.sleep(0.01)

def play_native(stream_data, target_url):
    url = stream_data.get("url")
    page = stream_data.get("_page")
    
    if "modifiles.fans" in url.lower() or "netanyahu" in url.lower():
        print("[*] Sensitive CDN detected. Engaging Nuclear Proxy...", file=sys.stderr)
        proxy_port = start_proxy_server()
        proxy_url = f"http://127.0.0.1:{proxy_port}/proxy?url={urllib.parse.quote(url)}"
        
        # Start the player
        player_path = find_player()
        if player_path:
            subprocess.Popen([player_path, proxy_url, "--cache=yes", "--demuxer-max-bytes=150M"])
        
        # Enter the event loop
        main_loop(page)
        return True

    # Standard path
    if shutil.which("streamlink"):
        if play_with_streamlink(stream_data): return True
    return play_direct(stream_data)

def find_player():
    for p in [r"C:\Program Files\MPV Player\mpv.exe", r"C:\Program Files\VideoLAN\VLC\vlc.exe", "mpv", "vlc"]:
        if shutil.which(p): return shutil.which(p)
    return None

def play_with_streamlink(stream_data):
    url, headers = stream_data.get("url"), stream_data.get("headers", {})
    cmd = ["streamlink"]
    for k, v in headers.items():
        if k.lower() not in ['host', 'connection', 'content-length']:
            cmd.extend(["--http-header", f"{k}={v}"])
    cmd.extend([url, "best"])
    player_path = find_player()
    if player_path: cmd.extend(["--player", player_path])
    try:
        subprocess.Popen(cmd)
        return True
    except: return False

def play_direct(stream_data):
    url, headers = stream_data.get("url"), stream_data.get("headers", {})
    player_path = find_player()
    if not player_path: return False
    cmd = [player_path, url]
    if "mpv" in player_path.lower():
        if "User-Agent" in headers: cmd.append(f"--user-agent={headers['User-Agent']}")
        if "Referer" in headers: cmd.append(f"--referrer={headers['Referer']}")
        h_fields = [f"{k}: {v}" for k, v in headers.items() if k.lower() not in ['host', 'connection']]
        if h_fields: cmd.append(f'--http-header-fields={",".join(h_fields)}')
        cmd.extend(["--cache=yes", "--demuxer-max-bytes=150M"])
    try:
        subprocess.Popen(cmd)
        return True
    except: return False

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    target_url = sys.argv[1]
    stream_data = extract_stream(target_url)
    if not stream_data: sys.exit(1)
    if "_browser_handle" in stream_data: _persistence_handles.append(stream_data["_browser_handle"])
    if "_pw_handle" in stream_data: _persistence_handles.append(stream_data["_pw_handle"])
    play_native(stream_data, target_url)
