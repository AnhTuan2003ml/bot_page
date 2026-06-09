@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_NAME=AutoBotPanel"
set "ENTRY=app.py"
set "DIST_DIR=dist"
set "BUILD_DIR=build"
set "SPEC_FILE=%APP_NAME%.spec"
set "VENV_DIR=.build_venv"

if not exist "%ENTRY%" (
    echo [ERROR] Khong tim thay %ENTRY%. Hay dat file build_exe.bat o thu muc goc du an.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Khong tim thay python trong PATH.
    pause
    exit /b 1
)

echo === Xoa output/build cu ===
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "bot_fb.spec" del /f /q "bot_fb.spec"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"

echo.
echo === Tao moi truong build sach ===
python -m venv "%VENV_DIR%"
if errorlevel 1 goto :fail

set "VPY=%CD%\%VENV_DIR%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [ERROR] Khong tao duoc virtualenv build.
    goto :fail
)

echo.
echo === Cai dung thu vien production duoc import trong du an ===
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

set "DATA_ARGS=--add-data templates;templates"
if exist "static" set "DATA_ARGS=!DATA_ARGS! --add-data static;static"

set "ICON_ARGS="
if exist "templates\logo.ico" set "ICON_ARGS=--icon templates\logo.ico"

REM Loai tru cac goi nang khong duoc import boi du an, tranh PyInstaller keo nham tu Python global.
set "EXCLUDE_ARGS="
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module tests --exclude-module pytest --exclude-module unittest"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module torch --exclude-module torchvision --exclude-module torchaudio"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module transformers --exclude-module tensorflow --exclude-module keras"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module pandas --exclude-module numpy --exclude-module scipy --exclude-module sklearn"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module matplotlib --exclude-module IPython --exclude-module jupyter --exclude-module notebook"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module tkinter --exclude-module pygame"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module cv2 --exclude-module PIL --exclude-module imageio --exclude-module altair"
set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module pyarrow --exclude-module numba --exclude-module llvmlite"

echo.
echo === Dong goi EXE one-file chi voi import cua du an ===
"%VPY%" -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name "%APP_NAME%" ^
  !ICON_ARGS! ^
  !DATA_ARGS! ^
  --paths "%CD%" ^
  --hidden-import ai_agent ^
  --hidden-import brain ^
  --hidden-import database ^
  --hidden-import domains ^
  --hidden-import services ^
  --hidden-import utils ^
  --hidden-import web ^
  --hidden-import controls ^
  !EXCLUDE_ARGS! ^
  "%ENTRY%"
if errorlevel 1 goto :fail

echo.
echo === Copy database/debug ra cung cap EXE, khong nhung vao EXE ===
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

if exist "database\plates.db" (
    copy /y "database\plates.db" "%DIST_DIR%\plates.db" >nul
) else (
    echo [WARN] Khong tim thay database\plates.db. App se tu tao plates.db khi chay neu code ho tro.
)

if exist "%DIST_DIR%\debug" rmdir /s /q "%DIST_DIR%\debug"
if exist "debug" (
    xcopy "debug" "%DIST_DIR%\debug\" /E /I /Y >nul
) else (
    mkdir "%DIST_DIR%\debug"
)

echo.
echo === Don rac build, chi giu thu muc dist ===
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "bot_fb.spec" del /f /q "bot_fb.spec"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"

if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo [ERROR] Build xong nhung khong thay %DIST_DIR%\%APP_NAME%.exe
    pause
    exit /b 1
)

echo.
echo [OK] Build thanh cong. Chi can giu/copy thu muc dist:
echo   %DIST_DIR%\%APP_NAME%.exe
echo   %DIST_DIR%\plates.db
echo   %DIST_DIR%\debug\
echo.
echo Luu y: plates.db va debug nam ngoai EXE, cung cap voi EXE, nen co the sua/thay the rieng.
pause
exit /b 0

:fail
echo.
echo === Don rac sau khi loi ===
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"
if exist "bot_fb.spec" del /f /q "bot_fb.spec"
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
echo.
echo [ERROR] Build that bai. Vui long xem log phia tren.
pause
exit /b 1
