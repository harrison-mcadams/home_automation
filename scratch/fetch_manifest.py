import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "streaming"))
import json
import base64
from playwright_extract import extract_stream

url = "https://ntv.cx/watch/kobra/usa-vs-belgium-2507707"
result = extract_stream(url)
if not result:
    print("Extraction failed")
    sys.exit(1)

page = result["_page"]
frame_url = result["frame_url"]
m3u8_url = result["url"]

target_frame = page.main_frame
for frame in page.frames:
    if frame.url == frame_url:
        target_frame = frame
        break

print(f"Master Playlist URL: {m3u8_url}")
print(f"Target Frame URL: {target_frame.url}")

def fetch_url(target_url):
    res = target_frame.evaluate('''async (targetUrl) => {
        try {
            const resp = await fetch(targetUrl);
            const text = await resp.text();
            return { text: text };
        } catch (e) { return { error: e.toString() }; }
    }''', target_url)
    return res

# Fetch master playlist
master_res = fetch_url(m3u8_url)
if "error" in master_res:
    print(f"Error fetching master: {master_res['error']}")
else:
    print("--- MASTER PLAYLIST ---")
    print(master_res["text"])
    print("-----------------------")

    # Find first sub-playlist
    lines = master_res["text"].splitlines()
    for line in lines:
        if line.strip() and not line.strip().startswith("#"):
            sub_url = line.strip()
            import urllib.parse
            full_sub_url = urllib.parse.urljoin(m3u8_url, sub_url)
            print(f"Fetching sub-playlist: {full_sub_url}")
            sub_res = fetch_url(full_sub_url)
            if "error" in sub_res:
                print(f"Error: {sub_res['error']}")
            else:
                print("--- SUB PLAYLIST ---")
                print(sub_res["text"])
                print("--------------------")
            break

result["_browser_handle"].close()
result["_pw_handle"].stop()
