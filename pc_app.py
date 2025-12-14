import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
import subprocess

# Імпортуємо наші модулі
from adb_utils import AdbManager
from video_manager import VideoStreamHandler
from audio_manager import AudioManager


class PhoneCamPCApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PhoneCam PC Client")

        self.root.geometry("800x500")
        self.root.resizable(True, True)
        self.root.configure(bg="#f0f0f0")

        # Ініціалізація менеджерів
        self.adb = AdbManager()
        self.video_handler = VideoStreamHandler()
        self.audio_handler = AudioManager()

        self.is_connected = False
        self.is_connecting_process = False

        self.last_usb_port_video = None
        self.last_usb_port_audio = None
        self.connection_id = 0

        self.protocol_var = tk.StringVar(value="Мережа")

        self._setup_ui()
        self._update_protocol_visuals()
        self.root.after(33, self._update_gui_loop)

    def _setup_ui(self):
        # --- Ліва панель ---
        self.left_panel = tk.Frame(self.root, width=250, bg="#f0f0f0", padx=20, pady=20)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y)
        self.left_panel.pack_propagate(False)

        self.mode_frame = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.mode_frame.pack(fill=tk.X, pady=(0, 20))

        self.btn_network = tk.Button(self.mode_frame, text="мережа", font=("Arial", 12),
                                     command=lambda: self._set_protocol("Мережа"), relief=tk.FLAT, bd=0)
        self.btn_network.pack(fill=tk.X, pady=5)

        self.btn_usb = tk.Button(self.mode_frame, text="USB", font=("Arial", 12),
                                 command=lambda: self._set_protocol("USB"), relief=tk.FLAT, bd=0)
        self.btn_usb.pack(fill=tk.X, pady=5)

        self.ip_section = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.ip_section.pack(fill=tk.X, pady=10)

        self.lbl_ip = tk.Label(self.ip_section, text="IP телефону:", font=("Arial", 12), bg="#f0f0f0", anchor="w")
        self.lbl_ip.pack(fill=tk.X)

        self.ip_entry = tk.Entry(self.ip_section, font=("Arial", 12), bg="#e0e0e0", bd=1, relief=tk.SOLID)
        self.ip_entry.insert(0, "192.168.0.105")
        self.ip_entry.pack(fill=tk.X, pady=5, ipady=3)

        self.spacer = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.spacer.pack(fill=tk.BOTH, expand=True)

        self.adb_label = tk.Label(self.left_panel, text="", font=("Arial", 8), bg="#f0f0f0")
        self.adb_label.pack(fill=tk.X, pady=(0, 5))
        self._check_adb_status()

        self.connect_btn = tk.Button(self.left_panel, text="Під'єднатись", font=("Arial", 12),
                                     bg="#b0b0c0", fg="black", command=self.toggle_connection, relief=tk.RAISED)
        self.connect_btn.pack(fill=tk.X, pady=10, ipady=5)

        # --- Права панель ---
        self.right_panel = tk.Frame(self.root, bg="#101010")
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.preview_label = tk.Label(self.right_panel, text="попередній\nперегляд\nкамери",
                                      font=("Arial", 20), fg="white", bg="#101010")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _check_adb_status(self):
        adb_found = self.adb.is_available()
        if adb_found:
            self.adb_label.config(text="ADB знайдено", fg="green")
        else:
            self.adb_label.config(text="ADB не знайдено", fg="red")

    def _set_protocol(self, protocol):
        if self.is_connected or self.is_connecting_process: return
        self.protocol_var.set(protocol)
        self._update_protocol_visuals()

    def _update_protocol_visuals(self):
        protocol = self.protocol_var.get()
        active_bg, active_fg = "#3333cc", "white"
        inactive_bg, inactive_fg = "#b0b0c0", "black"

        if protocol == "Мережа":
            self.btn_network.config(bg=active_bg, fg=active_fg)
            self.btn_usb.config(bg=inactive_bg, fg=inactive_fg)
            self.ip_section.pack(fill=tk.X, pady=10, after=self.mode_frame)
        else:
            self.btn_usb.config(bg=active_bg, fg=active_fg)
            self.btn_network.config(bg=inactive_bg, fg=inactive_fg)
            self.ip_section.pack_forget()

    def toggle_connection(self):
        if self.is_connected:
            self._disconnect()
            return

        if self.is_connecting_process:
            self.connection_id += 1
            self._disconnect()
            return

        ip = self.ip_entry.get()
        proto = self.protocol_var.get()

        if proto == "Мережа" and not ip:
            messagebox.showerror("Помилка", "Введіть IP адресу")
            return

        self.connect_btn.config(text="Скасувати", bg="#ffcccc")
        self.btn_network.config(state="disabled")
        self.btn_usb.config(state="disabled")
        self.ip_entry.config(state="disabled")

        self.is_connecting_process = True
        self.connection_id += 1
        current_attempt_id = self.connection_id

        threading.Thread(target=self._perform_connection, args=(proto, ip, current_attempt_id), daemon=True).start()

    def _perform_connection(self, proto, ip, attempt_id):
        target_host = ip
        target_port_video = 8554
        target_port_audio = 8555

        if proto == "USB":
            if not self.adb.is_available():
                self.root.after(0, lambda: messagebox.showerror("Помилка ADB", "ADB не знайдено."))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

            try:
                # 0. Обираємо конкретний девайс (щоб уникнути "more than one device")
                device = self.adb.select_device()
                if not device:
                    raise Exception("Не знайдено підключених USB пристроїв.")

                # 1. Знаходимо вільні порти
                free_port_video = self.adb.get_free_port(8554)
                free_port_audio = self.adb.get_free_port(free_port_video + 1)

                print(f"Mapping ports: {free_port_video}->8554, {free_port_audio}->8555 on device {device}")

                # 2. Прокидаємо порти
                self.adb.start_forwarding(free_port_video, 8554)
                self.adb.start_forwarding(free_port_audio, 8555)

                self.last_usb_port_video = free_port_video
                self.last_usb_port_audio = free_port_audio

                target_host = "127.0.0.1"
                target_port_video = free_port_video
                target_port_audio = free_port_audio

            except Exception as e:
                err_msg = str(e)
                print(f"Connection setup failed: {err_msg}")
                self.root.after(0, lambda: messagebox.showerror("Помилка USB",
                                                                f"{err_msg}\n\nПорада: Спробуйте відключити Емулятор, якщо він працює."))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

        self.video_handler.start(target_host, target_port_video)
        self.audio_handler.start(target_host, target_port_audio)

        self.root.after(0, self._on_connection_completed, True, attempt_id)

    def _on_connection_completed(self, success, attempt_id):
        if attempt_id != self.connection_id: return
        self.is_connecting_process = False

        if success:
            self.is_connected = True
            self.connect_btn.config(text="Від'єднатись", bg="#ff6666", fg="white")
            self.preview_label.config(text="Очікування трансляції...\n(Перевірте телефон)")
        else:
            self._disconnect()

    def _disconnect(self):
        self.video_handler.stop()
        self.audio_handler.stop()

        self.is_connected = False
        self.is_connecting_process = False

        self.connect_btn.config(text="Під'єднатись", bg="#b0b0c0", fg="black")
        self.btn_network.config(state="normal")
        self.btn_usb.config(state="normal")
        self.ip_entry.config(state="normal")
        self.preview_label.config(image="", text="попередній\nперегляд\nкамери", bg="#101010")

        if self.protocol_var.get() == "USB":
            if self.last_usb_port_video:
                self.adb.remove_forwarding(self.last_usb_port_video)
            if self.last_usb_port_audio:
                self.adb.remove_forwarding(self.last_usb_port_audio)
            self.last_usb_port_video = None
            self.last_usb_port_audio = None

    def toggle_preview_visibility(self):
        pass

    def _update_gui_loop(self):
        if self.is_connected:
            frame = self.video_handler.get_latest_frame()
            if frame is not None:
                self._display_frame(frame)
            else:
                if self.preview_label.cget("text") == "":
                    self.preview_label.config(image="", text="Очікування...", bg="#101010", fg="white")

        self.root.after(33, self._update_gui_loop)

    def _display_frame(self, rgb_image):
        try:
            panel_w = self.right_panel.winfo_width()
            panel_h = self.right_panel.winfo_height()
            if panel_w < 10 or panel_h < 10: return

            img = Image.fromarray(rgb_image)
            img_w, img_h = img.size
            ratio = min(panel_w / img_w, panel_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)

            img_resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(image=img_resized)

            self.preview_label.config(image=photo, text="", bg="black")
            self.preview_label.image = photo
        except Exception as e:
            print(f"Preview error: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PhoneCamPCApp(root)
    root.mainloop()
