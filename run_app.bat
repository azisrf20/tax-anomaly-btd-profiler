@echo off
REM ============================================================
REM  Tax Anomaly & BTD Profiler — Launcher
REM  Run this batch file to install dependencies and start the app
REM ============================================================

echo.
echo  =========================================
echo   Tax Anomaly ^& BTD Profiler
echo   DJP Tax Compliance Analytics Dashboard
echo  =========================================
echo.

REM --- Detect Python ---
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    set PYTHON=python
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL%==0 (
        set PYTHON=python3
    ) else (
        echo ERROR: Python tidak ditemukan. Pastikan Python 3.9+ sudah terinstall.
        pause
        exit /b 1
    )
)

echo  Menggunakan Python: %PYTHON%
%PYTHON% --version
echo.

REM --- Install / upgrade dependencies ---
echo  Menginstall dependensi dari requirements.txt ...
%PYTHON% -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Gagal menginstall dependensi. Periksa koneksi internet.
    pause
    exit /b 1
)
echo  Dependensi OK.
echo.

REM --- Generate dataset if missing ---
if not exist "data\dummy_wp_dataset.csv" (
    echo  Membuat dataset sintetis ...
    %PYTHON% src\data_generator.py
    echo  Dataset dibuat.
    echo.
)

REM --- Launch Streamlit ---
echo  Memulai dashboard ...
echo  Buka browser: http://localhost:8501
echo.
%PYTHON% -m streamlit run app.py --server.headless true
pause
