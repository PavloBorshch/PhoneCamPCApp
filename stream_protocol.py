import socket
import struct
import time


class StreamClient:
    """
    Відповідає за низькорівневе TCP з'єднання та розбір протоколу.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.is_connected = False

    def connect(self, timeout=2.0):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((self.host, self.port))

            # Збільшуємо таймаут для читання даних, щоб не розривати при лагах мережі
            self.socket.settimeout(3.0)
            self.is_connected = True
            print(f"[Protocol] Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            self.close()
            return False

    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.is_connected = False

    def receive_packet(self):
        """
        Читає один повний пакет даних.
        Повертає tuple: (image_bytes, rotation_degrees)
        """
        if not self.socket:
            raise ConnectionError("No socket")

        try:
            # Читаємо заголовок, розмір кадру
            size_data = self._recv_all(4)
            if not size_data:
                raise ConnectionResetError("Connection lost (no header)")

            size = struct.unpack('>I', size_data)[0]

            # Перевірка на End Of Stream або некоректні дані
            if size == 0:
                raise ConnectionResetError("EOS received")
            if size > 20_000_000:  # Ліміт 20МБ на кадр
                raise ValueError(f"Frame too large: {size}")

            # Читаємо кут повороту
            rot_data = self._recv_all(4)
            if not rot_data:
                raise ConnectionResetError("Connection lost (no rotation)")

            # Читаємо як знакове ціле (>i) для підтримки від'ємних значень
            raw_rotation = struct.unpack('>i', rot_data)[0]
            # Нормалізація кута
            rotation = raw_rotation % 360

            # Читаємо тіло
            image_data = self._recv_all(size)
            if not image_data:
                raise ConnectionResetError("Connection lost (incomplete body)")

            return image_data, rotation

        except socket.timeout:
            raise TimeoutError("Socket timeout")
        except Exception as e:
            self.close()
            raise e

    def _recv_all(self, n):
        """Читає рівно n байт з сокета."""
        data = b''
        while len(data) < n:
            try:
                packet = self.socket.recv(n - len(data))
                if not packet:
                    return None
                data += packet
            except socket.timeout:
                raise  # Прокидаємо таймаут вище
            except Exception:
                return None
        return data
