#!/usr/bin/env python3
import datetime
import signal
import time
import subprocess
import os

temperature_night = 4200
enabled = False
process = None

def check_time():
    current_time = datetime.datetime.now().time()
    start_time = datetime.time(20, 0)  # 9:30 PM
    end_time = datetime.time(7, 0)     # 7:00 AM
    
    # Handle overnight period (9:30 PM to 7:00 AM)
    if start_time > end_time:  # Crosses midnight
        return start_time <= current_time or current_time < end_time
    else:
        return start_time <= current_time < end_time

def cleanup(signum, frame):
    if process and process.poll() is None:
        process.terminate()
    exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

while True:
    should_enable = check_time()
    
    if should_enable and not enabled:
        # Start hyprsunset if not running
        process = subprocess.Popen(
            ['hyprsunset', '-t', str(temperature_night)],
            preexec_fn=os.setsid
        )
        enabled = True
        print(f"Enabled hyprsunset at {datetime.datetime.now()}")
        
    elif not should_enable and enabled:
        # Stop hyprsunset if running
        if process and process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        enabled = False
        print(f"Disabled hyprsunset at {datetime.datetime.now()}")
    
    time.sleep(60)  # Check every minute (more efficient than 5s)
