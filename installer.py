"""
AutoBotPanel - Installer tự động.

Chức năng:
- Tải release zip mới nhất từ GitHub về.
- Giải nén vào thư mục người dùng chỉ định.
- Tạo shortcut trên Desktop / Start Menu.
- Tùy chọn khởi chạy app sau khi cài xong.

Chỉ dùng thư viện chuẩn (tkinter, urllib, zipfile, subprocess).
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import updater

APP_TITLE = "AutoBotPanel Installer"
DEFAULT_INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AutoBotPanel")


class InstallerUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("760x560")
        self.root.minsize(680, 500)
        self.root.configure(bg="#0c0f14")

        self.msg_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.create_desktop_shortcut = tk.BooleanVar(value=True)
        self.create_start_menu_shortcut = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)

        self._build_ui()
        self._poll_queue()
        self._load_release_info()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        header = tk.Frame(self.root, bg="#0c0f14")
        header.pack(fill="x", padx=16, pady=(16, 6))
        tk.Label(
            header,
            text="AutoBotPanel Installer",
            bg="#0c0f14",
            fg="#d7e5ff",
            font=("Consolas", 16, "bold"),
        ).pack(side="left")
        self.release_var = tk.StringVar(value="Đang kiểm tra bản mới nhất...")
        tk.Label(
            header,
            textvariable=self.release_var,
            bg="#111827",
            fg="#facc15",
            padx=10,
            pady=4,
            font=("Consolas", 10),
        ).pack(side="right")

        body = tk.Frame(self.root, bg="#0c0f14")
        body.pack(fill="both", expand=True, padx=16, pady=8)

        # Install dir
        dir_frame = tk.Frame(body, bg="#0c0f14")
        dir_frame.pack(fill="x", pady=(0, 10))
        tk.Label(
            dir_frame,
            text="Thư mục cài đặt:",
            bg="#0c0f14",
            fg="#d7e5ff",
            font=("Consolas", 10, "bold"),
        ).pack(anchor="w")
        row = tk.Frame(dir_frame, bg="#0c0f14")
        row.pack(fill="x", pady=(4, 0))
        tk.Entry(
            row,
            textvariable=self.install_dir,
            bg="#111827",
            fg="#d7e5ff",
            insertbackground="#d7e5ff",
            relief="flat",
            font=("Consolas", 10),
        ).pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(
            row,
            text="Chọn...",
            command=self._choose_dir,
            bg="#1f2937",
            fg="#d7e5ff",
            activebackground="#374151",
            relief="flat",
            cursor="hand2",
            padx=12,
            font=("Consolas", 10),
        ).pack(side="left", padx=(8, 0))

        # Options
        opts = tk.Frame(body, bg="#0c0f14")
        opts.pack(fill="x", pady=(0, 10))
        tk.Checkbutton(
            opts,
            text="Tạo shortcut trên Desktop",
            variable=self.create_desktop_shortcut,
            bg="#0c0f14",
            fg="#d7e5ff",
            selectcolor="#111827",
            activebackground="#0c0f14",
            activeforeground="#d7e5ff",
            font=("Consolas", 10),
        ).pack(anchor="w")
        tk.Checkbutton(
            opts,
            text="Tạo shortcut trong Start Menu",
            variable=self.create_start_menu_shortcut,
            bg="#0c0f14",
            fg="#d7e5ff",
            selectcolor="#111827",
            activebackground="#0c0f14",
            activeforeground="#d7e5ff",
            font=("Consolas", 10),
        ).pack(anchor="w")
        tk.Checkbutton(
            opts,
            text="Khởi chạy AutoBotPanel sau khi cài xong",
            variable=self.launch_after,
            bg="#0c0f14",
            fg="#d7e5ff",
            selectcolor="#111827",
            activebackground="#0c0f14",
            activeforeground="#d7e5ff",
            font=("Consolas", 10),
        ).pack(anchor="w")

        # Log
        self.log_box = ScrolledText(
            body,
            bg="#020617",
            fg="#22c55e",
            insertbackground="#22c55e",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 10),
            wrap="word",
            height=12,
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.insert("end", "[i] Sẵn sàng.\n")
        self.log_box.configure(state="disabled")

        # Progress
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(10, 0))

        # Buttons
        btns = tk.Frame(self.root, bg="#0c0f14")
        btns.pack(fill="x", padx=16, pady=(0, 14))
        self.install_btn = tk.Button(
            btns,
            text="⬇️ Cài đặt",
            command=self._start_install,
            bg="#2b36a8",
            fg="#ffffff",
            activebackground="#3b48d6",
            activeforeground="#ffffff",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            font=("Consolas", 11, "bold"),
        )
        self.install_btn.pack(side="left")
        tk.Button(
            btns,
            text="Thoát",
            command=self.root.destroy,
            bg="#1f2937",
            fg="#d7e5ff",
            activebackground="#374151",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            font=("Consolas", 10),
        ).pack(side="right")

    def _choose_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir.get() or os.path.expanduser("~"))
        if chosen:
            self.install_dir.set(chosen)

    def _append_log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.install_btn.configure(state="disabled" if busy else "normal")

    # ------------------------------------------------------------- helpers
    def _load_release_info(self):
        def work():
            release = updater.get_latest_release()
            if release:
                tag = release.get("tag_name") or release.get("name") or "latest"
                self.root.after(0, lambda: self.release_var.set(f"Bản mới nhất: {tag}"))
            else:
                self.root.after(0, lambda: self.release_var.set("Không kết nối được GitHub"))
        threading.Thread(target=work, daemon=True).start()

    def _log(self, msg):
        self.msg_queue.put(msg)

    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=max(0, min(100, value))))

    # ------------------------------------------------------------- install
    def _start_install(self):
        if self.busy:
            return
        install_dir = self.install_dir.get().strip()
        if not install_dir:
            messagebox.showwarning("Thiếu thư mục", "Vui lòng chọn thư mục cài đặt.")
            return
        self._set_busy(True)
        self._set_progress(0)
        threading.Thread(
            target=self._run_install,
            args=(install_dir,),
            daemon=True,
        ).start()

    def _run_install(self, install_dir: str):
        exe_path = None
        try:
            self._log("[i] Kiểm tra bản mới nhất từ GitHub...")
            release = updater.get_latest_release()
            if not release:
                raise RuntimeError("Không lấy được thông tin release từ GitHub.")

            asset = updater.get_zip_asset(release)
            if not asset:
                raise RuntimeError("Release không có file .zip để tải.")

            self._log(f"[i] Release: {release.get('tag_name') or release.get('name')}")
            self._log(f"[i] Asset   : {asset.get('name')}")
            self._log("[i] Đang tải zip...")

            from updater import download, install_zip

            import tempfile

            tmp = tempfile.mkdtemp(prefix="abp_install_")
            zip_path = os.path.join(tmp, asset["name"])

            def on_download(done, total):
                pct = int(done * 100 / total) if total else 0
                self._set_progress(pct)

            download(asset.get("browser_download_url") or asset.get("url"), zip_path, progress=on_download)
            self._set_progress(100)
            self._log(f"[OK] Đã tải xong: {zip_path}")

            self._log(f"[i] Giải nén vào: {install_dir}")
            install_zip(
                zip_path,
                install_dir,
                overwrite_database=True,
                version=release.get("tag_name") or release.get("name") or "",
            )

            exe_path = os.path.join(install_dir, updater.APP_EXE)
            if not os.path.exists(exe_path):
                # Có thể exe nằm trong sub-folder
                exe_path = updater.find_exe_in_dir(install_dir)
            if not exe_path:
                raise RuntimeError("Không tìm thấy AutoBotPanel.exe sau khi giải nén.")
            self._log(f"[OK] Đã giải nén. EXE: {exe_path}")

            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

            if self.create_desktop_shortcut.get():
                target = updater.create_desktop_shortcut(exe_path)
                self._log(f"[OK] Desktop shortcut: {target}")
            if self.create_start_menu_shortcut.get():
                target = updater.create_start_menu_shortcut(exe_path)
                self._log(f"[OK] Start Menu shortcut: {target}")

            self._set_progress(100)
            self._log("")
            self._log("==============================")
            self._log("✅ Cài đặt thành công!")
            self._log(f"   Thư mục : {install_dir}")
            self._log(f"   EXE     : {exe_path}")
            self._log("==============================")

            if self.launch_after.get() and exe_path and os.path.exists(exe_path):
                import subprocess

                self._log("[i] Đang khởi chạy app...")
                subprocess.Popen([exe_path])

            self.root.after(0, lambda: messagebox.showinfo("Hoàn tất", "Cài đặt AutoBotPanel thành công!"))
        except Exception as e:
            self._log(f"[ERROR] {e}")
            self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Cài đặt thất bại:\n{e}"))
        finally:
            self.root.after(0, lambda: self._set_busy(False))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    InstallerUI().run()
