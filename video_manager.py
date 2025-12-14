import cv2
import threading
import time
import numpy as np
from stream_protocol import StreamClient

# Спробуємо імпортувати pyvirtualcam безпечно
try:
    import pyvirtualcam
except ImportError:
    pyvirtualcam = None
    print("Error: pyvirtualcam not installed. Run 'pip install pyvirtualcam'")


class VideoStreamHandler:
    def __init__(self):
        self.running = False
        self.thread = None
        self.virtual_cam = None
        self.current_frame = None
        self.lock = threading.Lock()

        self.target_width = 1920
        self.target_height = 1080
        self.fps = 30

        # Налаштування підключення
        self.target_host = "127.0.0.1"
        self.target_port = 8554

    def start(self, host, port):
        if self.running:
            return

        self.target_host = host
        self.target_port = int(port)
        self.running = True

        print(f"[VideoMgr] Starting thread for {self.target_host}:{self.target_port}")
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        self._close_virtual_cam()

        with self.lock:
            self.current_frame = None
        print("[VideoMgr] Stopped")

    def get_latest_frame(self):
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None

    def _setup_virtual_cam(self):
        if pyvirtualcam is None: return
        if self.virtual_cam is not None: return

        try:
            self.virtual_cam = pyvirtualcam.Camera(
                width=self.target_width,
                height=self.target_height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.BGR
            )
            print(f"[VirtualCam] Started: {self.virtual_cam.device}")
        except Exception as e:
            print(f"[VirtualCam] Error: {e}")

    def _close_virtual_cam(self):
        if self.virtual_cam:
            self.virtual_cam.close()
            self.virtual_cam = None

    def _worker_loop(self):
        self._setup_virtual_cam()
        client = StreamClient(self.target_host, self.target_port)

        while self.running:
            if not client.is_connected:
                connected = client.connect()
                if not connected:
                    time.sleep(1.0)
                    continue

            try:
                jpeg_data, rotation = client.receive_packet()
                nparr = np.frombuffer(jpeg_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # 1. Поворот зображення
                    frame = self._rotate_image(frame, rotation)

                    # 2. Відправка у віртуальну камеру (з збереженням пропорцій)
                    # Створюємо чорний фон (canvas) розміром з віртуальну камеру
                    canvas = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)

                    # Вписуємо зображення в canvas
                    resized_frame = self._resize_contain(frame, self.target_width, self.target_height)

                    # Центруємо зображення на фоні
                    h_small, w_small = resized_frame.shape[:2]
                    y_offset = (self.target_height - h_small) // 2
                    x_offset = (self.target_width - w_small) // 2

                    canvas[y_offset:y_offset + h_small, x_offset:x_offset + w_small] = resized_frame

                    # Відправка у віртуальну камеру
                    if self.virtual_cam:
                        self.virtual_cam.send(canvas)
                        self.virtual_cam.sleep_until_next_frame()

                    # Оновлення прев'ю для GUI (використовуємо той самий кадр, але в RGB)
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Для прев'ю краще оригінал без смуг
                    with self.lock:
                        self.current_frame = rgb_frame

            except TimeoutError:
                pass
            except (ConnectionResetError, ValueError) as e:
                print(f"[VideoMgr] Stream error: {e}")
                client.close()
                with self.lock:
                    self.current_frame = None
                time.sleep(0.5)
            except Exception as e:
                print(f"[VideoMgr] Unexpected error: {e}")
                client.close()
                time.sleep(1.0)

        client.close()
        self._close_virtual_cam()

    def _rotate_image(self, frame, rotation):
        if rotation == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _resize_contain(self, image, target_w, target_h):
        """Змінює розмір зображення, зберігаючи пропорції, щоб воно вмістилось у цільові розміри."""
        h, w = image.shape[:2]

        # Розрахунок масштабу
        scale = min(target_w / w, target_h / h)

        new_w = int(w * scale)
        new_h = int(h * scale)

        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)