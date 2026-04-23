import sys
import os
import time
import shutil
import threading
from playwright.sync_api import sync_playwright

"""
PROBLEM SOLVING & ARCHITECTURE: playwright_extract.py
---------------------------------------------------
1. THE CHALLENGE: Aggressive Ad-Shields & Click-Jackers
   Modern sports streaming sites (like ntv.cx) use multiple layers of transparent overlays, 
   z-index manipulation, and "click-jacking" to force popups. Standard Playwright 
   automation often hangs or fails because it gets stuck on these zombie elements.

2. THE SOLUTION: "Iron-Clad" Self-Correction
   - aggressive_popup_closer: We hook into the Playwright context to instantly close 
     ANY new tab/window that isn't the primary one.
   - self_correct_player: A recurring logic loop that scrolls, removes high z-index 
     overlays (using specific text and CSS selectors), and forces 'play()' on any 
     video element it finds.

3. CONCURRENCY: The "Wait-Loop" Problem
   - Standard time.sleep() blocks Playwright's internal event loop in sync_api, 
     preventing manifest detection callbacks from firing.
   - We use page.wait_for_timeout() and threading.Event (found_event) to ensure 
     the main thread stays responsive while the browser captures traffic.
"""

def extract_stream(url, timeout_secs=60):
    """
    Performs high-resiliency extraction of HLS/M3U8 streams.
    Returns a dict containing the URL, headers, and browser handles for session persistence.
    """
    target_m3u8 = None
    target_headers = {}
    found_event = threading.Event() # Thread-safe signal for the main loop
    
    # Start Playwright and keep it alive (do NOT use 'with' context manager here)
    p = sync_playwright().start()
    browser = None
    
    print(f"[*] Starting Stable Extraction for: {url}", file=sys.stderr)

    launch_args = {
        'headless': False, # Visible browser allows for easier debugging and "human-like" behavior
        'args': [
            '--no-sandbox', 
            '--disable-gpu',
            '--autoplay-policy=no-user-gesture-required' # Force autoplay for the player
        ]
    }
    try:
        browser = p.chromium.launch(**launch_args)
    except:
        browser = p.chromium.launch(headless=False)
            
    context = browser.new_context(viewport={'width': 1280, 'height': 720})
    
    # SECURITY: Prevent the site from spawning new windows via window.open
    context.add_init_script("""
        window.open = function() { 
            console.log("Blocked window.open call");
            return null; 
        };
    """)

    # NETWORK: Block common ad/tracking domains to reduce noise and prevent "heartbeat" 403s
    def block_ads(route):
        ad_domains = ["doubleclick", "adcash", "crowncoinscasino", "rainbet", "google-analytics", "fubo.tv", "insulinoustcave"]
        if any(domain in route.request.url for domain in ad_domains):
            return route.abort()
        return route.continue_()
    context.route("**/*", block_ads)

    page = context.new_page()

    # POPUP SHIELD: Close any surprise tabs immediately
    def handle_popup(popup):
        try:
            popup.close()
            print(f"[*] Aggressively closed popup: {popup.url}", file=sys.stderr)
        except: pass
    context.on("page", handle_popup)
    
    # TRAFFIC INTERCEPTION: This is the core discovery engine
    def handle_request(request):
        nonlocal target_m3u8, target_headers
        u = request.url
        u_low = u.lower()
        
        # Log all potential media traffic for debugging visibility
        if any(ext in u_low for ext in [".m3u8", ".mpd", "playlist", "chunklist"]):
            print(f"[*] Potential Traffic: {u[:100]}...", file=sys.stderr)
            
        # Target the final index/master manifest
        if ".m3u8" in u_low and "telemetry" not in u_low:
            # Prioritize index/master over small chunks
            if not target_m3u8 or "index.m3u8" in u_low or "master.m3u8" in u_low:
                target_m3u8 = u
                # Capture the headers EXACTLY as sent by the browser to preserve session tokens
                target_headers = {k: v for k, v in request.headers.items()}
                
                # RECOVERY: Sometimes Referer is truncated in standard headers; we pull it from the frame
                try:
                    frame_url = request.frame.url
                    if frame_url and len(frame_url) > len(target_headers.get('Referer', '')):
                         target_headers['Referer'] = frame_url
                         if 'referer' in target_headers: del target_headers['referer']
                except: pass
                
                print(f"[!] Target Found: {target_m3u8}", file=sys.stderr)
                found_event.set() # Signal the main loop to proceed

    page.on("request", handle_request)

    try:
        print(f"[*] Navigating...", file=sys.stderr)
        page.goto(url, wait_until="commit", timeout=timeout_secs*1000)
        
        # INITIAL AD-BURN: Wait for the first wave of overlays to manifest
        print(f"[*] Burning Ad-Overlays (Visual Phase)...", file=sys.stderr)
        time.sleep(5)
        self_correct_player(page)
        
        # MONITORING LOOP: Wait for the manifest to appear in network traffic
        print(f"[*] Waiting for stream initialization...", file=sys.stderr)
        for i in range(60): 
            if found_event.is_set():
                print(f"[*] Capturing final state...", file=sys.stderr)
                page.wait_for_timeout(1000) # Small delay to let headers settle
                try:
                    # Final cookie sync
                    cookies = page.context.cookies()
                    if cookies:
                        target_headers['Cookie'] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                except: pass
                
                print(f"[+] Extraction successful!", file=sys.stderr)
                # Return everything needed to keep the session alive in the main routine
                return {
                    "url": target_m3u8, 
                    "headers": target_headers, 
                    "_browser_handle": browser, 
                    "_pw_handle": p,
                    "_context": context,
                    "_page": page
                }
            
            # RECURRING SELF-CORRECT: Every 5s, we re-check for ad-overlays that might have popped up
            if i % 5 == 0:
                print(f"[*] Keep-alive/self-correct (step {i})...", file=sys.stderr)
                self_correct_player(page)
            
            # Use Playwright's wait to keep the JS engine alive
            page.wait_for_timeout(1000)

    except Exception as e:
        print(f"(!) Extraction Error: {e}", file=sys.stderr)
        if browser: browser.close()
        p.stop()

    return None

def self_correct_player(page, timeout=5000):
    """
    Visual sanitization routine. Removes transparent overlays and forces 'Play'.
    """
    try:
        page.bring_to_front()
        page.evaluate("window.scrollTo(0, 500)") # Scroll to bypass some 'view-required' ad logic
        
        for frame in page.frames:
            try:
                frame.evaluate('''() => {
                    // Identify and remove common ad/overlay patterns
                    const badSelectors = ['div[style*="z-index: 1"]', '#preact-border-shadow-host', '#adCloseBtn', '.vjs-ad-playing', '.vjs-ad-loading'];
                    badSelectors.forEach(s => {
                        document.querySelectorAll(s).forEach(el => {
                            if (!el.querySelector('video')) el.remove();
                        });
                    });
                    
                    // Kill "Top paying jobs" and other common bait-ads
                    document.querySelectorAll('div, section, aside').forEach(el => {
                        if (el.innerText && (el.innerText.includes("Top paying jobs") || el.innerText.includes("Watch Without Interruptions"))) {
                             el.remove();
                        }
                    });
                    
                    // Kill high z-index glassmorphism layers
                    document.querySelectorAll('*').forEach(el => { 
                        const z = parseInt(window.getComputedStyle(el).zIndex);
                        if(z > 100 && !el.querySelector('video')) el.remove(); 
                    });

                    // Force the player to play
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
    except: pass
