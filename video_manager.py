import cv2
import threading
import time

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
        self.cap = None
        self.virtual_cam = None
        self.current_frame = None
        self.lock = threading.Lock()

        # Прапорець для відстеження скасування під час спроби підключення
        self.connect_aborted = False

        self.target_width = 1920
        self.target_height = 1080
        self.fps = 30

    def start(self, protocol, ip_address):
        # Якщо вже працює - ігноруємо
        if self.running:
            return True

        # Скидаємо прапорець скасування перед новим підключенням
        self.connect_aborted = False

        url = ""
        # Обробка нових спрощених назв протоколів
        if protocol == "Мережа":
            # Використовуємо RTSP як стандартний мережевий протокол
            url = f"rtsp://{ip_address}:554/live"
        elif protocol == "USB":
            url = "rtsp://127.0.0.1:8554/live"

        # Залишаємо сумісність на випадок прямого виклику
        elif protocol == "RTSP":
            url = f"rtsp://{ip_address}:554/live"
        elif protocol == "HTTP":
            url = f"http://{ip_address}:8080/video"
        elif protocol == "MJPEG":
            url = f"http://{ip_address}:8080/mjpeg"

        print(f"Connecting to: {url}")

        try:
            # Це блокуюча операція. Не можливо перервати ззовні
            cap = cv2.VideoCapture(url)

            # Перевіряємо, чи не натиснув користувач "Скасувати"
            if self.connect_aborted:
                print("Connection aborted by user during attempt.")
                cap.release()
                return False

            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                print("Failed to open stream immediately.")
                return False

            # Якщо все добре і не скасовано - зберігаємо об'єкт
            self.cap = cap

        except Exception as e:
            print(f"Exception opening stream: {e}")
            return False

        # Запускаємо потік обробки тільки якщо не було скасування
        self.running = True
        self.thread = threading.Thread(target=self._process_stream, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        # Встановлюємо прапорець скасування
        self.connect_aborted = True

        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        if self.cap:
            self.cap.release()
            self.cap = None

        if self.virtual_cam:
            self.virtual_cam.close()
            self.virtual_cam = None

        with self.lock:
            self.current_frame = None

        print("Stream stopped")

    def get_latest_frame(self):
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None

    def _process_stream(self):
        if pyvirtualcam is None:
            print("Virtual Camera library not available.")
            return

        try:
            # Використовуємо pyvirtualcam.PixelFormat.BGR напряму
            self.virtual_cam = pyvirtualcam.Camera(
                width=self.target_width,
                height=self.target_height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.BGR
            )
            print(f"Virtual camera started: {self.virtual_cam.device}")
        except Exception as e:
            print(f"Virtual Camera Error (OBS installed?): {e}")
            self.virtual_cam = None

        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()

                if not ret:
                    time.sleep(0.1)
                    continue

                if self.virtual_cam:
                    try:
                        resized = cv2.resize(frame, (self.target_width, self.target_height))
                        self.virtual_cam.send(resized)
                        self.virtual_cam.sleep_until_next_frame()
                    except Exception as e:
                        print(f"Error sending to virtual cam: {e}")

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                with self.lock:
                    self.current_frame = rgb_frame
            else:
                time.sleep(0.5)