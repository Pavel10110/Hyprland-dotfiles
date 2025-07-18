#!/usr/bin/env python3
import datetime
import signal
import time
import subprocess
import os
import sys

def handle_exit(signum, frame):
    print(f"{datetime.datetime.now()} - Received shutdown signal")
    if 'process' in globals() and globals()['process']:
        globals()['process'].terminate()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)
# Configuration
temperature_night = 4200
enabled = False
process = None

def setup_hyprland_env():
    """Ensure Hyprland environment variables are set"""
    if not os.getenv('HYPRLAND_INSTANCE_SIGNATURE'):
        hyprland_socket = f"/tmp/hypr/{os.getenv('USER')}/.hyprland.sock"
        if os.path.exists(hyprland_socket):
            os.environ['HYPRLAND_INSTANCE_SIGNATURE'] = hyprland_socket
        else:
            print("Warning: Hyprland socket not found", file=sys.stderr)

def check_time():
    """Check if we should be in night mode"""
    current_time = datetime.datetime.now().time()
    start_time = datetime.time(20, 00)  # 9:30 PM
    end_time = datetime.time(7, 0)      # 7:00 AM
    
    if start_time > end_time:  # Crosses midnight
        return start_time <= current_time or current_time < end_time
    else:
        return start_time <= current_time < end_time

def main():
    global process, enabled
    
    setup_hyprland_env()
    print(f"{datetime.datetime.now()} - Starting hyprsunset controller")
    
    while True:
        should_enable = check_time()
        
        if should_enable and not enabled:
            print(f"{datetime.datetime.now()} - Enabling night mode")
            process = subprocess.Popen(
                ['hyprsunset', '-t', str(temperature_night)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            enabled = True
            
        elif not should_enable and enabled:
            print(f"{datetime.datetime.now()} - Disabling night mode")
            if process and process.poll() is None:
                process.terminate()
            enabled = False
            
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"{datetime.datetime.now()} - Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
