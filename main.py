import sys
import os
import time
import cv2
import threading
import json
import numpy as np
import socket
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from arduino.app_utils import *

# ==============================================================================
# 0. GROUND TRUTH NETWORK DIAGNOSTICS
# ==============================================================================
print("\n=== SYSTEM NETWORK DIAGNOSTICS ===")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Hostname: {socket.gethostname()}")
try:
    hostname = socket.gethostname()
    ip_list = socket.gethostbyname_ex(hostname)[2]
    print(f"Visible IP Interfaces: {ip_list}")
except Exception as e:
    print(f"Could not resolve IP interfaces: {e}")

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    print(f"Primary Outbound IP Layer: {s.getsockname()[0]}")
    s.close()
except Exception as e:
    print(f"Outbound network path isolated: {e}")
print("==================================\n")

# ==============================================================================
# 1. CORE HARDWARE & BUFFER SETUP
# ==============================================================================
blank_frame = np.zeros((240, 320, 3), dtype=np.uint8)
_, encoded_blank = cv2.imencode(".jpg", blank_frame)
latest_jpeg = encoded_blank.tobytes()

latest_overlay = "System Initializing..."
frame_lock = threading.Lock()
servo_angle = 90  
is_moving = 0     

print("CHECKPOINT 2: Activating webcam via native V4L2 pipeline...")
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
time.sleep(1)

# ==============================================================================
# 2. DATA ACQUISITION & THREADING LAYERS
# ==============================================================================
def camera_loop():
    global latest_jpeg
    while True:
        success, frame = camera.read()
        if not success:
            time.sleep(0.5)
            continue
        with frame_lock:
            cv2.putText(frame, latest_overlay, (85, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            success, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            if success:
                latest_jpeg = jpeg.tobytes()
        time.sleep(0.03)

def dht_loop():
    global latest_overlay
    while True:
        try:
            temperature = float(Bridge.call("temperature", ""))
            humidity = float(Bridge.call("humidity", ""))
            latest_overlay = f"Temp: {temperature:.1f}C  Hum: {humidity:.1f}%"
        except Exception:
            latest_overlay = f"Pos: {servo_angle} deg"
        time.sleep(2)

def servo_processing_loop():
    global servo_angle, is_moving
    while True:
        if is_moving == -1 and servo_angle > 0: servo_angle -= 4  
        elif is_moving == 1 and servo_angle < 180: servo_angle += 4
        servo_angle = max(0, min(180, servo_angle))
        try: 
            Bridge.call("set_angle", str(servo_angle))
        except Exception: 
            pass
        time.sleep(0.05) 

print("CHECKPOINT 3: Spinning up localized telemetry systems...")
threading.Thread(target=camera_loop, daemon=True).start()
threading.Thread(target=dht_loop, daemon=True).start()
threading.Thread(target=servo_processing_loop, daemon=True).start()

# ==============================================================================
# 3. EXPLICIT WEB INTERFACE LAYOUT
# ==============================================================================
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rover Control Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        * { box-sizing: border-box; user-select: none; -webkit-user-select: none; }
        body { margin: 0; background: #0e1114; color: #e1e7ed; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; overflow: hidden; }
        .wrapper { display: flex; flex-direction: column; align-items: center; width: 90%; max-width: 500px; gap: 15px; margin-top: 15px; }
        h2 { margin: 5px 0; font-size: 20px; text-transform: uppercase; letter-spacing: 1px; color: #ff8800; }
        .video-box { width: 100%; aspect-ratio: 4/3; background: #000; border-radius: 12px; overflow: hidden; border: 2px solid #2c3540; }
        #cam { width: 100%; height: 100%; object-fit: cover; }
        .control-pad { display: flex; width: 100%; gap: 15px; margin-top: 10px; }
        .control-btn { flex: 1; height: 80px; background: #ff8800; border: none; border-radius: 14px; font-size: 24px; font-weight: bold; color: #12161a; }
        .control-btn:active { background: #cc6c00; transform: scale(0.98); }
        .angle-txt { font-size: 16px; color: #8892b0; font-weight: bold; }
    </style>
</head>
<body>
    <div class="wrapper">
        <h2>Rover Mission Control</h2>
        <div class="angle-txt">Angle: <span id="deg">90</span>&deg;</div>
        <div class="video-box"><img id="cam" src="/frame.jpg"></div>
        <div class="control-pad">
            <button class="control-btn" ontouchstart="move(-1)" ontouchend="move(0)" onmousedown="move(-1)" onmouseup="move(0)">⬅️ LEFT</button>
            <button class="control-btn" ontouchstart="move(1)" ontouchend="move(0)" onmousedown="move(1)" onmouseup="move(0)">RIGHT ➡️</button>
        </div>
    </div>
    <script>
        function refreshImage() { document.getElementById("cam").src = "/frame.jpg?t=" + new Date().getTime(); }
        setInterval(refreshImage, 100);
        function move(dir) { fetch("/move?dir=" + dir); }
        function updateTelemetry() { fetch("/angle").then(res => res.json()).then(data => { document.getElementById("deg").innerText = data.angle; }); }
        setInterval(updateTelemetry, 200);
    </script>
</body>
</html>
"""

class RoverRouter(BaseHTTPRequestHandler):
    def log_message(self, format, *args): 
        return  

    def do_GET(self):
        global is_moving
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/" or path == "" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(INDEX_HTML)))
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
            return

        elif path == "/frame.jpg":
            with frame_lock: 
                frame_bytes = latest_jpeg
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame_bytes)))
            self.end_headers()
            self.wfile.write(frame_bytes)
            return

        elif path == "/move":
            query_params = parse_qs(parsed_url.query)
            try: 
                is_moving = int(query_params.get("dir", [0])[0])
            except: 
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        elif path == "/angle":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response_data = json.dumps({"angle": servo_angle})
            self.wfile.write(response_data.encode("utf-8"))
            return

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

# ==============================================================================
# 4. EXPLICIT NETWORK BINDING
# ==============================================================================
if __name__ == "__main__":
    server_address = ("0.0.0.0", 7000)
    print("CHECKPOINT 4: Binding web socket explicitly to port 7000...")
    rover_server = ThreadingHTTPServer(server_address, RoverRouter)
    print("SUCCESS: Web Server is locked open on port 7000!")
    rover_server.serve_forever()
