import serial
import time
import sys
import argparse
import json
import os

# Config
DEFAULT_PORT = "/dev/cu.usbmodem1442201"
FILES_DIR = os.path.dirname(__file__)
CODES_FILE = os.path.join(FILES_DIR, "remote_codes.json")

def main():
    parser = argparse.ArgumentParser(description='Interactive Sniffing Wizard')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, help="Serial port of the Pico")
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, 115200, timeout=1)
        time.sleep(1)
        
        # Load current data if it exists
        if os.path.exists(CODES_FILE):
            with open(CODES_FILE, 'r') as f:
                codes_db = json.load(f)
        else:
            codes_db = {}

        print("\n🧙 RF SNIFFING WIZARD")
        print("--------------------")
        
        target_buttons = [1, 2, 3, 4, 5]
        target_states = ["ON", "OFF"]
        
        for btn in target_buttons:
            for state in target_states:
                key = f"{btn} {state}"
                print(f"\n👉 TARGET: [{key}]")
                
                captured_samples = []
                while len(captured_samples) < 2:
                    current_count = len(captured_samples) + 1
                    input(f"   [{current_count}/2] Hold {key} and press ENTER to sniff...")
                    
                    ser.write(b"SNIFF\n")
                    found_code = None
                    
                    # Capture loop
                    start_time = time.time()
                    while time.time() - start_time < 8:
                        line = ser.readline().decode().strip()
                        if line.startswith("FOUND:"):
                            found_code = int(line.split(":")[1])
                            break
                        elif line == "TIMEOUT":
                            break
                    
                    if found_code:
                        # 🧠 SMART FILTER:
                        # Your remote uses the 0x44xxxx address space. 
                        # Anything else is likely a neighbor or static.
                        found_hex = hex(found_code)
                        if not (found_hex.startswith("0x44") or found_hex.startswith("0x45")):
                            print(f"      🗑️ REJECTED NOISE: {found_code} ({found_hex})")
                            continue
                            
                        print(f"      Captured: {found_code}")
                        captured_samples.append(found_code)
                        
                        # If we have two samples that don't match, we need a third!
                        if len(captured_samples) == 2 and captured_samples[0] != captured_samples[1]:
                            print("      ⚠️ Mismatch detected! Need a third sample for tie-break...")
                    else:
                        print("      ❌ Timeout. Let's try that one again.")

                # Decision logic
                if captured_samples[0] == captured_samples[1]:
                    final_code = captured_samples[0]
                    print(f"   ✅ CONSISTENT: {final_code}")
                else:
                    # Need a 3rd sample
                    input(f"   [3/3 TIE-BREAKER] Hold {key} and press ENTER...")
                    ser.write(b"SNIFF\n")
                    # Simplified capture for the 3rd one
                    third_code = None
                    start_time = time.time()
                    while time.time() - start_time < 8:
                        line = ser.readline().decode().strip()
                        if line.startswith("FOUND:"):
                            third_code = int(line.split(":")[1]); break
                    
                    # Take the most frequent one
                    all_three = captured_samples + [third_code] if third_code else captured_samples
                    final_code = max(set(all_three), key=all_three.count)
                    print(f"   ✅ CONSENSUS: {final_code}")

                if final_code:
                    codes_db[key] = {
                        "code": final_code,
                        "pulselength": 150,
                        "protocol": 1
                    }
                    with open(CODES_FILE, 'w') as f:
                        json.dump(codes_db, f, indent=2)

        print("\n🎉 ALL DONE! Your remote_codes.json is updated.")
        ser.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    main()
