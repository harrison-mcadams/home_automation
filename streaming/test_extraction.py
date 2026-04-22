
from playwright_extract import extract_stream
import json

url = "https://ntv.cx/watch/kobra/buffalo-sabres-vs-boston-bruins-2465704"
print(f"Testing extraction for: {url}")
result = extract_stream(url)

if result:
    print("Extraction successful!")
    print(json.dumps(result, indent=2))
else:
    print("Extraction failed.")
