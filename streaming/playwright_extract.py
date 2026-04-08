import sys
import time
import re
import platform
from pathlib import Path
from playwright.sync_api import sync_playwright

def extract_stream(url, timeout_secs=20):
    """
    Unified Stream Extractor.
    Automatically detects architecture to maximize robustness (native Chrome on PC, Chromium on Pi).
    Returns a dictionary: {"url": m3u8_url, "headers": {"referer": ..., "user-agent": ...}} or None
    """
    target_m3u8 = None
    target_headers = {}
    
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = data_dir / "debug_pi_view.png"
    
    print(f"[*] Turbo Launch for: {url}", file=sys.stderr)

    with sync_playwright() as p:
        
        is_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch64')
        
        # Platform intelligence
        if is_pi:
            # We assume Xvfb is running this script externally for headful Chromium execution
            launch_args = {'headless': False, 'args': ['--no-sandbox', '--autoplay-policy=no-user-gesture-required']}
        else:
            # PC/Mac: use out-of-the-box Chrome for proprietary codec support
            launch_args = {
                'headless': False, 
                'channel': 'chrome', 
                'args': ['--no-sandbox', '--autoplay-policy=no-user-gesture-required']
            }
            
        try:
            browser = p.chromium.launch(**launch_args)
        except Exception:
            if not is_pi:
                launch_args['channel'] = 'msedge'
                browser = p.chromium.launch(**launch_args)
            else:
                raise
                
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Stealth Mode
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page.add_init_script("if (!window.chrome) { window.chrome = { runtime: {} }; }")
        
        # HLS Codec Spoofing
        # Chrome natively returns 'no' for HLS (`application/vnd.apple.mpegurl`).
        # Tricking JWPlayer makes it blindly load the .m3u8 directly so we can intercept it.
        # ONLY DO THIS ON PC/MAC. Chromium on the Pi lacks proprietary codecs, meaning
        # spoofing native support will force a fatal C++ Demuxer error and kill the fetch!
        if not is_pi:
            mock_codec_script = """
            const originalCanPlayType = HTMLMediaElement.prototype.canPlayType;
            Object.defineProperty(HTMLMediaElement.prototype, 'canPlayType', {
                value: function(type) {
                    if (type && typeof type === 'string' && (type.includes('apple.mpegurl') || type.includes('m3u8') || type.includes('hls') || type.includes('mp4'))) {
                        return 'probably';
                    }
                    return originalCanPlayType.apply(this, arguments);
                }
            });
            """
            page.add_init_script(mock_codec_script)
        
        # Network Interceptor
        def handle_request(request):
            nonlocal target_m3u8, target_headers
            u = request.url.lower()
            if ".m3u8" in u:
                if not target_m3u8 and "placeholder" not in u:
                    target_m3u8 = request.url
                    target_headers = request.headers
                    try:
                        target_headers['frame_url'] = request.frame.url
                    except Exception:
                        pass
                    print(f"[!] Traffic Found: {target_m3u8}", file=sys.stderr)

        def smart_wait(seconds=5):
            for _ in range(int(seconds * 2)):
                if target_m3u8: return True
                time.sleep(0.5)
            return False

        page.on("request", handle_request)

        # Console Miner
        def handle_console(msg):
            nonlocal target_m3u8
            text = msg.text
            if "http" in text and (".m3u8" in text or "manifest" in text):
                urls = re.findall(r'(https?://[^\s\'\"]+\.m3u8[^\s\'\"]*)', text)
                if urls and not target_m3u8:
                    target_m3u8 = urls[0]
                    print(f"[!] Console Found: {target_m3u8}", file=sys.stderr)

        page.on("console", handle_console)

        try:
            # Step A: Load page
            print(f"[*] Navigating ({timeout_secs}s limit)...", file=sys.stderr)
            page.goto(url, wait_until="load", timeout=timeout_secs*1000)
            if smart_wait(3): return {"url": target_m3u8, "headers": target_headers}
            
            # Step B: Fast Jump
            if "/watch/" in url and not any(p in url for p in ["/admin/", "/delta/", "/echo/"]):
                print(f"[*] Game page detected. Jumping to provider...", file=sys.stderr)
                links = page.query_selector_all('a[href*="/watch/"]')
                for link in links:
                    href = link.get_attribute("href")
                    if href and ("admin/1" in href or "delta/1" in href):
                        target_url = href if "://" in href else f"https://{url.split('/')[2]}{href}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        break
                if smart_wait(3): return {"url": target_m3u8, "headers": target_headers}

            # Step C: Nested Frame Penetration
            if not target_m3u8:
                print(f"[*] Triggering player inside nested iframes...", file=sys.stderr)
                if smart_wait(2): return {"url": target_m3u8, "headers": target_headers}
                
                # Wake up lazy-loaded frames then snap back
                page.evaluate("window.scrollTo(0, 700)")
                if smart_wait(1): return {"url": target_m3u8, "headers": target_headers}
                page.evaluate("window.scrollTo(0, 0)")
                if smart_wait(1): return {"url": target_m3u8, "headers": target_headers}
                
                # Aggressive Native JS Clicks (3 passes)
                for pass_idx in range(3):
                    for frame in page.frames:
                        url_low = frame.url.lower()
                        if "blank" not in url_low:
                            print(f"[*] Aggressive click pass {pass_idx+1} on frame: {frame.url[:50]}...", file=sys.stderr)
                            try:
                                js_click = '''
                                    const el = document.elementFromPoint(window.innerWidth/2, window.innerHeight/2) || document.body;
                                    if(el) {
                                        el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                        el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                        el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                    }
                                    document.querySelectorAll('video').forEach(v => v.play().catch(e=>console.log(e)));
                                '''
                                frame.evaluate(js_click)
                            except Exception:
                                pass
                    if smart_wait(2): return {"url": target_m3u8, "headers": target_headers}

            # Step D: Polling
            start_time = time.time()
            print(f"[*] Final flush monitoring...", file=sys.stderr)
            while not target_m3u8 and (time.time() - start_time) < timeout_secs:
                time.sleep(1)

            if not target_m3u8:
                page.screenshot(path=str(screenshot_path))
                print(f"[-] Silent failure. Check {screenshot_path}", file=sys.stderr)

        except Exception as e:
            print(f"(!) Browser error: {e}", file=sys.stderr)
            try: page.screenshot(path=str(screenshot_path))
            except: pass
        finally:
            browser.close()

    if target_m3u8:
        return {"url": target_m3u8, "headers": target_headers}
    return None
