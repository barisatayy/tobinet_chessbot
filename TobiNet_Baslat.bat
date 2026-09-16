@echo off
title TobiNet Chess AI

:: 1. Proje dizinine gec (Masaustunden de calissa chess_ai klasorunu bulur)
if exist "%~dp0server.py" (
    cd /d "%~dp0"
) else if exist "%~dp0chess_ai\server.py" (
    cd /d "%~dp0chess_ai"
) else if exist "C:\Users\tobil\Desktop\chess_ai\server.py" (
    cd /d "C:\Users\tobil\Desktop\chess_ai"
) else if exist "%USERPROFILE%\Desktop\chess_ai\server.py" (
    cd /d "%USERPROFILE%\Desktop\chess_ai"
) else if exist "%USERPROFILE%\OneDrive\Desktop\chess_ai\server.py" (
    cd /d "%USERPROFILE%\OneDrive\Desktop\chess_ai"
) else (
    echo [HATA] chess_ai klasoru veya server.py bulunamadi!
    pause
    exit /b 1
)

:: 2. Python ortamini otomatik tespit et
set "PY_CMD="

:: Once Flask ve chess kutuphanesi hazir kurulu olan Python var mi ara:
py -3 -c "import flask, chess" >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=py -3"
    goto :FOUND
)

python -c "import flask, chess" >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :FOUND
)

py -c "import flask, chess" >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=py"
    goto :FOUND
)

call :TEST_PATH "%USERPROFILE%\anaconda3\python.exe"
if defined PY_CMD goto :FOUND
call :TEST_PATH "%USERPROFILE%\miniconda3\python.exe"
if defined PY_CMD goto :FOUND

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    call :TEST_PATH "%%D\python.exe"
    if defined PY_CMD goto :FOUND
)
for /d %%D in ("%ProgramFiles%\Python*") do (
    call :TEST_PATH "%%D\python.exe"
    if defined PY_CMD goto :FOUND
)

:: Flask kurulu bir ortam bulunamadiysa, sistemdeki calisir herhangi bir Python'u bul:
py -3 --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=py -3"
    goto :DO_INSTALL
)

python --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :DO_INSTALL
)

py --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=py"
    goto :DO_INSTALL
)

call :FIND_ANY_PATH "%USERPROFILE%\anaconda3\python.exe"
if defined PY_CMD goto :DO_INSTALL
call :FIND_ANY_PATH "%USERPROFILE%\miniconda3\python.exe"
if defined PY_CMD goto :DO_INSTALL

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    call :FIND_ANY_PATH "%%D\python.exe"
    if defined PY_CMD goto :DO_INSTALL
)
for /d %%D in ("%ProgramFiles%\Python*") do (
    call :FIND_ANY_PATH "%%D\python.exe"
    if defined PY_CMD goto :DO_INSTALL
)

echo [HATA] Sistemde hicbir Python kurulumu bulunamadi!
pause
exit /b 1

:TEST_PATH
if not exist "%~1" exit /b 0
"%~1" -c "import flask, chess" >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD="%~1""
)
exit /b 0

:FIND_ANY_PATH
if not exist "%~1" exit /b 0
"%~1" --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD="%~1""
)
exit /b 0

:DO_INSTALL
cls
echo ========================================================
echo             TOBINET CHESS AI BASLATICI
echo ========================================================
echo.
echo [*] Secilen Python : %PY_CMD%
echo [!] Flask veya diger kutuphaneler eksik gorunuyor.
echo [*] Gerekli paketler yukleniyor (pip install -r requirements.txt)...
echo     (Lutfen biraz bekleyin, paketler yukleniyor)
echo.
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [HATA] Paketler yuklenirken bir sorun olustu.
    pause
    exit /b 1
)

:FOUND
cls
echo ========================================================
echo             TOBINET CHESS AI BASLATICI
echo ========================================================
echo.
echo [*] Proje Dizini : %CD%
echo [*] Python       : %PY_CMD%
echo [*] Arayuz       : http://localhost:5000
echo.
echo [1/2] Tarayici 2 saniye icinde otomatik acilacak...
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5000"

echo [2/2] Sunucu calistiriliyor... (Kapatmak icin Ctrl+C yapin)
echo.
echo --------------------------------------------------------
%PY_CMD% server.py
if errorlevel 1 (
    echo.
    echo [!] Sunucu bir hata ile kapandi.
    pause
)
