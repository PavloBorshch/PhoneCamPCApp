import cv2
import threading
import time
import socket
import struct
import numpy as np

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

        # Для TCP (USB) режиму
        self.tcp_socket = None

        # Прапорець для відстеження скасування під час спроби підключення
        self.connect_aborted = False

        self.target_width = 1920
        self.target_height = 1080
        self.fps = 30
        self.tcp_port = 8554

    def start(self, protocol, ip_address):
        if self.running:
            return True

        self.connect_aborted = False
        self.running = True

        if protocol == "USB":
            if ip_address and ip_address.isdigit():
                self.tcp_port = int(ip_address)
            else:
                self.tcp_port = 8554

            print(f"Starting USB mode on localhost:{self.tcp_port}")
            self.thread = threading.Thread(target=self._process_stream_usb_tcp, daemon=True)
            self.thread.start()
            return True
        else:
            url = f"rtsp://{ip_address}:554/live"
            print(f"Connecting to RTSP: {url}")

            try:
                cap = cv2.VideoCapture(url)
                if self.connect_aborted:
                    cap.release()
                    return False
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    return False
                self.cap = cap
            except Exception as e:
                print(f"RTSP Error: {e}")
                return False

            self.thread = threading.Thread(target=self._process_stream_rtsp, daemon=True)
            self.thread.start()
            return True

    def stop(self):
        self.connect_aborted = True
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        if self.cap:
            self.cap.release()
            self.cap = None

        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None

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

    def _setup_virtual_cam(self):
        if pyvirtualcam is None: return
        try:
            self.virtual_cam = pyvirtualcam.Camera(
                width=self.target_width,
                height=self.target_height,
                fps=self.fps,
                fmt=pyvirtualcam.PixelFormat.BGR
            )
        except Exception as e:
            print(f"Virtual Camera Error: {e}")

    def _process_stream_rtsp(self):
        self._setup_virtual_cam()
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue
                self._handle_frame(frame)
            else:
                time.sleep(0.5)

    def _process_stream_usb_tcp(self):
        self._setup_virtual_cam()
        print(f"TCP Loop Started on port {self.tcp_port}. Waiting for connection...")

        # Нескінченний цикл спроб підключення (поки працює додаток)
        while self.running:
            # 1. Етап підключення
            if self.tcp_socket is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)  # Тайм-аут на підключення
                    sock.connect(('127.0.0.1', self.tcp_port))

                    self.tcp_socket = sock
                    self.tcp_socket.settimeout(3.0)  # Тайм-аут на читання даних
                    print("TCP Socket Connected! Receiving stream...")
                except Exception:
                    # Якщо підключення немає, чекаємо і пробуємо знову
                    time.sleep(1.0)
                    continue

            # 2. Етап читання даних
            try:
                # Читаємо розмір
                size_data = self._recv_all(4)
                if not size_data:
                    raise ConnectionResetError("No header")

                size = struct.unpack('>I', size_data)[0]

                # Обробка EOS (0 size) або помилкових даних
                if size == 0:
                    print("Received EOS (Stream Ended by Phone)")
                    # Скидаємо з'єднання, щоб чекати нового
                    raise ConnectionResetError("EOS")

                if size > 10_000_000:
                    print(f"Invalid frame size: {size}. Resetting.")
                    raise ValueError("Invalid size")

                # Читаємо кут
                rot_data = self._recv_all(4)
                if not rot_data:
                    raise ConnectionResetError("No rotation data")

                # Читаємо як знакове ціле і нормалізуємо
                raw_rotation = struct.unpack('>i', rot_data)[0]
                rotation = raw_rotation % 360

                # Читаємо картинку
                img_data = self._recv_all(size)
                if not img_data:
                    raise ConnectionResetError("No image body")

                nparr = np.frombuffer(img_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Логіка повороту
                    if rotation == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif rotation == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif rotation == 270:
                        # ВИПРАВЛЕНО: Використовуємо COUNTERCLOCKWISE для 270 (поворот вліво)
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                    self._handle_frame(frame)

            except (socket.timeout, ConnectionResetError, ValueError, OSError):
                # Закриваємо поточний сокет
                if self.tcp_socket:
                    try:
                        self.tcp_socket.close()
                    except:
                        pass
                    self.tcp_socket = None

                # Очищуємо кадр, щоб UI показав "Немає з'єднання"
                with self.lock:
                    self.current_frame = None

                time.sleep(0.5)  # Пауза перед наступною спробою

        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        print("TCP Loop finished")

    def _recv_all(self, n):
        data = b''
        while len(data) < n:
            try:
                packet = self.tcp_socket.recv(n - len(data))
                if not packet: return None
                data += packet
            except socket.timeout:
                raise
            except:
                return None
        return data

    def _handle_frame(self, frame):
        if self.virtual_cam:
            try:
                resized = cv2.resize(frame, (self.target_width, self.target_height))
                self.virtual_cam.send(resized)
                self.virtual_cam.sleep_until_next_frame()
            except Exception as e:
                pass

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with self.lock:
            self.current_frame = rgb_frame