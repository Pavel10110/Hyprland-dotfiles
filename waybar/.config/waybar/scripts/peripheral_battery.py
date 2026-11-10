#!/usr/bin/env python3
"""One-shot Waybar telemetry. Never pair, connect, write reports or infer charging.

JBL 0x49 decoding reuses the existing jbl-quantum-battery.py reader.
The separate worker bounds slow ioctl/BlueZ calls; Waybar polls every 30s.
"""
import argparse
import glob
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MAC = 'C0:E5:F0:EB:9C:72'


def render(kind, state, percent=None, detail=''):
    name, icon = ('Corne', '󰌌') if kind == 'keyboard' else ('JBL Quantum 910', '󰋋')
    valid = isinstance(percent, int) and 0 <= percent <= 100 and state in ('known', 'charging')
    if not valid:
        percent = None
        if state in ('known', 'charging'):
            state = 'unknown'
    classes = [state]
    if percent is not None:
        classes.append('critical' if percent <= 15 else 'warning' if percent <= 30 else 'normal')
    result = {'text': f'{icon} {str(percent) + "%" if percent is not None else "--"}',
              'tooltip': html.escape(f'{name}: {state}\n{detail}'), 'class': classes, 'alt': state}
    if percent is not None:
        result['percentage'] = percent
    return result


def keyboard_from_info(info, usb):
    connected = re.search(r'^\s*Connected:\s*(yes|no)\s*$', info, re.M)
    match = re.search(r'Battery Percentage:.*\((\d+)\)', info)
    if connected and connected[1] == 'yes':
        percent = int(match[1]) if match else None
        return render('keyboard', 'known' if percent is not None else 'unknown', percent,
                      'Host-visible central half only; charging and other half unknown')
    if usb:
        return render('keyboard', 'unknown', detail='USB Corne present; BLE battery unavailable; no USB battery exposed')
    return render('keyboard', 'disconnected' if connected else 'unknown',
                  detail='BLE disconnected; cached battery ignored' if connected else 'BlueZ connection state unavailable')


def keyboard():
    usb = False
    for entry in glob.glob('/sys/class/hidraw/hidraw*/device/uevent'):
        try:
            data = Path(entry).read_text()
            usb |= 'HID_ID=0003:00001D50:0000615E' in data and 'Corne' in data
        except OSError:
            pass
    try:
        info = subprocess.run(['bluetoothctl', 'info', MAC], capture_output=True, text=True,
                              timeout=2, env={**os.environ, 'LC_ALL': 'C'}).stdout
    except (OSError, subprocess.TimeoutExpired):
        info = ''
    return keyboard_from_info(info, usb)


def jbl():
    import jbl_reader
    device = jbl_reader.find_hidraw()
    if device is None:
        return render('jbl', 'disconnected', detail='Quantum 910 USB dongle absent')
    try:
        percent = jbl_reader.read_battery(device)
        return render('jbl', 'known', percent,
                      f'Dongle feature 0x49: {percent}%; {device}\nRadio link and charging state unknown')
    except (OSError, ValueError) as exc:
        return render('jbl', 'unknown', detail=f'Battery read unavailable: {exc}')


def bounded(kind):
    try:
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), kind, '--worker'],
                              capture_output=True, text=True, timeout=4)
        if proc.returncode:
            raise ValueError('telemetry worker failed')
        return json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return render(kind, 'unknown', detail='Telemetry unavailable or timed out (4 second deadline)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['keyboard', 'jbl'])
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    result = (keyboard() if args.kind == 'keyboard' else jbl()) if args.worker else bounded(args.kind)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
