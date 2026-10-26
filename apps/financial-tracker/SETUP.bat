@echo off
echo ========================================
echo  Vault Financial Tracker - Setup
echo ========================================
echo.
echo Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: npm install failed. Make sure Node.js is installed.
    pause
    exit /b 1
)
echo.
echo ========================================
echo  Setup complete!
echo  Run START.bat to launch the app.
echo ========================================
pause
