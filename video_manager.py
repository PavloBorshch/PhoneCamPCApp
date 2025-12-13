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
        if self.virtual_cam is not None: return  # Вже створено

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
        """Головний цикл обробки."""
        self._setup_virtual_cam()

        # Створюємо клієнт протоколу
        client = StreamClient(self.target_host, self.target_port)

        while self.running:
            # 1. Забезпечення з'єднання
            if not client.is_connected:
                connected = client.connect()
                if not connected:
                    time.sleep(1.0)  # Чекаємо перед повторною спробою
                    continue

            # 2. Отримання та обробка даних
            try:
                # Отримуємо сирі дані через протокол
                jpeg_data, rotation = client.receive_packet()

                # Декодуємо картинку
                nparr = np.frombuffer(jpeg_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Обробка повороту
                    frame = self._rotate_image(frame, rotation)

                    # Відправка у віртуальну камеру та оновлення прев'ю
                    self._process_frame_output(frame)

            except TimeoutError:
                # Просто немає даних певний час, нічого страшного, чекаємо далі
                pass
            except (ConnectionResetError, ValueError) as e:
                print(f"[VideoMgr] Stream error: {e}")
                client.close()
                # Очищаємо кадр, щоб показати "Немає сигналу"
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
            # Виправлення для повороту вліво (Counter-Clockwise)
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _process_frame_output(self, frame):
        # 1. Віртуальна камера
        if self.virtual_cam:
            try:
                # Ресайз до цільового розміру віртуальної камери
                resized = cv2.resize(frame, (self.target_width, self.target_height))
                self.virtual_cam.send(resized)
                self.virtual_cam.sleep_until_next_frame()
            except Exception:
                pass

        # 2. Прев'ю для GUI (BGR -> RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with self.lock:
            self.current_frame = rgb_frame