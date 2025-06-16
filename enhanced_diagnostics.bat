@echo off
echo ========================================
echo ENHANCED PSC2 Script Process Diagnostics
echo ========================================
echo.

echo [1] All Python processes (to see everything running)...
echo --------------------------------------------------------
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE
echo.

echo [2] Detailed token_monitor processes...
echo --------------------------------------
wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" get processid,commandline,creationdate,parentprocessid /format:table
echo.

echo [3] Detailed WorkingRate processes...
echo ------------------------------------
wmic process where "name='python.exe' and commandline like '%%WorkingRate.py%%'" get processid,commandline,creationdate,parentprocessid /format:table
echo.

echo [4] Detailed fluid_load_monitor processes...
echo --------------------------------------------
wmic process where "name='python.exe' and commandline like '%%fluid_load_monitor.py%%'" get processid,commandline,creationdate,parentprocessid /format:table
echo.

echo [5] Detailed collect_arrivals processes...
echo ------------------------------------------
wmic process where "name='python.exe' and commandline like '%%collect_arrivals.py%%'" get processid,commandline,creationdate,parentprocessid /format:table
echo.

echo [6] Process tree view (showing parent-child relationships)...
echo ----------------------------------------------------------
for /f "skip=1 tokens=1,2" %%a in ('wmic process where "name='python.exe' and (commandline like '%%token_monitor.py%%' or commandline like '%%WorkingRate.py%%' or commandline like '%%fluid_load_monitor.py%%' or commandline like '%%collect_arrivals.py%%')" get processid,parentprocessid') do (
    if "%%a" neq "" (
        echo PID: %%a ^| Parent PID: %%b
    )
)
echo.

echo [7] Check for multiple token monitor PIDs in PID file...
echo -------------------------------------------------------
if exist "monitor.pid" (
    echo PID file contains:
    type monitor.pid
    echo.
    set /p STORED_PID=<monitor.pid
    echo Checking if stored PID (!STORED_PID!) is still running:
    tasklist /FI "PID eq !STORED_PID!" 2>nul | find "python" >nul
    if !errorlevel! equ 0 (
        echo ✓ Stored PID is running
    ) else (
        echo ✗ Stored PID is NOT running (stale PID file)
    )
) else (
    echo No monitor.pid file found
)
echo.

echo [8] Summary - Count of each script type...
echo ------------------------------------------
for /f %%i in ('wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" get processid /format:value ^| find "ProcessId" ^| find /c "="') do echo token_monitor.py processes: %%i
for /f %%i in ('wmic process where "name='python.exe' and commandline like '%%WorkingRate.py%%'" get processid /format:value ^| find "ProcessId" ^| find /c "="') do echo WorkingRate.py processes: %%i
for /f %%i in ('wmic process where "name='python.exe' and commandline like '%%fluid_load_monitor.py%%'" get processid /format:value ^| find "ProcessId" ^| find /c "="') do echo fluid_load_monitor.py processes: %%i
for /f %%i in ('wmic process where "name='python.exe' and commandline like '%%collect_arrivals.py%%'" get processid /format:value ^| find "ProcessId" ^| find /c "="') do echo collect_arrivals.py processes: %%i
echo.

echo [9] Check recent log entries for clues...
echo -----------------------------------------
if exist "logs\monitor.log" (
    echo Recent monitor.log entries:
    powershell -Command "if (Test-Path 'logs\monitor.log') { Get-Content 'logs\monitor.log' -Tail 10 }"
) else (
    echo No monitor.log found
)
echo.

echo ========================================
echo ANALYSIS SUMMARY
echo ========================================
echo If you see:
echo - Multiple token_monitor.py processes = Problem! Should only be 1
echo - Multiple of the same script = Problem! Should be 1 of each
echo - Different Parent PIDs = Scripts started from different sources
echo - Stale PID file = Token monitor restarted but PID file not updated
echo.
pause