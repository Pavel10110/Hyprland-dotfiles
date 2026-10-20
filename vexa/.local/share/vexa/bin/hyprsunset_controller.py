#!/usr/bin/env python3
import datetime
import os
import signal
import subprocess
import time

TEMPERATURE_NIGHT = 4200
START_TIME = datetime.time(21, 30)
END_TIME = datetime.time(7, 0)
enabled = False
process = None

def should_enable_now() -> bool:
    current = datetime.datetime.now().time()
    if START_TIME > END_TIME:
        return START_TIME <= current or current < END_TIME
    return START_TIME <= current < END_TIME

def cleanup(*_args):
    global process
    if process and process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    raise SystemExit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

while True:
    should_enable = should_enable_now()
    if should_enable and not enabled:
        process = subprocess.Popen(['hyprsunset', '-t', str(TEMPERATURE_NIGHT)], preexec_fn=os.setsid)
        enabled = True
        print(f'Enabled hyprsunset at {datetime.datetime.now()}', flush=True)
    elif not should_enable and enabled:
        if process and process.poll() is None:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        enabled = False
        print(f'Disabled hyprsunset at {datetime.datetime.now()}', flush=True)
    time.sleep(60)
