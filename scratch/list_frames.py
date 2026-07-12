import sys
from playwright.sync_api import sync_playwright

url = "https://ntv.cx/watch/kobra/usa-vs-belgium-2507707"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        page.goto(url, wait_until="commit", timeout=30000)
        page.wait_for_timeout(5000)
        print("Frames found on page:")
        for idx, frame in enumerate(page.frames):
            print(f"[{idx}] {frame.url}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
