import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
import subprocess

# Імпортуємо наші модулі
from adb_utils import AdbManager
from video_manager import VideoStreamHandler


class PhoneCamPCApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PhoneCam PC Client")

        # Змінюємо розмір вікна на більш широкий для горизонтального компонування
        self.root.geometry("800x500")
        self.root.resizable(True, True)
        self.root.configure(bg="#f0f0f0")

        # Ініціалізація менеджерів
        self.adb = AdbManager()
        self.video_handler = VideoStreamHandler()

        self.is_connected = False
        self.is_connecting_process = False

        self.last_usb_port = None
        self.connection_id = 0

        # Змінна для збереження поточного протоколу
        self.protocol_var = tk.StringVar(value="Мережа")

        self._setup_ui()
        self._update_protocol_visuals()  # Початковий стан
        self.root.after(33, self._update_gui_loop)

    def _setup_ui(self):
        # --- Ліва панель (Керування) ---
        self.left_panel = tk.Frame(self.root, width=250, bg="#f0f0f0", padx=20, pady=20)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y)
        self.left_panel.pack_propagate(False)  # Фіксуємо ширину

        # Кнопки вибору режиму
        self.mode_frame = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.mode_frame.pack(fill=tk.X, pady=(0, 20))

        # Використовуємо tk.Button для можливості зміни кольору фону
        self.btn_network = tk.Button(
            self.mode_frame,
            text="мережа",
            font=("Arial", 12),
            command=lambda: self._set_protocol("Мережа"),
            relief=tk.FLAT,
            bd=0
        )
        self.btn_network.pack(fill=tk.X, pady=5)

        self.btn_usb = tk.Button(
            self.mode_frame,
            text="USB",
            font=("Arial", 12),
            command=lambda: self._set_protocol("USB"),
            relief=tk.FLAT,
            bd=0
        )
        self.btn_usb.pack(fill=tk.X, pady=5)

        # Секція IP адреси (контейнер для легкого приховування)
        self.ip_section = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.ip_section.pack(fill=tk.X, pady=10)

        self.lbl_ip = tk.Label(
            self.ip_section,
            text="IP телефону:",
            font=("Arial", 12),
            bg="#f0f0f0",
            anchor="w"
        )
        self.lbl_ip.pack(fill=tk.X)

        self.ip_entry = tk.Entry(self.ip_section, font=("Arial", 12), bg="#e0e0e0", bd=1, relief=tk.SOLID)
        self.ip_entry.insert(0, "192.168.0.105")
        self.ip_entry.pack(fill=tk.X, pady=5, ipady=3)

        # Пустий простір, щоб кнопка "Під'єднатись" була знизу
        self.spacer = tk.Frame(self.left_panel, bg="#f0f0f0")
        self.spacer.pack(fill=tk.BOTH, expand=True)

        # Статус ADB (маленький текст над кнопкою)
        self.adb_label = tk.Label(self.left_panel, text="", font=("Arial", 8), bg="#f0f0f0")
        self.adb_label.pack(fill=tk.X, pady=(0, 5))
        self._check_adb_status()

        # Кнопка підключення
        self.connect_btn = tk.Button(
            self.left_panel,
            text="Під'єднатись",
            font=("Arial", 12),
            bg="#b0b0c0",  # Світло-фіолетовий відтінок
            fg="black",
            command=self.toggle_connection,
            relief=tk.RAISED
        )
        self.connect_btn.pack(fill=tk.X, pady=10, ipady=5)

        # --- Права панель (Прев'ю) ---
        self.right_panel = tk.Frame(self.root, bg="#101010")
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.preview_label = tk.Label(
            self.right_panel,
            text="попередній\nперегляд\nкамери",
            font=("Arial", 20),
            fg="white",
            bg="#101010"
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        # Статус бар (внизу вікна, поверх панелей, або просто внизу лівої)
        # В даному дизайні статус бар не передбачено явно,
        # але ми можемо змінювати текст кнопки або виводити помилки messagebox-ом.

    def _check_adb_status(self):
        adb_found = self.adb.is_available()
        if adb_found:
            self.adb_label.config(text="ADB знайдено", fg="green")
        else:
            self.adb_label.config(text="ADB не знайдено", fg="red")

    def _set_protocol(self, protocol):
        if self.is_connected or self.is_connecting_process:
            return  # Не дозволяємо змінювати під час з'єднання

        self.protocol_var.set(protocol)
        self._update_protocol_visuals()

    def _update_protocol_visuals(self):
        protocol = self.protocol_var.get()

        # Кольори кнопок (активна - синя, неактивна - сіра)
        active_bg = "#3333cc"  # Темно-синій
        active_fg = "white"
        inactive_bg = "#b0b0c0"  # Сірий
        inactive_fg = "black"

        if protocol == "Мережа":
            self.btn_network.config(bg=active_bg, fg=active_fg)
            self.btn_usb.config(bg=inactive_bg, fg=inactive_fg)
            # Показуємо поле IP
            self.ip_section.pack(fill=tk.X, pady=10, after=self.mode_frame)
        else:
            self.btn_usb.config(bg=active_bg, fg=active_fg)
            self.btn_network.config(bg=inactive_bg, fg=inactive_fg)
            # Ховаємо поле IP
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

        # Зміна UI на стан "Підключення..."
        self.connect_btn.config(text="Скасувати", bg="#ffcccc")
        self.btn_network.config(state="disabled")
        self.btn_usb.config(state="disabled")
        self.ip_entry.config(state="disabled")

        self.is_connecting_process = True
        self.connection_id += 1
        current_attempt_id = self.connection_id

        # Запускаємо процес підключення в окремому потоці
        threading.Thread(target=self._perform_connection, args=(proto, ip, current_attempt_id), daemon=True).start()

    def _perform_connection(self, proto, ip, attempt_id):
        target_host = ip
        target_port = 8554

        if proto == "USB":
            if not self.adb.is_available():
                self.root.after(0, lambda: messagebox.showerror("Помилка ADB", "ADB не знайдено."))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

            try:
                free_port = self.adb.get_free_port(8554)
                print(f"Found free local port: {free_port}")

                self.adb.start_forwarding(free_port, 8554)
                print("ADB forward set successfully")

                self.last_usb_port = free_port
                target_host = "127.0.0.1"
                target_port = free_port

            except Exception as e:
                print(f"Connection setup failed: {e}")
                self.root.after(0, lambda: messagebox.showerror("Помилка", f"Помилка USB: {e}"))
                self.root.after(0, self._on_connection_completed, False, attempt_id)
                return

        # Запускаємо відео менеджер
        self.video_handler.start(target_host, target_port)

        # Вважаємо ініціацію успішною
        self.root.after(0, self._on_connection_completed, True, attempt_id)

    def _on_connection_completed(self, success, attempt_id):
        if attempt_id != self.connection_id:
            return

        self.is_connecting_process = False

        if success:
            self.is_connected = True
            self.connect_btn.config(text="Від'єднатись", bg="#ff6666", fg="white")  # Червона кнопка для розриву
            self.preview_label.config(text="Очікування трансляції...\n(Перевірте телефон)")
        else:
            self._disconnect()  # Скидаємо UI до початкового стану

    def _disconnect(self):
        self.video_handler.stop()
        self.is_connected = False
        self.is_connecting_process = False

        # Скидання UI
        self.connect_btn.config(text="Під'єднатись", bg="#b0b0c0", fg="black")
        self.btn_network.config(state="normal")
        self.btn_usb.config(state="normal")
        self.ip_entry.config(state="normal")

        self.preview_label.config(image="", text="попередній\nперегляд\nкамери", bg="#101010")

        # Очистка ADB forward
        if self.protocol_var.get() == "USB" and self.last_usb_port:
            self.adb.remove_forwarding(self.last_usb_port)
            self.last_usb_port = None

    def toggle_preview_visibility(self):
        # У новому дизайні кнопка приховання прев'ю не передбачена на макеті,
        # але функціонал можна залишити або прибрати.
        # Тут я його прибираю для відповідності макету.
        pass

    def _update_gui_loop(self):
        if self.is_connected:
            frame = self.video_handler.get_latest_frame()
            if frame is not None:
                self._display_frame(frame)
            else:
                # Якщо з'єднання активне, але кадрів немає
                if self.preview_label.cget("text") == "":
                    self.preview_label.config(image="", text="Очікування...", bg="#101010", fg="white")

        self.root.after(33, self._update_gui_loop)

    def _display_frame(self, rgb_image):
        try:
            # Отримуємо розміри правої панелі для адаптивного ресайзу
            panel_w = self.right_panel.winfo_width()
            panel_h = self.right_panel.winfo_height()

            if panel_w < 10 or panel_h < 10: return  # Ще не відмалювалось

            img = Image.fromarray(rgb_image)
            img_w, img_h = img.size

            # Зберігаємо пропорції (Fit Center)
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