"""
AutoBotPanel - Cập nhật & Cài đặt tự động từ GitHub Release.

- Tải release zip mới nhất về, giải nén, ghi đè exe hiện tại.
- An toàn trên Windows: exe đang chạy sẽ được thay bằng file .new + batch helper
  (taskkill -> del -> move -> start), sau đó app tự khởi chạy lại.
- Tạo shortcut Desktop / Start Menu.

Chỉ dùng thư viện chuẩn (urllib, zipfile, tkinter, subprocess) để không cần cài thêm gì.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

GITHUB_REPO = "AnhTuan2003ml/bot_page"
APP_NAME = "AutoBotPanel"
APP_EXE = f"{APP_NAME}.exe"
RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "AutoBotPanel-Updater"

# Version hiện tại (lưu file version.txt cạnh exe/source).
# Nếu không có file, dùng giá trị mặc định này.
DEFAULT_VERSION = "v1.0.0"
VERSION_FILE_NAME = "version.txt"

_CHUNK = 65536


# --------------------------------------------------------------------------- #
# Tiện ích
# --------------------------------------------------------------------------- #
def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Thư mục chứa exe khi đóng gói, hoặc thư mục source khi chạy python."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def version_file(base_dir=None):
    base = base_dir or app_dir()
    return os.path.join(base, VERSION_FILE_NAME)


def get_current_version(base_dir=None):
    """Đọc version hiện tại từ file version.txt (cạnh exe/source)."""
    try:
        with open(version_file(base_dir), encoding="utf-8") as fh:
            v = fh.read().strip()
            if v:
                return v
    except Exception:
        pass
    return DEFAULT_VERSION


def set_current_version(version, base_dir=None):
    """Ghi version hiện tại vào file version.txt."""
    try:
        with open(version_file(base_dir), "w", encoding="utf-8") as fh:
            fh.write(str(version).strip())
        return True
    except Exception:
        return False


def _norm_version(v):
    """Chuẩn hóa version: v1.0.1 -> 1.0.1, 1.0 -> 1.0.0... để so sánh."""
    if not v:
        return ""
    v = str(v).strip()
    if v.lower().startswith("v"):
        v = v[1:]
    parts = []
    for p in v.replace("-", ".").split("."):
        if p.isdigit():
            parts.append(int(p))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest, current):
    """True nếu latest > current (chỉ so phần số, không so pre-release)."""
    return _norm_version(latest) > _norm_version(current)


def _fmt_size(size):
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        size = 0
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #
def _api_get(url):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_latest_release():
    """Lấy release mới nhất. Trả về dict của GitHub hoặc None."""
    try:
        return _api_get(RELEASE_API)
    except Exception:
        pass
    try:
        data = _api_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases")
        return data[0] if data else None
    except Exception:
        return None


def get_zip_asset(release):
    """Tìm asset dạng .zip trong release (ưu tiên đuôi .zip)."""
    assets = release.get("assets") or []
    for asset in assets:
        if str(asset.get("name", "")).lower().endswith(".zip"):
            return asset
    return assets[0] if assets else None


# --------------------------------------------------------------------------- #
# Tải & giải nén
# --------------------------------------------------------------------------- #
def download(url, dest_path, progress=None):
    """Tải file từ URL về dest_path. progress(downloaded, total)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        written = 0
        with open(dest_path, "wb") as out:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                written += len(chunk)
                if progress:
                    progress(written, total)
    return dest_path


def _safe_join(base, name):
    target = os.path.realpath(os.path.join(base, name))
    if not target.startswith(os.path.realpath(base)):
        raise ValueError(f"Unsafe path in zip: {name}")
    return target


def _find_payload_root(extract_dir):
    """Nếu zip có đúng 1 thư mục gốc (vd 'dist/'), coi đó là gốc nội dung."""
    entries = os.listdir(extract_dir)
    dirs = [e for e in entries if os.path.isdir(os.path.join(extract_dir, e))]
    files = [e for e in entries if os.path.isfile(os.path.join(extract_dir, e))]
    if not files and len(dirs) == 1:
        return os.path.join(extract_dir, dirs[0])
    return extract_dir


def extract_and_root(zip_path, dest_dir, progress=None):
    """Giải nén zip vào dest_dir rồi trả về thư mục chứa nội dung thật."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        total = len(names)
        for i, name in enumerate(names):
            target = _safe_join(dest_dir, name)
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if progress:
                progress(i + 1, total)
    return _find_payload_root(dest_dir)


def find_exe_in_dir(root):
    for dirpath, _dirs, filenames in os.walk(root):
        if APP_EXE.lower() in [f.lower() for f in filenames]:
            return os.path.join(dirpath, APP_EXE)
    return None


# --------------------------------------------------------------------------- #
# Cài đặt / cập nhật
# --------------------------------------------------------------------------- #
def copy_install(src_root, install_dir, overwrite_database=False):
    """Copy nội dung src_root vào install_dir. Giữ DB cũ nếu overwrite_database=False."""
    os.makedirs(install_dir, exist_ok=True)
    for name in os.listdir(src_root):
        src = os.path.join(src_root, name)
        dst = os.path.join(install_dir, name)
        if os.path.isdir(src):
            if name.lower() == "database" and os.path.exists(dst) and not overwrite_database:
                continue
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    return install_dir


def install_zip(zip_path, install_dir, overwrite_database=True, progress=None, version=None):
    """Giải nén zip vào install_dir (dùng cho Installer / bản mới)."""
    tmp = tempfile.mkdtemp(prefix="abp_install_")
    try:
        root = extract_and_root(zip_path, tmp, progress=progress)
        copy_install(root, install_dir, overwrite_database=overwrite_database)
        if version:
            set_current_version(version, base_dir=install_dir)
        return install_dir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_restart_bat(install_dir):
    """Tạo batch thay exe đang chạy bằng exe mới (.new) rồi khởi chạy lại.

    - taskkill /f /im (KHÔNG dùng /t): /t sẽ giết cả process tree gồm cả
      cmd.exe đang chạy batch này, làm batch chết giữa chừng -> app không
      khởi động lại. /im đã giết hết mọi process tên AutoBotPanel.exe
      (cả bootloader cha lẫn process con của PyInstaller onefile).
    - Thử lại del/move nhiều lần (Windows giữ file vài giây sau khi kill).
    - Ghi log _update_log.txt để dễ debug nếu thất bại.
    """
    old = os.path.join(install_dir, APP_EXE)
    new = os.path.join(install_dir, APP_EXE + ".new")
    bat = os.path.join(install_dir, "_update_restart.bat")
    logf = os.path.join(install_dir, "_update_log.txt")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        'cd /d "%~dp0"',
        f'echo Dang cap nhat AutoBotPanel... > "{logf}"',
        f'echo old={old} >> "{logf}"',
        f'echo new={new} >> "{logf}"',
        "ping 127.0.0.1 -n 2 >nul",
        f'taskkill /f /im {APP_EXE} >> "{logf}" 2>&1',
        "ping 127.0.0.1 -n 2 >nul",
        ":retry_del",
        f'del /f /q "{old}" >> "{logf}" 2>&1',
        f'if exist "{old}" (',
        "    ping 127.0.0.1 -n 1 >nul",
        "    goto retry_del",
        ")",
        f'move /y "{new}" "{old}" >> "{logf}" 2>&1',
        f'if not exist "{new}" echo MOVE_OK >> "{logf}"',
        f'if exist "{new}" echo MOVE_FAIL >> "{logf}"',
        f'start "" "{old}"',
        'del "%~f0"',
    ]
    with open(bat, "w", encoding="utf-8") as fh:
        fh.write("\r\n".join(lines))
    return bat


def cleanup_pending_update(base_dir=None):
    """Dọn file tạm của lần update chưa hoàn tất khi app khởi động.

    - Nếu còn _update_restart.bat: update chưa áp xong -> tự xoá để lần sau cập nhật lại.
    - Xoá AutoBotPanel.exe.new và _update_log.txt nếu còn sót.
    """
    base = base_dir or app_dir()
    for name in (APP_EXE + ".new", "_update_restart.bat", "_update_restart_source.bat", "_update_log.txt"):
        p = os.path.join(base, name)
        try:
            if os.path.exists(p):
                os.remove(p)
                print(f"[UPDATER] Cleanup pending: {p}")
        except Exception:
            pass


def stage_update(release, log=print, progress=None):
    """Tải zip release mới nhất và chuẩn bị ghi đè exe hiện tại.

    Trả về thư mục cài đặt nếu thành công, kèm thông tin loại nâng cấp.
    """
    asset = get_zip_asset(release)
    if not asset:
        raise RuntimeError("Không tìm thấy file .zip trong release.")
    url = asset.get("browser_download_url") or asset.get("url")
    if not url:
        raise RuntimeError("Asset zip không có đường dẫn tải.")
    if not str(asset.get("name", "")).lower().endswith(".zip"):
        raise RuntimeError(f"Asset không phải zip: {asset.get('name')}")

    log(f"[UPDATE] Tải {asset['name']} ({_fmt_size(asset.get('size'))})...")
    tmp = tempfile.mkdtemp(prefix="abp_update_")
    try:
        zip_path = os.path.join(tmp, asset["name"])
        download(url, zip_path, progress=progress)
        log("[UPDATE] Giải nén zip...")
        payload_root = extract_and_root(zip_path, tmp, progress=progress)
        exe_path = find_exe_in_dir(payload_root)
        if not exe_path:
            raise RuntimeError("Không tìm thấy AutoBotPanel.exe trong zip đã tải.")

        target_dir = app_dir()
        if is_frozen():
            new_exe = os.path.join(target_dir, APP_EXE + ".new")
            shutil.copy2(exe_path, new_exe)
            write_restart_bat(target_dir)
            set_current_version(release.get("tag_name") or release.get("name") or "")
            return target_dir, "restart"
        copy_install(payload_root, target_dir, overwrite_database=False)
        set_current_version(release.get("tag_name") or release.get("name") or "")
        return target_dir, "copy"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def launch_update_and_exit():
    """Chạy batch thay exe và tự khởi động lại app (gọi sau khi đã stage)."""
    bat = os.path.join(app_dir(), "_update_restart.bat")
    if not os.path.exists(bat):
        raise RuntimeError("Chưa có batch cập nhật.")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, "CREATE_NO_WINDOW")
    subprocess.Popen(
        ["cmd", "/c", bat],
        creationflags=flags,
        close_fds=True,
    )
    return bat


def write_source_restart_bat(install_dir, entry_script):
    """Tạo batch khởi động lại app ở chế độ source (chạy python).

    - Chờ vài giây để response poll cuối được gửi xong.
    - Kill process hiện tại rồi chạy lại python với entry_script (app.py hoặc launcher).
    """
    current_pid = os.getpid()
    bat = os.path.join(install_dir, "_update_restart_source.bat")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        'cd /d "%~dp0"',
        "ping 127.0.0.1 -n 3 >nul",
        f'taskkill /f /pid {current_pid} >nul 2>&1',
        "ping 127.0.0.1 -n 2 >nul",
        f'start "" "{sys.executable}" "{entry_script}"',
        'del "%~f0"',
    ]
    with open(bat, "w", encoding="utf-8") as fh:
        fh.write("\r\n".join(lines))
    return bat


def launch_source_update_and_exit():
    """Khởi động lại app ở chế độ source để áp dụng code mới (cả backend)."""
    install_dir = app_dir()
    entry = os.path.abspath(sys.argv[0])
    if not entry.lower().endswith(".py"):
        entry = os.path.join(install_dir, "app.py")
    bat = write_source_restart_bat(install_dir, entry)
    if not os.path.exists(bat):
        raise RuntimeError("Chưa tạo được batch khởi động lại.")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, "CREATE_NO_WINDOW")
    subprocess.Popen(
        ["cmd", "/c", bat],
        creationflags=flags,
        close_fds=True,
    )
    return bat


# --------------------------------------------------------------------------- #
# Shortcut
# --------------------------------------------------------------------------- #
def desktop_dir():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def start_menu_dir():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def create_shortcut(exe_path, shortcut_path):
    """Tạo file .lnk bằng PowerShell (không cần pywin32)."""
    exe_path = os.path.abspath(exe_path)
    shortcut_path = os.path.abspath(shortcut_path)
    working = os.path.dirname(exe_path)
    ps = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{shortcut_path}');"
        f"$s.TargetPath = '{exe_path}';"
        f"$s.WorkingDirectory = '{working}';"
        f"$s.IconLocation = '{exe_path},0';"
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def create_desktop_shortcut(exe_path):
    target = os.path.join(desktop_dir(), f"{APP_NAME}.lnk")
    create_shortcut(exe_path, target)
    return target


def create_start_menu_shortcut(exe_path):
    target = os.path.join(start_menu_dir(), f"{APP_NAME}.lnk")
    create_shortcut(exe_path, target)
    return target
