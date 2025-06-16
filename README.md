# AWS Script Monitor - PSC2 Automation System

## Overview
This system automatically monitors and manages your AWS scripts with intelligent token management and duplicate prevention. It handles WorkingRate monitoring, Fluid Load UPH alerts, and LUCY compliance tracking.

## Quick Start
```cmd
# Daily startup (run once in the morning)
mwinit -o
startup_scripts.bat start

# Refresh token when needed (throughout the day)
mwinit -o
# Scripts automatically restart with new token!

# Check system status
startup_scripts.bat status
```

## File Structure
```
D:\Users\pucpetey\Run code\
├── token_monitor.py          # Main monitoring system
├── WorkingRate.py            # Quarter problem solve rates (automated)
├── fluid_load_monitor.py     # Hourly UPH monitoring (automated)
├── collect_arrivals.py       # LUCY compliance tracking (automated)
├── startup_scripts.bat       # Windows management script
├── enhanced_diagnostics.bat  # Troubleshooting tool
├── config.json              # Configuration settings
└── logs\
    └── monitor.log           # System activity logs
```

## Commands Reference

### Basic Operations
```cmd
# Start the monitoring system
startup_scripts.bat start

# Stop all scripts
startup_scripts.bat stop

# Restart everything
startup_scripts.bat restart

# Check system status
startup_scripts.bat status

# View live logs
startup_scripts.bat logs

# Refresh token and auto-restart scripts
startup_scripts.bat refresh
```

### Troubleshooting Commands
```cmd
# Comprehensive system diagnostics
enhanced_diagnostics.bat

# Check what Python processes are running
tasklist | find "python"

# Emergency stop - kill all Python processes
taskkill /F /IM python.exe

# Kill specific process by PID
taskkill /PID [ProcessID] /F

# View recent log entries
type logs\monitor.log
```

### Token Management
```cmd
# Refresh AWS token (primary command)
mwinit -o

# Check token validity
dir "%USERPROFILE%\.midway\cookie"

# Check token expiration
startup_scripts.bat status
```

## What Each Script Does

### 🔵 WorkingRate.py
- **Purpose**: Problem Solve Rates monitoring
- **Schedule**: Sends reports 1 minute after each quarter ends
- **Webhook**: PSC2 Tracker channel
- **Quarters**: 
  - Quarter 1 Days: 7:30-9:30 → Report at 9:31
  - Quarter 2 Days: 9:45-11:45 → Report at 11:46
  - Quarter 3 Days: 12:15-15:00 → Report at 15:01
  - Quarter 4 Days: 15:15-17:30 → Report at 17:31

### 🟠 fluid_load_monitor.py
- **Purpose**: UPH (Units Per Hour) monitoring
- **Schedule**: Hourly alerts for associates below 190 UPH
- **Webhook**: Fluid Load UPH Performance channel
- **Process ID**: 01003021

### 🟡 collect_arrivals.py
- **Purpose**: LUCY compliance monitoring for live loads
- **Schedule**: Real-time monitoring (checks every 60 seconds)
- **Webhook**: LUCY IN THE SKY WITH DIAMONDS channel
- **Notifications**: Arrivals, check-ins, compliance status, missed thresholds

### 🔧 token_monitor.py
- **Purpose**: Master controller and token management
- **Monitor Webhook**: PSC2-webhook-monitor channel
- **Functions**: Script health monitoring, automatic restarts, token refresh detection

## Daily Workflow

### Morning Setup (Once)
```cmd
# 1. Authenticate
mwinit -o

# 2. Start monitoring
startup_scripts.bat start

# 3. Verify everything is running
startup_scripts.bat status
```

### During the Day (As Needed)
```cmd
# When token expires (every 8-12 hours)
mwinit -o
# Scripts automatically restart - no other action needed!
```

### End of Day (Optional)
```cmd
# Stop monitoring (or leave running overnight)
startup_scripts.bat stop
```

## Notification Channels

### PSC2-webhook-monitor
- 🚀 Token Monitor Started
- 🔄 Token Refreshed  
- ✅ All Scripts Started
- ❌ Error notifications

### PSC2 Tracker
- 📊 Quarter problem solve rate reports
- 📈 Performance metrics by process

### Fluid Load UPH Performance  
- ⚠️ Low UPH alerts (below 190)
- 📋 Hourly performance summaries

### LUCY IN THE SKY WITH DIAMONDS
- 🚚 Live load arrivals
- ✅ Compliance met notifications
- ❌ Compliance missed alerts
- ⏰ Halfway and 30-minute warnings

## Troubleshooting Guide

### Problem: Duplicate Notifications
```cmd
# Diagnose the issue
enhanced_diagnostics.bat

# If multiple instances found, kill duplicates
taskkill /PID [OLD_PID] /F

# Or nuclear option
taskkill /F /IM python.exe
startup_scripts.bat start
```

### Problem: Scripts Not Starting
```cmd
# Check token validity
mwinit -o

# Check file locations
dir *.py

# Test Python
python --version

# View detailed logs
startup_scripts.bat logs
```

### Problem: No Notifications Received
```cmd
# Check script status
startup_scripts.bat status

# Check logs for errors
type logs\monitor.log

# Verify webhook URLs in scripts
```

### Problem: Token Expired
```cmd
# Simple fix - refresh token
mwinit -o

# Scripts will automatically restart with new token
```

## Expected Behavior

### Normal Operations
- **1 token_monitor.py** process
- **1 WorkingRate.py** process  
- **1 fluid_load_monitor.py** process
- **1 collect_arrivals.py** process
- **Total: 4 Python processes**

### Startup Notifications (One-time per session)
1. 🚀 Token Monitor Started
2. 🚀 WorkingRate Monitor Started  
3. 🚀 Fluid Load Monitor Started
4. 🚀 Collect Arrivals Monitor Started
5. ✅ All Scripts Started

### Token Refresh Process
1. You run `mwinit -o`
2. Token monitor detects new token
3. All scripts gracefully restart
4. 🔄 Token Refreshed notification sent
5. Normal monitoring resumes

## Advanced Configuration

### Webhook URLs
Update these in the respective script files:
- **Monitor alerts**: `token_monitor.py` → PSC2-webhook-monitor
- **Quarter reports**: `WorkingRate.py` → PSC2 Tracker  
- **UPH alerts**: `fluid_load_monitor.py` → Fluid Load Performance
- **LUCY alerts**: `collect_arrivals.py` → LUCY channel

### Timing Adjustments
- **Token check interval**: 30 seconds (in `token_monitor.py`)
- **Health check interval**: 60 seconds  
- **LUCY monitoring**: 60 seconds
- **UPH monitoring**: Hourly

## Security Notes
- Never commit AWS tokens or credentials
- Token files are stored in `%USERPROFILE%\.midway\cookie`
- Scripts use Kerberos authentication
- All webhooks use secure HTTPS endpoints

## Support
For issues or questions:
1. Check logs: `startup_scripts.bat logs`
2. Run diagnostics: `enhanced_diagnostics.bat`
3. Verify token: `mwinit -o`
4. Check system status: `startup_scripts.bat status`

---

**Version**: 1.0  
**Last Updated**: June 2025  
**Author**: pucpetey