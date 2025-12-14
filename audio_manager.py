import socket
import threading
import time

try:
    import pyaudio
except ImportError:
    pyaudio = None


class AudioManager:
    def __init__(self):
        self.running = False
        self.thread = None
        self.socket = None

        # Налаштування аудіо (16 bit, Mono, 44100 Hz)
        self.sample_rate = 44100
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16 if pyaudio else None

        self.pa = None
        self.stream = None

        self.target_host = "127.0.0.1"
        self.target_port = 8555

    def start(self, host, port):
        if self.running: return

        # Якщо бібліотеки немає взагалі - ми навіть не намагаємось
        if pyaudio is None:
            print("[AudioMgr] Skipping audio start (no lib).")
            return

        self.target_host = host
        self.target_port = int(port)
        self.running = True

        print(f"[AudioMgr] Starting thread for {self.target_host}:{self.target_port}")
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self._close_audio_stream()
        print("[AudioMgr] Stopped")

    def _init_audio_stream(self):
        if not self.running: return

        try:
            self.pa = pyaudio.PyAudio()

            output_device_index = None
            found_cable = False

            # Пошук пристрою "CABLE Input"
            info = self.pa.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')

            for i in range(0, numdevices):
                dev_info = self.pa.get_device_info_by_host_api_device_index(0, i)
                dev_name = dev_info.get('name')
                max_out = dev_info.get('maxOutputChannels')

                if max_out > 0 and "CABLE Input" in dev_name:
                    output_device_index = i
                    print(f"[AudioMgr] Found VB-Cable Virtual Audio Device: '{dev_name}' (Index: {i})")
                    found_cable = True
                    break

            if not found_cable:
                print("[AudioMgr] VB-Cable NOT found. Audio playback will be DISABLED.")
                # Ми НЕ відкриваємо потік, щоб не грати звук у колонки
                self.stream = None
                return

            # Відкриваємо потік тільки якщо знайшли кабель
            self.stream = self.pa.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                output_device_index=output_device_index,
                frames_per_buffer=self.chunk_size
            )
            print("[AudioMgr] Audio stream opened successfully.")

        except Exception as e:
            print(f"[AudioMgr] Init failed: {e}")
            self._close_audio_stream()

    def _close_audio_stream(self):
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        if self.pa:
            try:
                self.pa.terminate()
            except:
                pass
        self.stream = None
        self.pa = None

    def _worker_loop(self):
        # Ініціалізація
        self._init_audio_stream()

        while self.running:
            # Підключення до телефону
            if self.socket is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    sock.connect((self.target_host, self.target_port))
                    self.socket = sock
                    print(f"[AudioMgr] Connected to phone audio port {self.target_port}")
                except Exception:
                    time.sleep(1.0)
                    continue

            # Читання даних
            try:
                # Читаємо порцію даних
                # *2 тому що 16-бітний звук це 2 байти на семпл
                data = self.socket.recv(self.chunk_size * 2)

                if not data:
                    raise ConnectionResetError("No data")

                #мЯкщо потік відкритий, Cable знайдено - граємо.
                # Якщо ні -дропаємо, але продовжуємо читати, щоб буфер TCP не переповнився і додаток не завис.
                if self.stream:
                    self.stream.write(data)

            except Exception as e:
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                self.socket = None
                time.sleep(0.5)

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self._close_audio_stream()