import sys
import os
import time
import shutil
import threading
from playwright.sync_api import sync_playwright

def extract_stream(url, timeout_secs=60):
    """
    Iron-clad Playwright extraction for ntv.cx and similar sites.
    Keeps the browser alive to maintain session persistence.
    """
    target_m3u8 = None
    target_headers = {}
    found_event = threading.Event()
    
    p = sync_playwright().start()
    browser = None
    
    print(f"[*] Starting Stable Extraction for: {url}", file=sys.stderr)

    launch_args = {
        'headless': False,
        'args': [
            '--no-sandbox', 
            '--disable-gpu',
            '--autoplay-policy=no-user-gesture-required'
        ]
    }
    try:
        browser = p.chromium.launch(**launch_args)
    except:
        browser = p.chromium.launch(headless=False)
            
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    
    # Iron-Clad Popup Prevention
    context.add_init_script("""
        window.open = function() { 
            console.log("Blocked window.open call");
            return null; 
        };
    """)

    # Block known ad domains
    def block_ads(route):
        ad_domains = ["doubleclick", "adcash", "crowncoinscasino", "rainbet", "google-analytics", "fubo.tv", "insulinoustcave"]
        if any(domain in route.request.url for domain in ad_domains):
            return route.abort()
        return route.continue_()
    context.route("**/*", block_ads)

    page = context.new_page()

    def handle_popup(popup):
        try:
            popup.close()
            print(f"[*] Aggressively closed popup: {popup.url}", file=sys.stderr)
        except: pass
    context.on("page", handle_popup)
    
    def handle_request(request):
        nonlocal target_m3u8, target_headers
        u = request.url
        u_low = u.lower()
        if any(ext in u_low for ext in [".m3u8", ".mpd", "playlist", "chunklist"]):
            print(f"[*] Potential Traffic: {u[:100]}...", file=sys.stderr)
            
        if ".m3u8" in u_low and "telemetry" not in u_low:
            if not target_m3u8 or "index.m3u8" in u_low or "master.m3u8" in u_low:
                target_m3u8 = u
                target_headers = {k: v for k, v in request.headers.items()}
                
                try:
                    frame_url = request.frame.url
                    if frame_url and len(frame_url) > len(target_headers.get('referer', '')) and len(frame_url) > len(target_headers.get('Referer', '')):
                         target_headers['Referer'] = frame_url
                         if 'referer' in target_headers: del target_headers['referer']
                except: pass
                
                # Ensure critical security headers are present for CORS compliance
                if 'Sec-Fetch-Dest' not in target_headers: target_headers['Sec-Fetch-Dest'] = 'empty'
                if 'Sec-Fetch-Mode' not in target_headers: target_headers['Sec-Fetch-Mode'] = 'cors'
                if 'Sec-Fetch-Site' not in target_headers: target_headers['Sec-Fetch-Site'] = 'cross-site'
                
                print(f"[!] Target Found: {target_m3u8}", file=sys.stderr)
                found_event.set()

    page.on("request", handle_request)

    try:
        print(f"[*] Navigating...", file=sys.stderr)
        page.goto(url, wait_until="commit", timeout=timeout_secs*1000)
        
        print(f"[*] Burning Ad-Overlays (Visual Phase)...", file=sys.stderr)
        time.sleep(5)
        self_correct_player(page)
        
        print(f"[*] Waiting for stream initialization...", file=sys.stderr)
        for i in range(60): 
            if found_event.is_set():
                print(f"[*] Capturing final state...", file=sys.stderr)
                page.wait_for_timeout(1000)
                try:
                    cookies = page.context.cookies()
                    if cookies:
                        target_headers['Cookie'] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                except: pass
                
                print(f"[+] Extraction successful!", file=sys.stderr)
                # Return handles and context so caller can keep session alive and perform proxied fetches
                return {
                    "url": target_m3u8, 
                    "headers": target_headers, 
                    "_browser_handle": browser, 
                    "_pw_handle": p,
                    "_context": context,
                    "_page": page
                }
            
            if i % 5 == 0:
                print(f"[*] Keep-alive/self-correct (step {i})...", file=sys.stderr)
                self_correct_player(page)
            
            page.wait_for_timeout(1000)

    except Exception as e:
        print(f"(!) Extraction Error: {e}", file=sys.stderr)
        if browser: browser.close()
        p.stop()

    return None

def self_correct_player(page, timeout=5000):
    try:
        page.bring_to_front()
        page.evaluate("window.scrollTo(0, 500)")
        
        for frame in page.frames:
            try:
                frame.evaluate('''() => {
                    const badSelectors = ['div[style*="z-index: 1"]', '#preact-border-shadow-host', '#adCloseBtn', '.vjs-ad-playing', '.vjs-ad-loading'];
                    badSelectors.forEach(s => {
                        document.querySelectorAll(s).forEach(el => {
                            if (!el.querySelector('video')) el.remove();
                        });
                    });
                    document.querySelectorAll('div, section, aside').forEach(el => {
                        if (el.innerText && (el.innerText.includes("Top paying jobs") || el.innerText.includes("Watch Without Interruptions"))) {
                             el.remove();
                        }
                    });
                    document.querySelectorAll('*').forEach(el => { 
                        const z = parseInt(window.getComputedStyle(el).zIndex);
                        if(z > 100 && !el.querySelector('video')) el.remove(); 
                    });
                    const selectors = ['.vjs-big-play-button', '#player_overlay', '.play-button', 'video'];
                    selectors.forEach(s => {
                        const el = document.querySelector(s);
                        if(el) {
                            el.click();
                            if (el.tagName === 'VIDEO') {
                                el.play().catch(()=>{});
                                el.muted = true;
                            }
                        }
                    });
                }''', timeout=timeout)
            except: pass
    except Exception as e:
        pass
