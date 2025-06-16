@echo off
setlocal enabledelayedexpansion

:: Configuration
set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=python"
set "MONITOR_SCRIPT=%SCRIPT_DIR%token_monitor.py"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "PID_FILE=%SCRIPT_DIR%monitor.pid"

:: Create logs directory if it doesn't exist
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Main script logic
if "%1"=="start" goto start_monitor
if "%1"=="stop" goto stop_monitor
if "%1"=="restart" goto restart_monitor
if "%1"=="status" goto status_monitor
if "%1"=="logs" goto follow_logs
if "%1"=="refresh" goto refresh_token
if "%1"=="help" goto show_help
if "%1"=="" goto show_default
goto show_help

:show_default
echo AWS Script Monitor
echo Run '%~nx0 help' for usage information
echo Quick start: '%~nx0 start' to begin monitoring
echo.
goto status_monitor

:start_monitor
echo [%date% %time%] Checking if monitor is already running...
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    tasklist /FI "PID eq !PID!" 2>nul | find "python" >nul
    if !errorlevel! equ 0 (
        echo [%date% %time%] Token monitor is already running (PID: !PID!)
        goto :eof
    ) else (
        echo [%date% %time%] Removing stale PID file...
        del "%PID_FILE%" 2>nul
    )
)

echo [%date% %time%] Starting token monitor...

:: Check if monitor script exists
if not exist "%MONITOR_SCRIPT%" (
    echo [%date% %time%] ERROR: Monitor script not found at %MONITOR_SCRIPT%
    goto :eof
)

:: Test Python
echo [%date% %time%] Testing Python...
%PYTHON_EXE% --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [%date% %time%] ERROR: Python not found. Trying python3...
    set "PYTHON_EXE=python3"
    python3 --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [%date% %time%] ERROR: Neither python nor python3 found!
        goto :eof
    )
)

echo [%date% %time%] Starting monitor process...
start /B "" "%PYTHON_EXE%" "%MONITOR_SCRIPT%" > "%LOG_DIR%\monitor.log" 2>&1

:: Wait and get PID
timeout /t 3 /nobreak >nul

:: Find the python process (simplified approach)
for /f "skip=1 tokens=2" %%i in ('wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" get processid 2^>nul') do (
    if "%%i" neq "" (
        echo %%i > "%PID_FILE%"
        echo [%date% %time%] Token monitor started successfully (PID: %%i)
        echo [%date% %time%] Logs: %LOG_DIR%\monitor.log
        echo [%date% %time%] Run 'mwinit -o' to refresh tokens when needed
        goto :eof
    )
)

:: Fallback - just assume it started
echo [%date% %time%] Monitor started (PID detection failed but process should be running)
echo [%date% %time%] Check logs: %LOG_DIR%\monitor.log
goto :eof

:stop_monitor
echo [%date% %time%] Stopping token monitor...
if not exist "%PID_FILE%" (
    echo [%date% %time%] No PID file found. Trying to kill all python processes running token_monitor.py...
    wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" delete >nul 2>&1
    echo [%date% %time%] Stop command completed
    goto :eof
)

set /p PID=<"%PID_FILE%"
echo [%date% %time%] Stopping process (PID: %PID%)...

taskkill /PID %PID% /T /F >nul 2>&1
if !errorlevel! equ 0 (
    echo [%date% %time%] Token monitor stopped successfully
) else (
    echo [%date% %time%] Failed to stop process, trying alternative method...
    wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" delete >nul 2>&1
)

del "%PID_FILE%" 2>nul
goto :eof

:restart_monitor
call :stop_monitor
timeout /t 2 /nobreak >nul
call :start_monitor
goto :eof

:status_monitor
echo [%date% %time%] Checking monitor status...
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    tasklist /FI "PID eq !PID!" 2>nul | find "python" >nul
    if !errorlevel! equ 0 (
        echo [%date% %time%] Token monitor is RUNNING (PID: !PID!)
        
        :: Show recent log entries if available
        if exist "%LOG_DIR%\monitor.log" (
            echo.
            echo Recent log entries:
            powershell -Command "if (Test-Path '%LOG_DIR%\monitor.log') { Get-Content '%LOG_DIR%\monitor.log' -Tail 5 }"
        )
        goto :eof
    ) else (
        echo [%date% %time%] PID file exists but process not found. Cleaning up...
        del "%PID_FILE%" 2>nul
    )
)

:: Check if any python process is running token_monitor
wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" get processid >nul 2>&1
if !errorlevel! equ 0 (
    echo [%date% %time%] Token monitor appears to be running (no PID file)
) else (
    echo [%date% %time%] Token monitor is NOT running
)

:: Check if log file exists and show status
if exist "%LOG_DIR%\monitor.log" (
    echo [%date% %time%] Log file exists: %LOG_DIR%\monitor.log
) else (
    echo [%date% %time%] No log file found
)

:: Check if required scripts exist
echo.
echo Script status:
if exist "%MONITOR_SCRIPT%" (
    echo   ✓ token_monitor.py found
) else (
    echo   ✗ token_monitor.py NOT found
)

if exist "WorkingRate.py" (
    echo   + WorkingRate.py found
) else (
    echo   - WorkingRate.py NOT found
)

if exist "fluid_load_monitor.py" (
    echo   + fluid_load_monitor.py found
) else (
    echo   - fluid_load_monitor.py NOT found
)

if exist "collect_arrivals.py" (
    echo   + collect_arrivals.py found
) else (
    echo   - collect_arrivals.py NOT found
)

:: Check token file
set "TOKEN_FILE=%USERPROFILE%\.midway\cookie"
if exist "%TOKEN_FILE%" (
    echo   ✓ Midway token file exists
) else (
    echo   ✗ Midway token file NOT found - run 'mwinit -o'
)
goto :eof

:follow_logs
if exist "%LOG_DIR%\monitor.log" (
    echo Following logs from %LOG_DIR%\monitor.log (Ctrl+C to stop):
    powershell -Command "Get-Content '%LOG_DIR%\monitor.log' -Wait"
) else (
    echo Log file not found: %LOG_DIR%\monitor.log
    echo Try starting the monitor first: %~nx0 start
)
goto :eof

:refresh_token
echo [%date% %time%] Refreshing midway token...
mwinit -o
if !errorlevel! equ 0 (
    echo [%date% %time%] Token refreshed successfully
    echo [%date% %time%] Monitor will automatically detect the new token and restart scripts
) else (
    echo [%date% %time%] Failed to refresh token
)
goto :eof

:show_help
echo AWS Script Monitor - Token Management and Script Launcher
echo.
echo Usage: %~nx0 [COMMAND]
echo.
echo Commands:
echo     start       Start the token monitor
echo     stop        Stop the token monitor
echo     restart     Restart the token monitor
echo     status      Show monitor status
echo     logs        Follow monitor logs
echo     refresh     Refresh midway token (runs mwinit -o)
echo     help        Show this help message
echo.
echo The monitor will:
echo - Watch for midway token changes
echo - Automatically restart scripts when tokens are refreshed
echo - Monitor script health and restart failed scripts
echo - Log all activities to %LOG_DIR%\
echo.
echo To refresh your token at any time, run:
echo     mwinit -o
echo.
echo The monitor will automatically detect the new token and restart all scripts.
goto :eof

:eof
endlocal