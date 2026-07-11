import os
import sys
import cv2
import numpy as np
import mediapipe as mp
import requests
import time
import json
import threading
import argparse

# Reconfigure stdout to support unicode emojis on all terminals
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Config File Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
CALIBRATION_FILE = os.path.join(SCRIPT_DIR, "calibration_data.json")

class ThreadedCamera:
    """Reads frames in a separate thread to ensure low-latency frame acquisition."""
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.src = src
        
    def start(self):
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.grabbed:
                print("[Camera] Stream lost... attempting to reconnect")
                self.stream.release()
                time.sleep(2)
                self.stream = cv2.VideoCapture(self.src)
                self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                (self.grabbed, self.frame) = self.stream.read()
                if not self.grabbed:
                    time.sleep(1)
                    continue

            (grabbed, frame) = self.stream.read()
            if grabbed:
                self.grabbed = True
                self.frame = frame
            else:
                self.grabbed = False
                time.sleep(0.1)

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()

class GestureController:
    def __init__(self, source, headless=False, target_fps=20, complexity=1):
        self.source = source
        self.headless = headless
        self.target_fps = target_fps
        self.frame_duration = 1.0 / target_fps
        
        # Load configurations
        self.load_config()
        self.load_calibration()
        
        # MediaPipe Setup
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            model_complexity=complexity,  # 0=Lite, 1=Full
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # State Machine
        self.state = "IDLE"  # IDLE, ARMED, COOLDOWN
        self.state_time = time.time()
        
        # Counters
        self.fist_frames = 0
        self.match_frames = 0
        self.matched_target = None
        
        # Track local toggle states for direct API fallback
        self.local_light_states = {k: False for k in self.config["targets"].keys()}

    def load_config(self):
        """Loads config.json or falls back to default settings."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
                print("[Config] Loaded configuration successfully.")
                return
            except Exception as e:
                print(f"[Config] Error loading config.json: {e}. Using defaults.")
        
        # Fallback Default Config
        self.config = {
            "use_home_assistant": True,
            "home_assistant_url": "http://puck-server.tailcfee0c.ts.net:8123",
            "home_assistant_token": "YOUR_LONG_LIVED_ACCESS_TOKEN_HERE",
            "direct_api_url": "http://puck-server.tailcfee0c.ts.net:5000/api/control",
            "targets": {
                "1": {"name": "Left Wall Light", "ha_entity": "switch.rf_light_1", "direct_button": "1"},
                "2": {"name": "Top Right Corner Light", "ha_entity": "switch.rf_light_2", "direct_button": "2"},
                "3": {"name": "Bottom Right Corner Light", "ha_entity": "switch.rf_light_3", "direct_button": "3"}
            },
            "similarity_threshold": 0.85,
            "fist_threshold_frames": 8,
            "pointing_threshold_frames": 8,
            "cooldown_duration": 1.5,
            "ready_timeout": 4.0
        }

    def load_calibration(self):
        """Loads calibrated target vectors from file."""
        self.calibration_data = {}
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, 'r') as f:
                    data = json.load(f)
                    # Convert list back to numpy array
                    for k, v in data.items():
                        self.calibration_data[k] = np.array(v)
                print(f"[Calibration] Loaded {len(self.calibration_data)} targets.")
            except Exception as e:
                print(f"[Calibration] Error loading calibration_data.json: {e}")
        else:
            print("[Calibration] No calibration data found. Please run with --calibrate.")

    def get_finger_status(self, landmarks):
        """
        Returns [Thumb, Index, Middle, Ring, Pinky] indicating if open.
        """
        wrist = landmarks[0]
        # Tips: Thumb(4), Index(8), Middle(12), Ring(16), Pinky(20)
        # PIPs/IP: Thumb(3), Index(6), Middle(10), Ring(14), Pinky(18)
        finger_tips = [8, 12, 16, 20]
        finger_pips = [6, 10, 14, 18]
        
        status = []
        
        # --- Thumb logic ---
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        pinky_mcp = landmarks[17]
        dist_thumb_tip = np.linalg.norm(np.array([thumb_tip.x - pinky_mcp.x, thumb_tip.y - pinky_mcp.y]))
        dist_thumb_ip = np.linalg.norm(np.array([thumb_ip.x - pinky_mcp.x, thumb_ip.y - pinky_mcp.y]))
        status.append(dist_thumb_tip > dist_thumb_ip)
        
        # --- Index, Middle, Ring, Pinky logic ---
        for tip, pip in zip(finger_tips, finger_pips):
            tip_pt = landmarks[tip]
            pip_pt = landmarks[pip]
            dist_tip = np.linalg.norm(np.array([tip_pt.x - wrist.x, tip_pt.y - wrist.y]))
            dist_pip = np.linalg.norm(np.array([pip_pt.x - wrist.x, pip_pt.y - wrist.y]))
            status.append(dist_tip > dist_pip)
            
        return status

    def get_pointing_vector(self, landmarks):
        """
        Calculates and normalizes the pointing vector from Index MCP (5) to Index Tip (8) in 3D.
        """
        mcp = landmarks[5]
        tip = landmarks[8]
        v = np.array([tip.x - mcp.x, tip.y - mcp.y, tip.z - mcp.z])
        norm = np.linalg.norm(v)
        if norm == 0:
            return v
        return v / norm

    def trigger_light(self, target_id):
        """Toggles the light matching the target_id."""
        target = self.config["targets"].get(str(target_id))
        if not target:
            return
        
        name = target["name"]
        
        def _send():
            if self.config.get("use_home_assistant", True):
                ha_url = self.config["home_assistant_url"]
                ha_token = self.config["home_assistant_token"]
                entity_id = target["ha_entity"]
                
                url = f"{ha_url}/api/services/switch/toggle"
                headers = {
                    "Authorization": f"Bearer {ha_token}",
                    "Content-Type": "application/json"
                }
                payload = {"entity_id": entity_id}
                
                try:
                    print(f"[API] Home Assistant: Toggling {name} ({entity_id})...")
                    r = requests.post(url, json=payload, headers=headers, timeout=5)
                    if r.status_code == 200:
                        print(f"[API] Successfully toggled {name} via HA REST API.")
                    else:
                        print(f"[API] HA request failed: {r.status_code} - {r.text}")
                        self._trigger_direct_fallback(target)
                except Exception as e:
                    print(f"[API] HA connection failed: {e}. Attempting direct fallback...")
                    self._trigger_direct_fallback(target)
            else:
                self._trigger_direct_fallback(target)

        threading.Thread(target=_send, daemon=True).start()

    def _trigger_direct_fallback(self, target):
        """Sends command directly to the Pi's Flask RF Bridge API."""
        button_id = target["direct_button"]
        self.local_light_states[button_id] = not self.local_light_states[button_id]
        suffix = "ON" if self.local_light_states[button_id] else "OFF"
        button_name = f"{button_id} {suffix}"
        
        url = self.config["direct_api_url"]
        payload = {"button": button_name}
        
        try:
            print(f"[Direct API] Sending {button_name} to {url}...")
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                print(f"[Direct API] Successfully sent: {button_name}")
            else:
                print(f"[Direct API] Failed: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"[Direct API] Error sending command: {e}")

    def calibrate(self):
        """Interactive visual calibration routine for spatial target pointing."""
        print("\n=== STARTING INTERACTIVE SPATIAL CALIBRATION ===")
        print("Point at the requested targets in order and press SPACEBAR to capture the vector.")
        print("Press 'q' at any time to abort calibration.")
        
        camera = ThreadedCamera(self.source).start()
        time.sleep(1.0)
        
        if not camera.grabbed:
            print("[Error] Could not connect to camera source.")
            camera.stop()
            return
            
        cv2.namedWindow("Gesture Calibration", cv2.WINDOW_NORMAL)
        
        calibrated_vectors = {}
        targets_to_calibrate = list(self.config["targets"].items())
        target_idx = 0
        
        collecting = False
        collected_vectors = []
        COLLECT_FRAMES = 25
        
        while target_idx < len(targets_to_calibrate):
            key_id, target = targets_to_calibrate[target_idx]
            name = target["name"]
            
            frame = camera.read()
            if frame is None:
                time.sleep(0.01)
                continue
                
            if isinstance(self.source, int):
                frame = cv2.flip(frame, 1)
                
            h, w, c = frame.shape
            
            # Process frame with MediaPipe
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(frame_rgb)
            
            pointing_detected = False
            curr_vector = None
            
            if results.multi_hand_landmarks:
                for hand_lms in results.multi_hand_landmarks:
                    self.mp_draw.draw_landmarks(frame, hand_lms, self.mp_hands.HAND_CONNECTIONS)
                    
                    status = self.get_finger_status(hand_lms.landmark)
                    # Check pointing: Index extended, Middle/Ring/Pinky closed
                    is_pointing = status[1] and not status[2] and not status[3] and not status[4]
                    
                    if is_pointing:
                        pointing_detected = True
                        curr_vector = self.get_pointing_vector(hand_lms.landmark)
                        
                        # Draw vector visualization lines/dots
                        index_tip = hand_lms.landmark[8]
                        cx, cy = int(index_tip.x * w), int(index_tip.y * h)
                        cv2.circle(frame, (cx, cy), 15, (0, 255, 0), -1)
                        
            # Calibration state overlay (Premium design)
            # Semi-transparent card top
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 110), (10, 10, 15), -1)
            cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
            
            cv2.putText(frame, f"CALIBRATION MODE: Step {target_idx + 1} of {len(targets_to_calibrate)}", 
                        (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (138, 43, 226), 2)
            cv2.putText(frame, f"Target: {name}", 
                        (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            
            # Action Instructions
            if not collecting:
                msg = "Point at light & press SPACEBAR to capture"
                cv2.putText(frame, msg, (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
            else:
                progress = len(collected_vectors)
                bar_w = int((progress / COLLECT_FRAMES) * 200)
                cv2.rectangle(frame, (20, 85), (220, 100), (50, 50, 50), -1)
                cv2.rectangle(frame, (20, 85), (20 + bar_w, 100), (0, 255, 0), -1)
                cv2.putText(frame, f"Capturing: {progress}/{COLLECT_FRAMES}", 
                            (230, 97), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                if pointing_detected and curr_vector is not None:
                    collected_vectors.append(curr_vector)
                    if len(collected_vectors) >= COLLECT_FRAMES:
                        # Average and store
                        avg_vec = np.mean(collected_vectors, axis=0)
                        norm_avg_vec = avg_vec / np.linalg.norm(avg_vec)
                        calibrated_vectors[key_id] = norm_avg_vec.tolist()
                        
                        print(f"✅ Target [{name}] calibrated successfully!")
                        collecting = False
                        collected_vectors = []
                        target_idx += 1
                else:
                    cv2.putText(frame, "HOLD POINT STEADY!", (w - 250, 95), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.imshow("Gesture Calibration", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                if pointing_detected and not collecting:
                    collecting = True
                    collected_vectors = []
                    print(f"Capturing vector for {name}...")
            elif key == ord('q'):
                print("❌ Calibration aborted by user.")
                break
                
        camera.stop()
        cv2.destroyAllWindows()
        
        # Save results
        if len(calibrated_vectors) == len(targets_to_calibrate):
            with open(CALIBRATION_FILE, 'w') as f:
                json.dump(calibrated_vectors, f, indent=2)
            print(f"\n🎉 Calibration successfully completed! Data saved to {CALIBRATION_FILE}\n")
        else:
            print("\n⚠️ Calibration incomplete. Data not saved.\n")

    def run(self):
        """Main detection loop using the spatial pointing algorithm."""
        if not self.calibration_data:
            print("[Warning] No calibration data found. Please run '--calibrate' first.")
            return

        print(f"[Camera] Connecting to: {self.source}")
        camera = ThreadedCamera(self.source).start()
        time.sleep(1.0)
        
        if not camera.grabbed:
            print(f"[Error] Could not open video source: {self.source}")
            camera.stop()
            return
            
        print("\n=== RUNNING SPATIAL GESTURE CONTROLLER ===")
        print("Ready. Close fist for 0.5s to ARM, then point to target to toggle.")
        print("Press Ctrl+C in terminal or 'q' in window to exit.\n")
        
        if not self.headless:
            cv2.namedWindow("Spatial Gesture Control", cv2.WINDOW_NORMAL)
            
        prev_time = time.time()
        
        try:
            while True:
                loop_start = time.time()
                
                frame = camera.read()
                if frame is None:
                    time.sleep(0.01)
                    continue
                    
                if isinstance(self.source, int):
                    frame = cv2.flip(frame, 1)
                    
                h, w, c = frame.shape
                
                # Run MediaPipe Hands
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.hands.process(frame_rgb)
                
                # Default states
                finger_count = -1
                is_fist = False
                is_pointing = False
                curr_vector = None
                
                if results.multi_hand_landmarks:
                    for hand_lms in results.multi_hand_landmarks:
                        if not self.headless:
                            self.mp_draw.draw_landmarks(frame, hand_lms, self.mp_hands.HAND_CONNECTIONS)
                            
                        status = self.get_finger_status(hand_lms.landmark)
                        
                        # Detect Fist: Index, Middle, Ring, Pinky are all closed
                        is_fist = not status[1] and not status[2] and not status[3] and not status[4]
                        
                        # Detect Pointing: Index is open, Middle/Ring/Pinky are closed
                        is_pointing = status[1] and not status[2] and not status[3] and not status[4]
                        
                        if is_pointing:
                            curr_vector = self.get_pointing_vector(hand_lms.landmark)
                            
                # --- State Machine Logic ---
                current_time = time.time()
                
                if self.state == "IDLE":
                    # Look for Fist to ARM
                    if is_fist:
                        self.fist_frames += 1
                        if self.fist_frames >= self.config["fist_threshold_frames"]:
                            self.state = "ARMED"
                            self.state_time = current_time
                            self.fist_frames = 0
                            self.match_frames = 0
                            self.matched_target = None
                            print("[State] system ARMED -> Ready for pointing command.")
                    else:
                        self.fist_frames = 0
                        
                elif self.state == "ARMED":
                    # Check timeout
                    if current_time - self.state_time > self.config["ready_timeout"]:
                        self.state = "IDLE"
                        print("[State] Armed timeout -> IDLE")
                        
                    elif is_pointing and curr_vector is not None:
                        # Find closest calibrated target using cosine similarity
                        best_target = None
                        best_sim = -1.0
                        
                        for k, ref_v in self.calibration_data.items():
                            sim = np.dot(curr_vector, ref_v)
                            if sim > best_sim:
                                best_sim = sim
                                best_target = k
                                
                        # Print similarities for debugging if pointing
                        # print(f"Pointing: closest={best_target}, similarity={best_sim:.3f}", end='\r')
                        
                        if best_sim >= self.config["similarity_threshold"]:
                            if self.matched_target == best_target:
                                self.match_frames += 1
                                if self.match_frames >= self.config["pointing_threshold_frames"]:
                                    # Trigger command!
                                    print(f"\n[ACTION] Matched target {best_target} ({self.config['targets'][best_target]['name']})! Triggering toggle...")
                                    self.trigger_light(best_target)
                                    
                                    # Transition to Cooldown
                                    self.state = "COOLDOWN"
                                    self.state_time = current_time
                            else:
                                self.matched_target = best_target
                                self.match_frames = 1
                        else:
                            self.matched_target = None
                            self.match_frames = 0
                    else:
                        self.matched_target = None
                        self.match_frames = 0
                        
                elif self.state == "COOLDOWN":
                    if current_time - self.state_time > self.config["cooldown_duration"]:
                        self.state = "IDLE"
                        print("[State] Cooldown end -> IDLE")
                        
                # --- Visual Feedback Overlay (Premium Aesthetics) ---
                if not self.headless:
                    # Glassmorphic control panel overlay
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (10, 10), (320, 190), (15, 15, 20), -1)
                    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
                    
                    # State indicators & colors
                    state_colors = {
                        "IDLE": (180, 180, 180),
                        "ARMED": (0, 255, 0),
                        "COOLDOWN": (0, 0, 255)
                    }
                    state_color = state_colors.get(self.state, (255, 255, 255))
                    
                    # Draw text details
                    cv2.putText(frame, f"SYSTEM STATE: {self.state}", (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, state_color, 2)
                    
                    # Show progress bars
                    if self.state == "IDLE":
                        progress = self.fist_frames / self.config["fist_threshold_frames"]
                        bar_w = int(progress * 150)
                        cv2.putText(frame, "Arming Fist:", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                        cv2.rectangle(frame, (130, 65), (280, 78), (40, 40, 40), -1)
                        cv2.rectangle(frame, (130, 65), (130 + bar_w, 78), (0, 200, 255), -1)
                    
                    elif self.state == "ARMED":
                        # Timeout remaining
                        rem = max(0.0, self.config["ready_timeout"] - (current_time - self.state_time))
                        cv2.putText(frame, f"Timeout: {rem:.1f}s", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                        
                        # Match progress
                        if self.matched_target:
                            t_name = self.config["targets"][self.matched_target]["name"]
                            cv2.putText(frame, f"Target: {t_name}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                            
                            progress = self.match_frames / self.config["pointing_threshold_frames"]
                            bar_w = int(progress * 150)
                            cv2.rectangle(frame, (130, 125), (280, 138), (40, 40, 40), -1)
                            cv2.rectangle(frame, (130, 125), (130 + bar_w, 138), (0, 255, 0), -1)
                        else:
                            cv2.putText(frame, "Point at a light...", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
                            
                    elif self.state == "COOLDOWN":
                        rem = max(0.0, self.config["cooldown_duration"] - (current_time - self.state_time))
                        cv2.putText(frame, f"Locked: {rem:.1f}s", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                        
                    # Calculate and display local FPS
                    fps = 1.0 / (current_time - prev_time) if current_time - prev_time > 0 else 0.0
                    prev_time = current_time
                    cv2.putText(frame, f"FPS: {int(fps)}", (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    
                    # Draw target visualizers if ARMED and pointing
                    if self.state == "ARMED" and is_pointing and curr_vector is not None:
                        for hand_lms in results.multi_hand_landmarks:
                            index_tip = hand_lms.landmark[8]
                            cx, cy = int(index_tip.x * w), int(index_tip.y * h)
                            # Draw pointer ring
                            cv2.circle(frame, (cx, cy), 18, (0, 255, 0) if self.matched_target else (0, 255, 255), 2)
                    
                    cv2.imshow("Spatial Gesture Control", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                        
                # FPS Limiter
                elapsed = time.time() - loop_start
                if elapsed < self.frame_duration:
                    time.sleep(self.frame_duration - elapsed)
                    
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            camera.stop()
            if not self.headless:
                cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spatial Pointing Hand Gesture Controller")
    parser.add_argument("--source", type=str, default="0", help="Video source (index or HTTP stream)")
    parser.add_argument("--usb", action="store_true", help="Forces video source to index 0 (USB Webcam)")
    parser.add_argument("--calibrate", action="store_true", help="Runs target calibration routine")
    parser.add_argument("--headless", action="store_true", help="Runs without OpenCV GUI window")
    parser.add_argument("--fps", type=int, default=20, help="Target FPS limit (default: 20)")
    parser.add_argument("--complexity", type=int, default=1, choices=[0, 1], help="MediaPipe Model Complexity (0=Lite, 1=Full)")
    
    args = parser.parse_args()
    
    source = args.source
    if args.usb:
        source = 0
    elif source.isdigit():
        source = int(source)
        
    controller = GestureController(source, headless=args.headless, target_fps=args.fps, complexity=args.complexity)
    
    if args.calibrate:
        controller.calibrate()
    else:
        controller.run()
