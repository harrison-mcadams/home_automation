import machine
import utime
import sys
import select

# Pins
tx_pin = machine.Pin(15, machine.Pin.OUT)
rx_pin = machine.Pin(14, machine.Pin.IN)

def transmit_code(code, protocol, pulse_length):
    p = int(pulse_length)
    for _ in range(25):
        for i in range(23, -1, -1):
            if (code >> i) & 1:
                tx_pin.value(1); utime.sleep_us(p * 3); tx_pin.value(0); utime.sleep_us(p)
            else:
                tx_pin.value(1); utime.sleep_us(p); tx_pin.value(0); utime.sleep_us(p * 3)
        tx_pin.value(1); utime.sleep_us(p); tx_pin.value(0); utime.sleep_us(p * 31)

def sniff_mode():
    print("READY_TO_SNIFF")
    deadline = utime.ticks_add(utime.ticks_ms(), 5000)
    findings = {}
    
    while utime.ticks_diff(deadline, utime.ticks_ms()) > 0:
        low_count = 0
        while rx_pin.value() == 0:
            utime.sleep_us(50)
            low_count += 50
            if low_count > 10000: break
        
        if low_count > 3000:
            code = 0; success = True
            for i in range(24):
                t1 = utime.ticks_us()
                while rx_pin.value() == 1:
                    if utime.ticks_diff(utime.ticks_us(), t1) > 2000: break
                high_dur = utime.ticks_diff(utime.ticks_us(), t1)
                
                t2 = utime.ticks_us()
                while rx_pin.value() == 0:
                    if utime.ticks_diff(utime.ticks_us(), t2) > 2000: break
                low_dur = utime.ticks_diff(utime.ticks_us(), t2)
                
                if high_dur > 1500 or low_dur > 1500:
                    success = False; break
                
                if high_dur > low_dur: code = (code << 1) | 1
                else: code = (code << 1) | 0
            
            if success and code > 0:
                print(f"SAMPLE:{code}")
                findings[code] = findings.get(code, 0) + 1
                # Short sleep to avoid double-processing the same burst
                utime.sleep_ms(50)

    if findings:
        # Find the most common code
        best_code = max(findings, key=findings.get)
        print(f"FOUND:{best_code}")
    else:
        print("TIMEOUT")

print("PICO RF READY")

buffer = ""
while True:
    if select.select([sys.stdin], [], [], 0.01)[0]:
        char = sys.stdin.read(1)
        if char == '\n':
            line = buffer.strip()
            if line == "SNIFF":
                sniff_mode()
            elif "," in line:
                try:
                    parts = line.split(',')
                    c = int(parts[0]); pr = int(parts[1]); pl = int(parts[2])
                    print(f"TX: {c}")
                    transmit_code(c, pr, pl)
                    print("Done.")
                except: pass
            buffer = ""
        else:
            buffer += char
