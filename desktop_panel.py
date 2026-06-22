import os
import sys
import queue
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from contextlib import redirect_stdout, redirect_stderr

APP_TITLE = "AutoBotPanel Launcher"
BASE_URL = "http://localhost:5000"
APP_USER_MODEL_ID = "AutoBotPanel.Launcher.1"

NAV_ITEMS = [
    ("📱 Dashboard & Quản lý Pages", "/admin/pages"),
    ("🎯 Quản lý Chuyên môn", "/admin/skills"),
    ("Dữ liệu chuyên môn", "/admin/skill-data"),
    ("💬 Thống kê Tin nhắn", "/admin/message-stats"),
    ("🌐 API Logs", "/admin/api-logs"),
    ("⚙️ Cấu hình", "/admin/settings"),
]


def app_base_dir() -> str:
    """Folder chứa exe khi đóng gói, hoặc folder source khi chạy python."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    """Lấy path đúng cho file được add-data khi chạy PyInstaller onefile.

    - Khi chạy source: lấy theo folder source.
    - Khi chạy exe onefile: ưu tiên sys._MEIPASS, nơi PyInstaller giải nén templates/static.
    - Nếu muốn thay icon ngoài exe, vẫn fallback về folder cạnh exe.
    """
    relative_path = relative_path.replace("/", os.sep).replace("\\", os.sep)

    if getattr(sys, "frozen", False):
        mei_base = getattr(sys, "_MEIPASS", None)
        if mei_base:
            bundled = os.path.join(mei_base, relative_path)
            if os.path.exists(bundled):
                return bundled
        return os.path.join(app_base_dir(), relative_path)

    return os.path.join(app_base_dir(), relative_path)


def set_windows_app_id():
    """Giúp Windows nhận đúng icon app trên taskbar/titlebar."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


class TkTextWriter:
    """Ghi stdout/stderr vào queue để Tkinter hiển thị an toàn từ thread khác.

    Một số thư viện như click/colorama đôi lúc ghi bytes thay vì str trên Windows.
    Vì vậy writer phải chấp nhận cả str và bytes để tránh lỗi:
    TypeError: can only concatenate str (not "bytes") to str
    """

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, log_queue: queue.Queue, prefix: str = ""):
        self.log_queue = log_queue
        self.prefix = prefix

    def write(self, text) -> int:
        if text is None:
            return 0

        original_len = len(text) if hasattr(text, "__len__") else 0

        if isinstance(text, bytes):
            text = text.decode(self.encoding, errors=self.errors)
        else:
            text = str(text)

        if text:
            self.log_queue.put(self.prefix + text)
        return original_len

    def flush(self):
        pass

    def isatty(self):
        return False


class LauncherUI:
    def __init__(self):
        set_windows_app_id()

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1100x680")
        self.root.minsize(900, 560)
        self.root.configure(bg="#0c0f14")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.server_thread = None

        self._set_icon()
        self._build_ui()
        self._start_server_thread()
        self._poll_logs()

    def _set_icon(self):
        icon_path = resource_path(os.path.join("templates", "logo.ico"))

        if not os.path.exists(icon_path):
            # Log sau khi UI tạo xong thì chưa có log_box, nên ghi queue trước.
            self.log_queue.put(f"[UI] Không tìm thấy icon: {icon_path}\n")
            return

        try:
            # Titlebar icon cho Tkinter trên Windows.
            self.root.iconbitmap(default=icon_path)
            self.log_queue.put(f"[UI] Đã nạp icon: {icon_path}\n")
        except Exception as e:
            self.log_queue.put(f"[UI] Không set được icon Tkinter: {e}\n")

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#0c0f14")
        header.pack(fill="x", padx=14, pady=(14, 8))

        title = tk.Label(
            header,
            text="AutoBotPanel CMD Launcher",
            bg="#0c0f14",
            fg="#d7e5ff",
            font=("Consolas", 16, "bold"),
        )
        title.pack(side="left")

        self.status_var = tk.StringVar(value="SERVER: STARTING")
        status = tk.Label(
            header,
            textvariable=self.status_var,
            bg="#111827",
            fg="#facc15",
            padx=12,
            pady=6,
            font=("Consolas", 10, "bold"),
        )
        status.pack(side="right")

        nav = tk.Frame(self.root, bg="#111827", highlightbackground="#283447", highlightthickness=1)
        nav.pack(fill="x", padx=14, pady=(0, 10))

        for label, path in NAV_ITEMS:
            btn = tk.Button(
                nav,
                text=label,
                command=lambda p=path: self.open_url(p),
                bg="#172033",
                fg="#d7e5ff",
                activebackground="#2b36a8",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=14,
                pady=12,
                cursor="hand2",
                font=("Consolas", 10, "bold"),
            )
            btn.pack(side="left", padx=(0, 2), fill="y")

        body = tk.Frame(self.root, bg="#0c0f14")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        log_title = tk.Label(
            body,
            text="CMD LOG OUTPUT",
            bg="#0c0f14",
            fg="#22c55e",
            anchor="w",
            font=("Consolas", 11, "bold"),
        )
        log_title.pack(fill="x", pady=(0, 4))

        self.log_box = ScrolledText(
            body,
            bg="#020617",
            fg="#22c55e",
            insertbackground="#22c55e",
            selectbackground="#1e40af",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 10),
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.insert("end", "[UI] Đang khởi động Flask server...\n")
        self.log_box.configure(state="disabled")

        bottom = tk.Frame(self.root, bg="#0c0f14")
        bottom.pack(fill="x", padx=14, pady=(0, 14))

        tk.Button(
            bottom,
            text="Mở Dashboard",
            command=lambda: self.open_url("/admin/pages"),
            bg="#2b36a8",
            fg="#ffffff",
            activebackground="#3b48d6",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            font=("Consolas", 10, "bold"),
        ).pack(side="left")

        tk.Button(
            bottom,
            text="Xóa log hiển thị",
            command=self.clear_logs,
            bg="#1f2937",
            fg="#d7e5ff",
            activebackground="#374151",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            font=("Consolas", 10, "bold"),
        ).pack(side="left", padx=(8, 0))

    def open_url(self, path: str):
        url = BASE_URL + path
        self._append_log(f"\n[UI] Open: {url}\n")
        webbrowser.open(url)

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _append_log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_logs(self):
        try:
            while True:
                text = self.log_queue.get_nowait()
                self._append_log(text)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_logs)

    def _start_server_thread(self):
        self.server_thread = threading.Thread(target=self._run_flask_server, daemon=True)
        self.server_thread.start()

    def _run_flask_server(self):
        writer = TkTextWriter(self.log_queue)
        with redirect_stdout(writer), redirect_stderr(writer):
            try:
                os.chdir(app_base_dir())
                print("[SERVER] Import app.py...")

                # Tắt banner CLI của Flask trước khi app.run để tránh click/colorama ghi bytes.
                try:
                    import flask.cli
                    flask.cli.show_server_banner = lambda *args, **kwargs: None
                except Exception:
                    pass

                from app import app

                try:
                    from utils.config_service import get_runtime_bool, get_runtime_int
                    port = get_runtime_int("PORT", 5000)
                    debug_mode = get_runtime_bool("FLASK_DEBUG", False)
                except Exception:
                    port = 5000
                    debug_mode = False

                self.root.after(0, lambda: self.status_var.set(f"SERVER: RUNNING :{port}"))
                print(f"[SERVER] Running: http://localhost:{port}")
                print("[SERVER] Dùng các nút phía trên để mở lại trang web khi lỡ đóng browser.")

                app.run(
                    host="127.0.0.1",
                    port=port,
                    debug=debug_mode,
                    use_reloader=False,
                )
            except Exception:
                self.root.after(0, lambda: self.status_var.set("SERVER: ERROR"))
                print("\n[SERVER ERROR]")
                print(traceback.format_exc())

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    LauncherUI().run()
