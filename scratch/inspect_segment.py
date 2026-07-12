import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "streaming"))
from playwright_extract import extract_stream

url = "https://ntv.cx/watch/kobra/usa-vs-belgium-2507707"
result = extract_stream(url)
if not result:
    print("Extraction failed")
    sys.exit(1)

page = result["_page"]
frame_url = result["frame_url"]

target_frame = page.main_frame
for frame in page.frames:
    if frame.url == frame_url:
        target_frame = frame
        break

# Paste one of the segment URLs
segment_url = "https://p16-common-sign.tiktokcdn.com/tos-alisg-avt-0068/929d9f63bade35a752e287a3fb843861~tplv-tiktokx-origin.image?dr=14575&refresh_token=4581a27e&x-expires=1783407600&x-signature=cKq4g9sJOn4nNK7sZI6YC4wip5k%3D&t=4d5b0474&ps=13740610&shp=f21f527a&shcp=9b759fb9&idc=my"

print(f"Fetching segment: {segment_url}")
res = target_frame.evaluate('''async (targetUrl) => {
    try {
        const resp = await fetch(targetUrl);
        const buf = await resp.arrayBuffer();
        const uint8 = new Uint8Array(buf);
        
        // Convert first 1000 bytes to array for python to print
        const head = Array.from(uint8.subarray(0, 1000));
        return { length: uint8.byteLength, head: head };
    } catch (e) { return { error: e.toString() }; }
}''', segment_url)

if "error" in res:
    print(f"Error: {res['error']}")
else:
    length = res["length"]
    head = bytes(res["head"])
    print(f"Successfully fetched segment of length: {length} bytes")
    print(f"First 16 bytes: {head[:16]}")
    print(f"First 16 bytes hex: {head[:16].hex()}")
    
    # Let's search for the TS sync byte pattern (0x47 repeating every 188 bytes)
    # Since we only downloaded the first 1000 bytes, let's find if the pattern starts in it.
    found_idx = -1
    for i in range(len(head) - 188 * 3):
        if head[i] == 0x47 and head[i+188] == 0x47 and head[i+188*2] == 0x47 and head[i+188*3] == 0x47:
            found_idx = i
            break
            
    if found_idx != -1:
        print(f"FOUND TS SYNC PATTERN STARTING AT INDEX: {found_idx}")
        print(f"Sync bytes at: {found_idx}, {found_idx+188}, {found_idx+188*2}, {found_idx+188*3}")
    else:
        print("TS sync pattern not found in first 1000 bytes. Let's do a wider search in python.")
        # Let's fetch the entire body to look deeper
        res_full = target_frame.evaluate('''async (targetUrl) => {
            try {
                const resp = await fetch(targetUrl);
                const buf = await resp.arrayBuffer();
                const uint8 = new Uint8Array(buf);
                let binary = '';
                const len = uint8.byteLength;
                for (let i = 0; i < len; i += 8192) {
                    binary += String.fromCharCode.apply(null, uint8.subarray(i, i + 8192));
                }
                return { bodyBase64: btoa(binary) };
            } catch (e) { return { error: e.toString() }; }
        }''', segment_url)
        
        import base64
        body = base64.b64decode(res_full["bodyBase64"])
        print(f"Full body size: {len(body)}")
        
        found_idx = -1
        for i in range(len(body) - 188 * 4):
            if body[i] == 0x47 and body[i+188] == 0x47 and body[i+188*2] == 0x47 and body[i+188*3] == 0x47:
                found_idx = i
                break
        if found_idx != -1:
            print(f"FOUND TS SYNC PATTERN STARTING AT INDEX (FULL BODY): {found_idx}")
        else:
            print("TS sync pattern not found anywhere in the file!")

result["_browser_handle"].close()
result["_pw_handle"].stop()
