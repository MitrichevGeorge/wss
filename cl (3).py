# cl.py
# pip install mss opencv-python websockets numpy asyncio

import asyncio
import base64
import cv2
import numpy as np
import mss
import websockets
import time

# ================== НАСТРОЙКИ ==================
ID = "CLIENT_001"                     # <- уникальный id
SERVER_WS = "ws://77.232.128.127:8080/client_ws/" + ID
FPS = 8                               # базовая частота кадров
INIT_QUALITY = 60                     # начальное качество
WIDTH = 1280                          # ширина (автомасштаб)
ADAPTIVITY = True                     # включить адаптивное качество
# ===============================================

paused = False
pause_event = asyncio.Event()
pause_event.set()

async def capture_loop(ws):
    global paused
    prev_gray = None
    jpeg_quality = INIT_QUALITY
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            if not pause_event.is_set():
                await pause_event.wait()

            start = time.time()
            img = np.array(sct.grab(monitor))
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            h, w = img.shape[:2]
            new_h = int(h * (WIDTH / w))
            frame = cv2.resize(img, (WIDTH, new_h))

            # === адаптивное качество ===
            if ADAPTIVITY:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    # вычисляем среднюю разницу пикселей
                    diff = cv2.absdiff(gray, prev_gray)
                    mean_diff = diff.mean()

                    # чем больше разница — тем ниже качество (для скорости)
                    if mean_diff > 15:
                        jpeg_quality = max(10, jpeg_quality - 80)
                    elif mean_diff < 2:
                        jpeg_quality = min(100, jpeg_quality + 10)

                    # сгладим резкие скачки
                    jpeg_quality = int(jpeg_quality)
                prev_gray = gray

            # === кодирование и отправка ===
            ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if not ret:
                await asyncio.sleep(1.0 / FPS)
                continue
            b64 = base64.b64encode(buf).decode('ascii')

            try:
                await ws.send(b64)
            except Exception as e:
                print("send error:", e)
                raise

            elapsed = time.time() - start
            await asyncio.sleep(max(0, 1.0 / FPS - elapsed))

async def ws_handler():
    global paused
    backoff = 1
    while True:
        try:
            async with websockets.connect(SERVER_WS, max_size=2**24) as ws:
                print("connected to server ws")
                consumer_task = asyncio.create_task(capture_loop(ws))
                try:
                    async for msg in ws:
                        if msg == "pause":
                            paused = True
                            pause_event.clear()
                            print("paused by server")
                        elif msg == "resume":
                            paused = False
                            pause_event.set()
                            print("resumed by server")
                except websockets.ConnectionClosed:
                    print("connection closed")
                finally:
                    consumer_task.cancel()
        except Exception as e:
            print("connection failed:", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

def main():
    asyncio.run(ws_handler())

if __name__ == "__main__":
    main()
