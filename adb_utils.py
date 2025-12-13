import shutil
import platform
import os
import subprocess
import socket


class AdbManager:
    def __init__(self):
        self.adb_path = self._find_adb()

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
                # Для Windows шляхи з пробілами краще брати в лапки,
                # але subprocess.run(shell=True) краще розуміє raw string.
                return f'"{path}"'

        return None

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
        """Виконує adb forward."""
        if not self.adb_path:
            raise Exception("ADB not found")

        # Спочатку намагаємось очистити цей порт, про всяк випадок
        self.remove_forwarding(local_port)

        cmd = f"{self.adb_path} forward tcp:{local_port} tcp:{remote_port}"
        print(f"[ADB] Executing: {cmd}")

        # capture_output=True дозволяє перехопити текст помилки
        result = subprocess.run(cmd, check=True, shell=True, capture_output=True, text=True)
        return result

    def remove_forwarding(self, local_port):
        """Очищає прокидання порту."""
        if not self.adb_path: return
        try:
            cmd = f"{self.adb_path} forward --remove tcp:{local_port}"
            subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)
            print(f"[ADB] Forward removed for port {local_port}")
        except Exception:
            pass
