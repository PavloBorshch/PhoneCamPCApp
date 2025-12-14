import shutil
import platform
import os
import subprocess
import socket


class AdbManager:
    def __init__(self):
        self.adb_path = self._find_adb()
        self.current_device_serial = None

    def is_available(self):
        return self.adb_path is not None

    def _find_adb(self):
        """Автоматичний пошук ADB у системі."""
        if shutil.which("adb"):
            return "adb"

        system = platform.system()
        user_home = os.path.expanduser("~")
        possible_paths = []

        if system == "Windows":
            possible_paths = [
                os.path.join(user_home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
                os.path.join("C:", "Android", "platform-tools", "adb.exe"),
                "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools\\adb.exe"
            ]
        elif system == "Darwin":  # MacOS
            possible_paths = [
                os.path.join(user_home, "Library", "Android", "sdk", "platform-tools", "adb"),
                "/opt/homebrew/bin/adb"
            ]
        else:  # Linux
            possible_paths = [
                os.path.join(user_home, "Android", "Sdk", "platform-tools", "adb"),
                "/usr/bin/adb"
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return f'"{path}"'

        return None

    def get_devices(self):
        """Повертає список підключених пристроїв (serial, type)."""
        if not self.adb_path: return []

        try:
            cmd = f"{self.adb_path} devices"
            result = subprocess.run(cmd, check=True, shell=True, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            devices = []
            # Перший рядок - заголовок "List of devices attached", пропускаємо
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    if state == 'device':
                        devices.append(serial)
            return devices
        except Exception as e:
            print(f"[ADB] Error getting devices: {e}")
            return []

    def select_device(self):
        """Обирає найкращий пристрій (пріоритет - фізичний, не емулятор)."""
        devices = self.get_devices()
        if not devices:
            return None

        if len(devices) == 1:
            self.current_device_serial = devices[0]
            return devices[0]

        # Якщо декілька, шукаємо той, що не емулятор (не починається на emulator-)
        for d in devices:
            if not d.startswith("emulator-"):
                self.current_device_serial = d
                print(f"[ADB] Multiple devices found. Auto-selected physical device: {d}")
                return d

        # Якщо всі емулятори, беремо перший
        self.current_device_serial = devices[0]
        return devices[0]

    def get_free_port(self, start_port=8554):
        """Знаходить вільний локальний порт."""
        port = start_port
        while port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    port += 1
        return start_port

    def start_forwarding(self, local_port, remote_port):
        """Виконує adb forward для вибраного пристрою."""
        if not self.adb_path:
            raise Exception("ADB not found")

        # Переконуємось, що пристрій вибрано
        if not self.current_device_serial:
            device = self.select_device()
            if not device:
                raise Exception("No Android device connected via USB")

        # Спочатку намагаємось очистити цей порт
        self.remove_forwarding(local_port)

        # Додаємо -s SERIAL, щоб вказати конкретний телефон
        cmd = f"{self.adb_path} -s {self.current_device_serial} forward tcp:{local_port} tcp:{remote_port}"
        print(f"[ADB] Executing: {cmd}")

        result = subprocess.run(cmd, check=True, shell=True, capture_output=True, text=True)
        return result

    def remove_forwarding(self, local_port):
        """Очищає прокидання порту."""
        if not self.adb_path: return
        try:
            # Видаляємо правило для конкретного пристрою, якщо він відомий
            target = f"-s {self.current_device_serial}" if self.current_device_serial else ""
            cmd = f"{self.adb_path} {target} forward --remove tcp:{local_port}"
            subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)
            print(f"[ADB] Forward removed for port {local_port}")
        except Exception:
            pass
