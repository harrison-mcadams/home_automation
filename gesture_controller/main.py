import cv2
import mediapipe as mp
import requests
import time
import threading
import argparse

# Configuration
# IP Webcam URL - Replace with the actual URL from your Android app
DEFAULT_VIDEO_URL = "http://192.168.1.97:8080/video"
# Home Automation API URL
API_URL = "http://puck-server.tailcfee0c.ts.net:5000/api/control"

# Constants
DEBOUNCE_TIME = 2.0  # Seconds between commands

class ThreadedCamera:
    """Reads frames in a separate thread to always ensure the latest frame is processed."""
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Try to minimize buffer
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.src = src
        
    def start(self):
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.grabbed:
                # If stream connection is lost, check if we need to reconnect
                pass 
            
            (grabbed, frame) = self.stream.read()
            if grabbed:
                self.grabbed = True
                self.frame = frame
            else:
                self.grabbed = False
                # If reading fails, maybe wait a bit to avoid hot loop
                time.sleep(0.1)

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()

class GestureController:
    def __init__(self, source, headless=False, target_fps=15, complexity=0):
        self.source = source
        self.headless = headless
        self.target_fps = target_fps
        self.frame_duration = 1.0 / target_fps
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            model_complexity=complexity, # 0=Lite, 1=Full
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.4
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # State Machine
        self.state = "IDLE" # IDLE, READY, COOLDOWN
        self.state_time = 0
        self.ready_timeout = 3.0 # Seconds to wait for command after fist
        self.cooldown_time = 0.5
        
        # Toggle State Tracking (1-5)
        self.light_states = {i: False for i in range(1, 6)}

    def send_command(self, light_id):
        """Toggle light_id (1-5)"""
        # ... (same as before) ...
        if light_id not in self.light_states:
            return

        # Flip state
        new_state = not self.light_states[light_id]
        self.light_states[light_id] = new_state
        
        suffix = "ON" if new_state else "OFF"
        button_name = f"{light_id} {suffix}"
        
        def _send():
            try:
                print(f"Sending command: {button_name}...")
                response = requests.post(API_URL, json={'button': button_name}, timeout=5)
                if response.status_code == 200:
                    print(f"Success: {button_name}")
                else:
                    print(f"Failed: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"Error sending command: {e}")

        threading.Thread(target=_send, args=(), daemon=True).start()
        return f"{button_name}"

    def get_finger_status(self, landmarks):
        # ... (same as before) ...
        """
        Returns a list of booleans [Thumb, Index, Middle, Ring, Pinky] indicating if open.
        """
        # Thumb (4), Index (8), Middle (12), Ring (16), Pinky (20)
        finger_tips = [8, 12, 16, 20]
        finger_pips = [6, 10, 14, 18] 
        
        status = []
        
        # 0. Wrist
        wrist = landmarks[0]
        
        # --- Thumb Logic ---
        # Reverting to Pinky MCP (17) check as it was more robust for Closed Fist.
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        pinky_mcp = landmarks[17]
        
        dist_thumb_tip = ((thumb_tip.x - pinky_mcp.x)**2 + (thumb_tip.y - pinky_mcp.y)**2)**0.5
        dist_thumb_ip = ((thumb_ip.x - pinky_mcp.x)**2 + (thumb_ip.y - pinky_mcp.y)**2)**0.5
        
        # Open if Tip is Further from Pinky than IP is
        is_thumb_open = dist_thumb_tip > dist_thumb_ip
        status.append(is_thumb_open)
        
        # --- Fingers Logic ---
        for tip, pip in zip(finger_tips, finger_pips):
            tip_pt = landmarks[tip]
            pip_pt = landmarks[pip]
            
            # Distance from wrist
            dist_tip = ((tip_pt.x - wrist.x)**2 + (tip_pt.y - wrist.y)**2)**0.5
            dist_pip = ((pip_pt.x - wrist.x)**2 + (pip_pt.y - wrist.y)**2)**0.5
            
            status.append(dist_tip > dist_pip)
            
        return status

    def run(self):
        print(f"Connecting to video stream: {self.source}")
        camera = ThreadedCamera(self.source).start()
        
        time.sleep(1)
        
        if not camera.grabbed:
            print(f"Error: Could not open video stream from {self.source}.")
            camera.stop()
            return

        print("Running... Press Ctrl+C to stop.")
        
        prev_time = 0
        
        # Confirmation counters
        gesture_buffer = [] 
        BUFFER_SIZE = 5 # Frames to confirm gesture
        
        fist_frames = 0
        FIST_THRESHOLD = 5 # Require 5 consecutive frames of fist to arm
        
        try:
            while True:
                loop_start = time.time()
                
                img = camera.read()
                if img is None:
                    time.sleep(0.01)
                    continue
                
                if isinstance(self.source, int):
                    img = cv2.flip(img, 1)

                imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                results = self.hands.process(imgRGB)

                finger_count = -1
                finger_status = [False]*5
                
                if results.multi_hand_landmarks:
                    for hand_lms in results.multi_hand_landmarks:
                        if not self.headless:
                             self.mp_draw.draw_landmarks(img, hand_lms, self.mp_hands.HAND_CONNECTIONS)
                        
                        finger_status = self.get_finger_status(hand_lms.landmark)
                        
                        # Smart Thumb Logic
                        non_thumb_count = sum(finger_status[1:])
                        is_thumb_open = finger_status[0]
                        
                        if non_thumb_count == 4 and is_thumb_open:
                            finger_count = 5
                        else:
                            finger_count = non_thumb_count
                        
                        if not self.headless:
                             # Visualize Finger Status
                             h, w, c = img.shape
                             tips_ids = [4, 8, 12, 16, 20]
                             for idx, is_open in enumerate(finger_status):
                                 tid = tips_ids[idx]
                                 lm = hand_lms.landmark[tid]
                                 cx, cy = int(lm.x * w), int(lm.y * h)
                                 color = (0, 255, 0) if is_open else (0, 0, 255)
                                 cv2.circle(img, (cx, cy), 10, color, cv2.FILLED)
                
                # State Machine Logic
                current_time = time.time()
                message = ""
                # ... (Logic remains same, visualization separated) ...

                if self.state == "IDLE":
                    if finger_count == 0: 
                        fist_frames += 1
                        if fist_frames >= FIST_THRESHOLD:
                            self.state = "READY"
                            self.state_time = current_time
                            fist_frames = 0
                            print("System READY -> Waiting for command")
                    else:
                        fist_frames = 0
                
                elif self.state == "READY":
                    if current_time - self.state_time > self.ready_timeout:
                        self.state = "IDLE"
                        print("Timeout -> IDLE")
                    
                    elif finger_count >= 1 and finger_count <= 5:
                        if len(gesture_buffer) < BUFFER_SIZE:
                             gesture_buffer.append(finger_count)
                        else:
                            if all(x == finger_count for x in gesture_buffer):
                                cmd = self.send_command(finger_count)
                                print(f"ACTION: {cmd}")
                                self.state = "COOLDOWN"
                                self.state_time = current_time
                                gesture_buffer = []
                            else:
                                gesture_buffer.pop(0)
                                gesture_buffer.append(finger_count)
                    else:
                        gesture_buffer = [] 
                        
                elif self.state == "COOLDOWN":
                    if current_time - self.state_time > self.cooldown_time:
                        self.state = "IDLE"

                # Display info only if not headless
                if not self.headless:
                    # FPS
                    curr_time = time.time()
                    fps = 1 / (curr_time - prev_time) if prev_time else 0
                    prev_time = curr_time
                    cv2.putText(img, f"FPS: {int(fps)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    # State & Fingers
                    color = (200, 200, 200)
                    if self.state == "READY": color = (0, 255, 0)
                    elif self.state == "COOLDOWN": color = (0, 0, 255)

                    cv2.putText(img, f"State: {self.state}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)
                    
                    finger_names = ["T", "I", "M", "R", "P"]
                    status_str = " ".join([f"{n}:{'O' if s else 'C'}" for n, s in zip(finger_names, finger_status)])
                    cv2.putText(img, status_str, (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    
                    cv2.putText(img, f"Count: {finger_count}", (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                    
                    cv2.imshow("Gesture Control", img)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                
                # FPS Limiting
                elapsed = time.time() - loop_start
                if elapsed < self.frame_duration:
                    time.sleep(self.frame_duration - elapsed)

        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            camera.stop()
            if not self.headless:
                cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hand Gesture Control")
    parser.add_argument("--source", type=str, default=DEFAULT_VIDEO_URL, help="Video URL or camera index (default: IP Webcam)")
    parser.add_argument("--usb", action="store_true", help="Use default USB webcam (Index 0)")
    parser.add_argument("--headless", action="store_true", help="Run without GUI window")
    parser.add_argument("--fps", type=int, default=15, help="Target FPS limit (default: 15)")
    parser.add_argument("--complexity", type=int, default=0, choices=[0, 1], help="MediaPipe Model Complexity (0=Lite, 1=Full). Default 0.")
    
    args = parser.parse_args()
    
    source = args.source
    if args.usb:
        source = 0
    elif source.isdigit():
        source = int(source)
        
    print(f"Starting Gesture Control...")
    print(f"Source: {source}")
    print(f"Headless: {args.headless}")
    print(f"FPS Limit: {args.fps}")
    print(f"Model Complexity: {args.complexity}")
        
    controller = GestureController(source, headless=args.headless, target_fps=args.fps, complexity=args.complexity)
    controller.run()
