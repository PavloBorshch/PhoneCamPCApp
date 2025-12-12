import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import video_manager
import threading
import subprocess
import os
import platform
import shutil
import socket


class PhoneCamPCApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PhoneCam PC Client")

        self.expanded_geometry = "500x750"
        self.collapsed_geometry = "500x260"

        self.root.geometry(self.expanded_geometry)
        self.root.resizable(False, False)

        self.video_handler = video_manager.VideoStreamHandler()

        self.is_connected = False
        self.is_connecting_process = False
        self.show_preview = True

        self.last_usb_port = None

        # Шлях до ADB
        self.adb_path = self._find_adb()
        print(f"ADB Path detected: {self.adb_path}")

        self.connection_id = 0

        self._setup_ui()
        self.root.after(33, self._update_gui_loop)

    def _find_adb(self):
        if shutil.which("adb"):
            return "adb"

        system = platform.system()
        possible_paths = []
        user_home = os.path.expanduser("~")

        if system == "Windows":
            possible_paths = [
                os.path.join(user_home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
                os.path.join("C:", "Android", "platform-tools", "adb.exe"),
                "C:\\Program Files (x86)\\Android\\android-sdk\\platform-tools\\adb.exe"
            ]
        elif system == "Darwin":
            possible_paths = [
                os.path.join(user_home, "Library", "Android", "sdk", "platform-tools", "adb"),
                "/opt/homebrew/bin/adb"
            ]
        else:
            possible_paths = [
                os.path.join(user_home, "Android", "Sdk", "platform-tools", "adb"),
                "/usr/bin/adb"
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return f'"{path}"'

        return None

    def _get_free_port(self, start_port=8554):
        port = start_port
        while port < 65535:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    port += 1
        return start_port

    def _setup_ui(self):
        conn_frame = ttk.LabelFrame(self.root, text="Налаштування з'єднання", padding=10)
        conn_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(conn_frame, text="Підключення:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.protocol_var = tk.StringVar(value="Мережа")
        self.proto_combo = ttk.Combobox(conn_frame, textvariable=self.protocol_var,
                                        values=["Мережа", "USB"], state="readonly", width=10)
        self.proto_combo.grid(row=0, column=1, padx=5, pady=5)
        self.proto_combo.bind("<<ComboboxSelected>>", self._on_protocol_change)

        ttk.Label(conn_frame, text="IP Телефону:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.ip_entry = ttk.Entry(conn_frame, width=20)
        self.ip_entry.insert(0, "192.168.0.105")
        self.ip_entry.grid(row=1, column=1, padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="Під'єднатись", command=self.toggle_connection)
        self.connect_btn.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")

        adb_status_text = "ADB знайдено" if self.adb_path else "ADB не знайдено (USB не працюватиме)"
        adb_color = "green" if self.adb_path else "red"
        self.adb_label = tk.Label(conn_frame, text=adb_status_text, fg=adb_color, font=("Arial", 8))
        self.adb_label.grid(row=3, column=0, columnspan=2)

        self.preview_frame_container = ttk.LabelFrame(self.root, text="Попередній перегляд", padding=5)
        self.preview_frame_container.pack(fill="both", expand=True, padx=10, pady=5)

        self.preview_toggle_btn = ttk.Button(self.preview_frame_container, text="Приховати перегляд",
                                             command=self.toggle_preview_visibility)
        self.preview_toggle_btn.pack(anchor="ne")

        self.preview_label = tk.Label(self.preview_frame_container, text="Немає з'єднання", bg="black", fg="white")
        self.preview_label.pack(fill="both", expand=True, pady=5)

        self.status_var = tk.StringVar(value="Готовий до роботи")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(side="bottom", fill="x")

    def _on_protocol_change(self, event):
        proto = self.protocol_var.get()
        if proto == "USB":
            self.ip_entry.config(state="disabled")
        else:
            self.ip_entry.config(state="normal")

    def toggle_connection(self):
        if self.is_connected:
            self._disconnect()
            return

        if self.is_connecting_process:
            self.status_var.set("Скасовано користувачем")
            self.connection_id += 1
            self._disconnect()
            return

        ip = self.ip_entry.get()
        proto = self.protocol_var.get()

        if not ip and proto == "Мережа":
            messagebox.showerror("Помилка", "Введіть IP адресу")
            return

        self.status_var.set(f"Підключення до {proto}...")
        self.is_connecting_process = True
        self.connection_id += 1
        current_attempt_id = self.connection_id

        self.connect_btn.config(text="Скасувати", state="normal")
        self.ip_entry.config(state="disabled")
        self.proto_combo.config(state="disabled")

        threading.Thread(target=self._perform_connection, args=(proto, ip, current_attempt_id), daemon=True).start()

    def _perform_connection(self, proto, ip, attempt_id):
        actual_ip_or_port = ip

        if proto == "USB":
            if not self.adb_path:
                print("ADB path not found.")
                self.root.after(0, lambda: messagebox.showerror("Помилка ADB", "ADB не знайдено."))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

            try:
                free_port = self._get_free_port(8554)
                print(f"Found free local port: {free_port}")

                cmd = f"{self.adb_path} forward tcp:{free_port} tcp:8554"
                print(f"Executing: {cmd}")

                subprocess.run(cmd, check=True, shell=True, capture_output=True, text=True)
                print("ADB forward set successfully")

                self.last_usb_port = free_port
                actual_ip_or_port = str(free_port)

            except subprocess.CalledProcessError as e:
                err_msg = e.stderr.strip() if e.stderr else str(e)
                print(f"ADB forward failed: {err_msg}")
                self.root.after(0, lambda: messagebox.showerror("Помилка ADB", f"ADB Error: {err_msg}"))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return
            except Exception as e:
                print(f"Connection setup failed: {e}")
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

        success = self.video_handler.start(proto, actual_ip_or_port)
        self.root.after(0, self._on_connection_completed, success, attempt_id)

    def _on_connection_completed(self, success, attempt_id):
        if attempt_id != self.connection_id:
            return

        self.is_connecting_process = False

        if success:
            self.is_connected = True
            self.connect_btn.config(text="Від'єднатись")
            self.status_var.set("Трансляція активна / Очікування...")
        else:
            self.is_connected = False
            self.connect_btn.config(text="Під'єднатись")
            self.proto_combo.config(state="normal")
            if self.protocol_var.get() != "USB":
                self.ip_entry.config(state="normal")

            if self.video_handler.connect_aborted:
                self.status_var.set("Підключення перервано")
            else:
                self.status_var.set("Помилка підключення")

    def _disconnect(self):
        self.video_handler.stop()
        self.is_connected = False
        self.is_connecting_process = False

        self.connect_btn.config(text="Під'єднатись")
        self.proto_combo.config(state="normal")
        if self.protocol_var.get() != "USB":
            self.ip_entry.config(state="normal")

        self.preview_label.config(image="", text="Немає з'єднання", bg="black")
        self.status_var.set("Відключено")

        if self.protocol_var.get() == "USB" and self.adb_path and self.last_usb_port:
            try:
                subprocess.run(f"{self.adb_path} forward --remove tcp:{self.last_usb_port}", shell=True)
                self.last_usb_port = None
            except:
                pass

    def toggle_preview_visibility(self):
        self.show_preview = not self.show_preview
        if self.show_preview:
            self.preview_toggle_btn.config(text="Приховати перегляд")
            self.preview_label.pack(fill="both", expand=True, pady=5)
            self.root.geometry(self.expanded_geometry)
        else:
            self.preview_toggle_btn.config(text="Показати перегляд")
            self.preview_label.pack_forget()
            self.root.geometry(self.collapsed_geometry)

    def _update_gui_loop(self):
        if self.is_connected and self.show_preview:
            frame = self.video_handler.get_latest_frame()
            if frame is not None:
                self._display_frame(frame)
            else:
                # Оновлено: відображення тексту при відсутності кадрів (але активному з'єднанні)
                self.preview_label.config(image="",
                                          text="Очікування трансляції...\n(Перевірте, чи запущено стрім на телефоні)",
                                          bg="black", fg="white")
                self.preview_label.image = None

        self.root.after(33, self._update_gui_loop)

    def _display_frame(self, rgb_image):
        try:
            display_w = 460
            display_h = 460

            img = Image.fromarray(rgb_image)
            img_w, img_h = img.size

            ratio = min(display_w / img_w, display_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)

            img_resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(image=img_resized)

            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo
        except Exception as e:
            print(f"Preview error: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PhoneCamPCApp(root)
    root.mainloop()