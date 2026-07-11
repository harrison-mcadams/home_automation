from playwright_extract import extract_stream
import json

url = "https://ntv.cx/watch/kobra/usa-vs-belgium-2507707"
print(f"Testing extraction for: {url}")
result = extract_stream(url)

if result:
    print("Extraction successful!")
    # Remove browser handles from printable output
    clean_result = {k: v for k, v in result.items() if not k.startswith('_')}
    print(json.dumps(clean_result, indent=2))
else:
    print("Extraction failed.")
