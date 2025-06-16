@echo off
echo ========================================
echo PSC2 Script Process Diagnostics
echo ========================================
echo.

echo [1] Checking for WorkingRate processes...
echo ----------------------------------------
wmic process where "name='python.exe' and commandline like '%%WorkingRate.py%%'" get processid,commandline,creationdate /format:table
echo.

echo [2] Checking for fluid_load_monitor processes...
echo ------------------------------------------------
wmic process where "name='python.exe' and commandline like '%%fluid_load_monitor.py%%'" get processid,commandline,creationdate /format:table
echo.

echo [3] Checking for collect_arrivals processes...
echo ----------------------------------------------
wmic process where "name='python.exe' and commandline like '%%collect_arrivals.py%%'" get processid,commandline,creationdate /format:table
echo.

echo [4] Checking for token_monitor processes...
echo -------------------------------------------
wmic process where "name='python.exe' and commandline like '%%token_monitor.py%%'" get processid,commandline,creationdate /format:table
echo.

echo [5] Summary of all Python monitoring processes...
echo -------------------------------------------------
for /f "skip=1 tokens=1,2" %%a in ('wmic process where "name='python.exe' and (commandline like '%%WorkingRate.py%%' or commandline like '%%fluid_load_monitor.py%%' or commandline like '%%collect_arrivals.py%%' or commandline like '%%token_monitor.py%%')" get processid,creationdate') do (
    if "%%a" neq "" (
        echo PID: %%a ^| Started: %%b
    )
)
echo.

echo ========================================
echo CLEANUP OPTIONS:
echo ========================================
echo.
echo To kill a specific process: taskkill /PID [ProcessID] /F
echo To kill all WorkingRate:   taskkill /F /IM python.exe /FI "WINDOWTITLE eq *WorkingRate*"
echo To kill all monitoring:    taskkill /F /IM python.exe
echo.
echo RECOMMENDED: Kill older processes (earlier creation dates) and keep newer ones
echo.

pause