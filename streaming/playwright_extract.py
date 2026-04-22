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
        
        # Popup Killer (Handles ad redirects immediately)
        main_page = None
        def handle_popup(popup):
            nonlocal main_page
            try:
                if main_page is None:
                    main_page = popup
                    return
                print(f"[!] Ad Popup Blocked: {popup.url}", file=sys.stderr)
                popup.close()
            except: pass
        context.on("page", handle_popup)
        
        page = context.new_page()
        main_page = page

        # Stealth Mode
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page.add_init_script("if (!window.chrome) { window.chrome = { runtime: {} }; }")
        
        # HLS Codec Spoofing
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
                # Exclude known tracking or placeholder m3u8s
                if "telemetry" in u or "log" in u:
                    return

                if not target_m3u8 or "index.m3u8" in u:
                    target_m3u8 = request.url
                    # Capture ALL headers for maximum robustness
                    target_headers = request.headers
                    
                    # Capture cookies from the context
                    try:
                        # Try to get cookies for BOTH the stream domain and the frame domain
                        urls_to_check = [request.url]
                        try: urls_to_check.append(request.frame.url)
                        except: pass
                        
                        cookies = request.frame.page.context.cookies(urls_to_check)
                        if cookies:
                            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                            target_headers['Cookie'] = cookie_str
                            print(f"[!] Cookies Captured: {len(cookies)} items", file=sys.stderr)
                    except Exception as e:
                        print(f"[*] Cookie capture warning: {e}", file=sys.stderr)

                    try:
                        target_headers['frame_url'] = request.frame.url
                        # Synthesize Origin if missing but Referer exists
                        if not target_headers.get('Origin') and target_headers.get('Referer'):
                            ref_url = target_headers['Referer']
                            target_headers['Origin'] = "/".join(ref_url.split("/")[:3])
                        elif not target_headers.get('origin') and target_headers.get('referer'):
                            ref_url = target_headers['referer']
                            target_headers['Origin'] = "/".join(ref_url.split("/")[:3])
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
            if "http" in text and (".m3u8" in text or "manifest" in text or "index.m3u8" in text):
                urls = re.findall(r'(https?://[^\s\'\"]+\.m3u8[^\s\'\"]*)', text)
                if urls and not target_m3u8:
                    target_m3u8 = urls[0]
                    print(f"[!] Console Found: {target_m3u8}", file=sys.stderr)

        page.on("console", handle_console)
        page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}", file=sys.stderr))

        try:
            # Step A: Load page
            print(f"[*] Navigating ({timeout_secs}s limit)...", file=sys.stderr)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_secs*1000)
            except Exception as e:
                print(f"[*] Navigation warning: {e}. Checking for intercepted traffic...", file=sys.stderr)
                
            if smart_wait(3): return {"url": target_m3u8, "headers": target_headers}
            
            # Step B: Fast Jump (Disabled as it may break session context for some providers)
            # if "/watch/" in url and not any(p in url for p in ["/admin/", "/delta/", "/echo/"]):
            #     print(f"[*] Game page detected. Jumping to provider...", file=sys.stderr)
            #     links = page.query_selector_all('a[href*="/watch/"]')
            #     for link in links:
            #         href = link.get_attribute("href")
            #         if href and ("admin/1" in href or "delta/1" in href or "embed?t=" in href):
            #             target_url = href if "://" in href else f"https://{url.split('/')[2]}{href}"
            #             print(f"[*] Jumping to: {target_url}", file=sys.stderr)
            #             try: page.goto(target_url, wait_until="domcontentloaded", timeout=10000)
            #             except: pass
            #             break
            #     if smart_wait(3): return {"url": target_m3u8, "headers": target_headers}

            # Step C: Nested Frame Penetration & Ad Burn
            if not target_m3u8:
                print(f"[*] Triggering player inside nested iframes (Persistent Mode)...", file=sys.stderr)
                
                # Wake up lazy-loaded frames
                page.evaluate("window.scrollTo(0, 500)")
                time.sleep(1)
                
                # Aggressive Native JS Clicks (7 passes to burn through ad layers)
                for pass_idx in range(7):
                    # We iterate all frames in case the player is deep
                    for frame in page.frames:
                        url_low = frame.url.lower()
                        if "blank" in url_low: continue
                        
                        try:
                            # Look for "Play" buttons, overlays, and common "Close Ad" selectors
                            js_click = '''
                                (function() {
                                    // 1. Kill common ad overlays first
                                    const adSelectors = [
                                        '.ad-popup-close', '#adPopupClose', '#discordFollowLater', 
                                        'div[class*="close"]', 'button[class*="close"]', 
                                        'div[id*="rainbet"]', 'div[class*="overlay"]'
                                    ];
                                    adSelectors.forEach(s => {
                                        document.querySelectorAll(s).forEach(el => {
                                            if (el.offsetParent !== null) el.click();
                                        });
                                    });

                                    // 2. Click play elements
                                    const playSelectors = ['div[class*="play"]', 'button[class*="play"]', 'svg[class*="play"]', '.vjs-big-play-button'];
                                    playSelectors.forEach(s => {
                                        document.querySelectorAll(s).forEach(el => {
                                            if (el.offsetParent !== null) el.click();
                                        });
                                    });

                                    // 3. Brute force click the center
                                    const el = document.elementFromPoint(window.innerWidth/2, window.innerHeight/2) || document.body;
                                    if(el) {
                                        const evts = ['mousedown', 'mouseup', 'click'];
                                        evts.forEach(et => el.dispatchEvent(new MouseEvent(et, {bubbles: true})));
                                    }
                                    
                                    // 4. Force video start
                                    document.querySelectorAll('video').forEach(v => {
                                        v.play().catch(() => {});
                                        v.muted = true; // Auto-play requires mute often
                                    });
                                })();
                            '''
                            frame.evaluate(js_click)
                        except: pass
                        
                    if smart_wait(2): break

            # Step D: Polling
            start_time = time.time()
            if not target_m3u8:
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
