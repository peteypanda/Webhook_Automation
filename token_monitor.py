import os
import time
import threading
import subprocess
import logging
from datetime import datetime
from pathlib import Path
import sys
import signal
import json
from typing import Dict, List, Optional, Callable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('token_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TokenMonitor:
    """Monitors midway token changes and manages script lifecycle"""
    
    def __init__(self):
        self.cookie_path = os.path.join(os.path.expanduser("~"), ".midway", "cookie")
        self.last_token_time = 0
        self.running_scripts: Dict[str, subprocess.Popen] = {}
        self.script_configs: List[Dict] = []
        self.shutdown_event = threading.Event()
        self.startup_notification_sent = False  # Track if startup notification was sent
        
        # PSC2-webhook-monitor channel URL for monitor/token alerts
        self.monitor_webhook_url = "https://hooks.slack.com/triggers/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"
        
    def get_token_modification_time(self) -> float:
        """Get the last modification time of the token file"""
        try:
            if os.path.exists(self.cookie_path):
                return os.path.getmtime(self.cookie_path)
        except Exception as e:
            logger.error(f"Error checking token file: {e}")
        return 0
    
    def is_token_valid(self) -> bool:
        """Check if the current token is still valid"""
        try:
            if not os.path.exists(self.cookie_path):
                return False
                
            with open(self.cookie_path, "rt") as f:
                cookie_lines = f.readlines()
            
            now = time.time()
            # Check if any cookie line is still valid (not expired)
            for line_num in range(4, len(cookie_lines)):
                try:
                    expiry_time = int(cookie_lines[line_num].split("\t")[4])
                    if expiry_time > now:
                        return True
                except (IndexError, ValueError):
                    continue
            return False
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            return False
    
    def add_script_config(self, name: str, script_path: str, args: List[str] = None, 
                         working_dir: str = None, env_vars: Dict[str, str] = None):
        """Add a script configuration to be managed"""
        config = {
            'name': name,
            'script_path': script_path,
            'args': args or [],
            'working_dir': working_dir or os.path.dirname(script_path),
            'env_vars': env_vars or {},
            'restart_count': 0,
            'last_restart': 0
        }
        self.script_configs.append(config)
        logger.info(f"Added script config: {name}")
    
    def start_script(self, config: Dict) -> Optional[subprocess.Popen]:
        """Start a single script"""
        try:
            env = os.environ.copy()
            env.update(config['env_vars'])
            
            cmd = [sys.executable, config['script_path']] + config['args']
            
            logger.info(f"Starting script: {config['name']}")
            logger.info(f"Command: {' '.join(cmd)}")
            logger.info(f"Working directory: {config['working_dir']}")
            
            process = subprocess.Popen(
                cmd,
                cwd=config['working_dir'],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,  # Add stdin for automated inputs
                universal_newlines=True,
                bufsize=1
            )
            
            config['restart_count'] += 1
            config['last_restart'] = time.time()
            
            # Send automated inputs for interactive scripts
            # Note: The automated versions don't need inputs, but keeping this for compatibility
            if config['name'] == 'CollectArrivals':
                # Automated version doesn't need input, but close stdin to prevent hanging
                try:
                    process.stdin.close()
                    logger.info(f"Closed stdin for automated {config['name']}")
                except Exception as e:
                    logger.warning(f"Failed to close stdin for {config['name']}: {e}")
            elif config['name'] == 'WorkingRate':
                # Automated version doesn't need input, but close stdin to prevent hanging
                try:
                    process.stdin.close()
                    logger.info(f"Closed stdin for automated {config['name']}")
                except Exception as e:
                    logger.warning(f"Failed to close stdin for {config['name']}: {e}")
            elif config['name'] == 'FluidLoadMonitor':
                # Automated version doesn't need input, but close stdin to prevent hanging
                try:
                    process.stdin.close()
                    logger.info(f"Closed stdin for automated {config['name']}")
                except Exception as e:
                    logger.warning(f"Failed to close stdin for {config['name']}: {e}")
            
            # Start threads to handle output
            threading.Thread(
                target=self._handle_output,
                args=(process.stdout, config['name'], 'STDOUT'),
                daemon=True
            ).start()
            
            threading.Thread(
                target=self._handle_output,
                args=(process.stderr, config['name'], 'STDERR'),
                daemon=True
            ).start()
            
            return process
            
        except Exception as e:
            logger.error(f"Failed to start script {config['name']}: {e}")
            return None
    
    def _handle_output(self, pipe, script_name: str, stream_type: str):
        """Handle script output in separate thread"""
        try:
            for line in iter(pipe.readline, ''):
                if line.strip():
                    logger.info(f"[{script_name}] {stream_type}: {line.strip()}")
        except Exception as e:
            logger.error(f"Error handling output for {script_name}: {e}")
    
    def stop_script(self, name: str):
        """Stop a specific script"""
        if name in self.running_scripts:
            process = self.running_scripts[name]
            try:
                logger.info(f"Stopping script: {name}")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Script {name} didn't terminate gracefully, killing...")
                    process.kill()
                    process.wait()
                
                del self.running_scripts[name]
                logger.info(f"Script {name} stopped")
                
            except Exception as e:
                logger.error(f"Error stopping script {name}: {e}")
    
    def stop_all_scripts(self):
        """Stop all running scripts"""
        logger.info("Stopping all scripts...")
        for name in list(self.running_scripts.keys()):
            self.stop_script(name)
    
    def start_all_scripts(self):
        """Start all configured scripts"""
        logger.info("Starting all scripts...")
        
        # Send startup notification only once per session
        if not self.startup_notification_sent:
            self.send_startup_notification()
            self.startup_notification_sent = True
        
        for config in self.script_configs:
            if config['name'] not in self.running_scripts:
                process = self.start_script(config)
                if process:
                    self.running_scripts[config['name']] = process
        
        # Send running status notification only if we have scripts
        if self.running_scripts:
            self.send_status_notification("All Scripts Started", "All configured scripts are now running and monitoring")
    
    def send_startup_notification(self):
        """Send a notification that the monitor is starting"""
        try:
            script_list = "\n".join([f"• {config['name']}: {config.get('description', 'No description')}" for config in self.script_configs])
            
            payload = {
                "Title": "🚀 Token Monitor Started",
                "metrics": f"**Configured Scripts:**\n{script_list}\n\n**Status:** All systems operational\n**Token Status:** Valid\n**Auto-restart:** Enabled",
                "footer": f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Token Monitor v1.0"
            }
            
            import requests
            response = requests.post(self.monitor_webhook_url, json=payload)
            response.raise_for_status()
            logger.info("Startup notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")
    
    def send_status_notification(self, title: str, message: str):
        """Send a status notification"""
        try:
            running_scripts = list(self.running_scripts.keys())
            script_status = "\n".join([f"✅ {name}" for name in running_scripts])
            if not script_status:
                script_status = "❌ No scripts currently running"
            
            payload = {
                "Title": title,
                "metrics": f"{message}\n\n**Currently Running:**\n{script_status}",
                "footer": f"Token Monitor | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            import requests
            response = requests.post(self.monitor_webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Status notification sent: {title}")
        except Exception as e:
            logger.error(f"Failed to send status notification: {e}")
    
    def send_script_startup_notification(self, script_name: str, description: str):
        """Send individual script startup notification"""
        try:
            payload = {
                "Title": f"🚀 {script_name} Monitor Started",
                "metrics": f"Auto-started by token monitor\n\n{description}",
                "footer": f"Token Monitor | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            import requests
            response = requests.post(self.monitor_webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"Script startup notification sent: {script_name}")
        except Exception as e:
            logger.error(f"Failed to send script startup notification: {e}")
    
    def restart_all_scripts(self):
        """Restart all scripts (usually after token refresh)"""
        logger.info("Restarting all scripts due to token refresh...")
        self.stop_all_scripts()
        time.sleep(2)  # Give scripts time to fully stop
        self.start_all_scripts()
        
        # Send token refresh notification
        self.send_status_notification("🔄 Token Refreshed", "New midway token detected! All scripts have been restarted with fresh authentication.")
    
    def check_script_health(self):
        """Check if scripts are still running and restart if needed"""
        for config in self.script_configs:
            name = config['name']
            if name in self.running_scripts:
                process = self.running_scripts[name]
                if process.poll() is not None:
                    logger.warning(f"Script {name} has stopped unexpectedly")
                    del self.running_scripts[name]
                    
                    # Restart if token is still valid
                    if self.is_token_valid():
                        logger.info(f"Restarting script {name}")
                        new_process = self.start_script(config)
                        if new_process:
                            self.running_scripts[name] = new_process
                    else:
                        logger.warning(f"Not restarting {name} - token invalid")
    
    def monitor_token(self):
        """Main monitoring loop"""
        logger.info("Starting token monitoring...")
        
        # Initial token check
        self.last_token_time = self.get_token_modification_time()
        
        # Start scripts if token is valid
        if self.is_token_valid():
            self.start_all_scripts()
        else:
            logger.warning("Token is invalid or missing. Please run 'mwinit -o' to authenticate.")
        
        while not self.shutdown_event.is_set():
            try:
                current_token_time = self.get_token_modification_time()
                
                # Check if token file has been updated
                if current_token_time > self.last_token_time:
                    logger.info("New token detected!")
                    self.last_token_time = current_token_time
                    
                    # Restart all scripts with new token
                    self.restart_all_scripts()
                
                # Check script health
                self.check_script_health()
                
                # Check token validity
                if not self.is_token_valid() and self.running_scripts:
                    logger.warning("Token has expired. Stopping all scripts.")
                    self.stop_all_scripts()
                
                # Wait before next check
                self.shutdown_event.wait(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self.shutdown_event.wait(60)  # Wait longer on error
    
    def start(self):
        """Start the token monitor"""
        try:
            self.monitor_token()
        except KeyboardInterrupt:
            logger.info("Shutting down due to keyboard interrupt")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the monitor and all scripts"""
        logger.info("Shutting down token monitor...")
        self.shutdown_event.set()
        self.stop_all_scripts()
        logger.info("Token monitor shutdown complete")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    global monitor
    if monitor:
        monitor.shutdown()
    sys.exit(0)


def main():
    global monitor
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create monitor instance
    monitor = TokenMonitor()
    
    # Add your script configurations here
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add WorkingRate.py (automated version)
    working_rate_path = os.path.join(script_dir, "WorkingRate.py")
    if os.path.exists(working_rate_path):
        monitor.add_script_config(
            name="WorkingRate",
            script_path=working_rate_path,
            working_dir=script_dir
        )
        # Add description for better notifications
        monitor.script_configs[-1]['description'] = "Problem Solve Rates monitoring (quarters)"
    else:
        logger.warning(f"WorkingRate.py not found at {working_rate_path}")
    
    # Add collect_arrivals.py (automated version) 
    collect_arrivals_path = os.path.join(script_dir, "collect_arrivals.py")
    if os.path.exists(collect_arrivals_path):
        monitor.add_script_config(
            name="CollectArrivals",
            script_path=collect_arrivals_path,
            working_dir=script_dir
        )
        # Add description for better notifications
        monitor.script_configs[-1]['description'] = "LUCY compliance monitoring (live loads)"
    else:
        logger.warning(f"collect_arrivals.py not found at {collect_arrivals_path}")
    
    # Add fluid_load_monitor.py if it exists
    fluid_monitor_path = os.path.join(script_dir, "fluid_load_monitor.py")
    if os.path.exists(fluid_monitor_path):
        monitor.add_script_config(
            name="FluidLoadMonitor",
            script_path=fluid_monitor_path,
            working_dir=script_dir
        )
        # Add description for better notifications
        monitor.script_configs[-1]['description'] = "Fluid Load UPH monitoring (hourly alerts)"
    else:
        logger.warning(f"fluid_load_monitor.py not found at {fluid_monitor_path}")
    
    # Add more scripts as needed
    # monitor.add_script_config(
    #     name="AnotherScript",
    #     script_path="/path/to/another_script.py",
    #     args=["--arg1", "value1"],
    #     env_vars={"CUSTOM_VAR": "value"}
    # )
    
    logger.info("Token Monitor started. Press Ctrl+C to stop.")
    logger.info("To refresh tokens, run 'mwinit -o' in another terminal.")
    
    # Start monitoring
    monitor.start()


if __name__ == "__main__":
    monitor = None
    main()