@echo off
setlocal enabledelayedexpansion

set APP_NAME=AutoBotPanel
set ENTRY_FILE=desktop_panel.py
set VENV_DIR=.build_venv
set DIST_DIR=dist
set BUILD_DIR=build
set SPEC_FILE=%APP_NAME%.spec
set ICON_FILE=templates\logo.ico

cd /d "%~dp0"

echo === Xoa output/build cu ===
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
mkdir "%DIST_DIR%" >nul 2>nul

if not exist "%ENTRY_FILE%" (
    echo [ERROR] Khong tim thay %ENTRY_FILE%.
    echo Hay dat build_exe.bat o thu muc goc du an, cung cap voi desktop_panel.py.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo [ERROR] Khong tim thay app.py.
    pause
    exit /b 1
)

echo.
echo === Kiem tra icon ===
if exist "%ICON_FILE%" (
    echo [OK] Dung icon: %ICON_FILE%
    set SPEC_ICON=icon='templates\\logo.ico',
) else (
    echo [WARNING] Khong tim thay %ICON_FILE%. EXE se dung icon mac dinh.
    set SPEC_ICON=icon=None,
)

echo.
echo === Tao moi truong build sach ===
py -3.10 -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [WARNING] Khong tao duoc venv bang py -3.10, thu bang python...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Khong tao duoc venv. Hay cai Python 3.10+ va thu lai.
        pause
        exit /b 1
    )
)

set PY=%CD%\%VENV_DIR%\Scripts\python.exe
if not exist "%PY%" (
    echo [ERROR] Khong tim thay Python trong venv: %PY%
    pause
    exit /b 1
)

echo.
echo === Cai thu vien runtime + PyInstaller ===
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto BUILD_ERROR

REM KHONG dung requirements.txt vi trong do co pytest/dev dependency.
REM Chi cai thu vien runtime can cho app + PyInstaller.
"%PY%" -m pip install Flask requests openai groq pyinstaller
if errorlevel 1 goto BUILD_ERROR

echo.
echo === Tao spec tam ===
> "%SPEC_FILE%" echo import sys
>> "%SPEC_FILE%" echo sys.setrecursionlimit(sys.getrecursionlimit() * 5)
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo block_cipher = None
>> "%SPEC_FILE%" echo.
>> "%SPEC_FILE%" echo a = Analysis(
>> "%SPEC_FILE%" echo     ['%ENTRY_FILE%'],
>> "%SPEC_FILE%" echo     pathex=[],
>> "%SPEC_FILE%" echo     binaries=[],
>> "%SPEC_FILE%" echo     datas=[('templates', 'templates'), ('static', 'static')],
>> "%SPEC_FILE%" echo     hiddenimports=[],
>> "%SPEC_FILE%" echo     hookspath=[],
>> "%SPEC_FILE%" echo     hooksconfig={},
>> "%SPEC_FILE%" echo     runtime_hooks=[],
>> "%SPEC_FILE%" echo     excludes=[
>> "%SPEC_FILE%" echo         'pytest','unittest','doctest','test','tests',
>> "%SPEC_FILE%" echo         'IPython','jupyter','notebook',
>> "%SPEC_FILE%" echo         'numpy','pandas','matplotlib','scipy',
>> "%SPEC_FILE%" echo         'torch','tensorflow','transformers','sklearn',
>> "%SPEC_FILE%" echo         'pygame','PyQt5','PyQt6'
>> "%SPEC_FILE%" echo     ],
>> "%SPEC_FILE%" echo     win_no_prefer_redirects=False,
>> "%SPEC_FILE%" echo     win_private_assemblies=False,
>> "%SPEC_FILE%" echo     cipher=block_cipher,
>> "%SPEC_FILE%" echo     noarchive=False,
>> "%SPEC_FILE%" echo )
>> "%SPEC_FILE%" echo pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
>> "%SPEC_FILE%" echo exe = EXE(
>> "%SPEC_FILE%" echo     pyz,
>> "%SPEC_FILE%" echo     a.scripts,
>> "%SPEC_FILE%" echo     a.binaries,
>> "%SPEC_FILE%" echo     a.zipfiles,
>> "%SPEC_FILE%" echo     a.datas,
>> "%SPEC_FILE%" echo     [],
>> "%SPEC_FILE%" echo     name='%APP_NAME%',
>> "%SPEC_FILE%" echo     debug=False,
>> "%SPEC_FILE%" echo     bootloader_ignore_signals=False,
>> "%SPEC_FILE%" echo     strip=False,
>> "%SPEC_FILE%" echo     upx=True,
>> "%SPEC_FILE%" echo     upx_exclude=[],
>> "%SPEC_FILE%" echo     runtime_tmpdir=None,
>> "%SPEC_FILE%" echo     console=False,
>> "%SPEC_FILE%" echo     disable_windowed_traceback=False,
>> "%SPEC_FILE%" echo     argv_emulation=False,
>> "%SPEC_FILE%" echo     target_arch=None,
>> "%SPEC_FILE%" echo     codesign_identity=None,
>> "%SPEC_FILE%" echo     entitlements_file=None,
>> "%SPEC_FILE%" echo     %SPEC_ICON%
>> "%SPEC_FILE%" echo )

echo.
echo === Dong goi EXE one-file windowed ===
"%PY%" -m PyInstaller --clean --noconfirm "%SPEC_FILE%"
if errorlevel 1 goto BUILD_ERROR

echo.
echo === Copy DB vao dist\database va copy debug ===
if not exist "%DIST_DIR%\database" mkdir "%DIST_DIR%\database"
if not exist "%DIST_DIR%\debug" mkdir "%DIST_DIR%\debug"

if exist "database\plates.db" (
    copy /y "database\plates.db" "%DIST_DIR%\database\plates.db" >nul
    echo [OK] Database: %DIST_DIR%\database\plates.db
) else if exist "plates.db" (
    copy /y "plates.db" "%DIST_DIR%\database\plates.db" >nul
    echo [OK] Database: %DIST_DIR%\database\plates.db
) else (
    echo [WARNING] Khong tim thay database\plates.db hoac plates.db de copy.
)

if exist "debug" (
    if exist "%DIST_DIR%\debug" rmdir /s /q "%DIST_DIR%\debug"
    xcopy "debug" "%DIST_DIR%\debug" /e /i /y >nul
    echo [OK] Debug: %DIST_DIR%\debug\
) else (
    mkdir "%DIST_DIR%\debug" >nul 2>nul
    echo [OK] Tao thu muc debug rong: %DIST_DIR%\debug\
)

echo.
echo === Don rac, chi giu dist ===
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"

echo.
echo [OK] Build xong.
echo - EXE: %DIST_DIR%\%APP_NAME%.exe
echo - DB : %DIST_DIR%\database\plates.db
echo - LOG: %DIST_DIR%\debug\
echo.
echo Neu Explorer van hien icon cu, bam F5 hoac restart Explorer vi Windows co cache icon.
pause
exit /b 0

:BUILD_ERROR
echo.
echo [ERROR] Build that bai. Dang don rac tam...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
pause
exit /b 1
