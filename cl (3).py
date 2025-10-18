# cl.py
# Screen capture and streaming client for ROSA MOS Linux (using venv, no admin privileges)
import asyncio
import base64
import cv2
import numpy as np
import time
try:
    import mss
except ImportError:
    print("Error: 'mss' library not found. Activate your venv and install it with: pip install mss")
    exit(1)
try:
    import websockets
except ImportError:
    print("Error: 'websockets' library not found. Activate your venv and install it with: pip install websockets")
    exit(1)

# ================== SETTINGS ==================
ID = "CLIENT_001"  # Unique client ID
SERVER_WS = "ws://77.232.128.127:8080/client_ws/" + ID
FPS = 8  # Base frame rate
INIT_QUALITY = 60  # Initial JPEG quality
WIDTH = 1280  # Output width (auto-scaled)
ADAPTIVITY = True  # Enable adaptive quality
# =============================================

paused = False
pause_event = asyncio.Event()
pause_event.set()

async def capture_loop(ws):
    global paused
    prev_gray = None
    jpeg_quality = INIT_QUALITY
    try:
        with mss.mss() as sct:
            try:
                monitor = sct.monitors[1]  # Primary monitor
            except IndexError:
                print("Error: No monitor detected. Ensure a display is available.")
                return
            while True:
                if not pause_event.is_set():
                    await pause_event.wait()
                start = time.time()
                try:
                    img = np.array(sct.grab(monitor))
                except Exception as e:
                    print(f"Screen capture error: {e}. Ensure you have permission to capture the screen.")
                    await asyncio.sleep(1.0)
                    continue
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                h, w = img.shape[:2]
                new_h = int(h * (WIDTH / w))
                frame = cv2.resize(img, (WIDTH, new_h))
                # === Adaptive quality ===
                if ADAPTIVITY:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if prev_gray is not None:
                        diff = cv2.absdiff(gray, prev_gray)
                        mean_diff = diff.mean()
                        # Adjust quality based on frame difference
                        if mean_diff > 15:
                            jpeg_quality = max(10, jpeg_quality - 8)
                        elif mean_diff < 2:
                            jpeg_quality = min(100, jpeg_quality + 10)
                        jpeg_quality = int(jpeg_quality)
                    prev_gray = gray
                # === Encode and send ===
                ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                if not ret:
                    print("Error: Failed to encode frame.")
                    await asyncio.sleep(1.0 / FPS)
                    continue
                b64 = base64.b64encode(buf).decode('ascii')
                try:
                    await ws.send(b64)
                except Exception as e:
                    print(f"Send error: {e}")
                    raise
                elapsed = time.time() - start
                await asyncio.sleep(max(0, 1.0 / FPS - elapsed))
    except Exception as e:
        print(f"Capture loop error: {e}")

async def ws_handler():
    global paused
    backoff = 1
    while True:
        try:
            async with websockets.connect(SERVER_WS, max_size=2**24) as ws:
                print("Connected to server WebSocket")
                consumer_task = asyncio.create_task(capture_loop(ws))
                try:
                    async for msg in ws:
                        if msg == "pause":
                            paused = True
                            pause_event.clear()
                            print("Paused by server")
                        elif msg == "resume":
                            paused = False
                            pause_event.set()
                            print("Resumed by server")
                except websockets.ConnectionClosed:
                    print("WebSocket connection closed")
                finally:
                    consumer_task.cancel()
        except Exception as e:
            print(f"Connection failed: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

def main():
    # Check for OpenCV installation
    if cv2.__version__ is None:
        print("Error: OpenCV not found. Activate your venv and install it with: pip install opencv-python")
        exit(1)
    try:
        asyncio.run(ws_handler())
    except KeyboardInterrupt:
        print("Script terminated by user")
    except Exception as e:
        print(f"Main error: {e}")

if __name__ == "__main__":
    print("Starting screen capture client on ROSA MOS Linux (using venv)...")
    print("Ensure your virtual environment is activated and dependencies are installed with:")
    print("pip install mss opencv-python websockets numpy")
    main()
