#!/usr/bin/env python3
import argparse
import fcntl
import glob
import json
import os
import re
import sys

VENDOR = "0ecb"
PRODUCT = "2088"
NAME_RE = re.compile(r"JBL Quantum 910 Wireless", re.I)
REPORT_ID = 0x49

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(dir_, type_, nr, size):
    return (dir_ << _IOC_DIRSHIFT) | (type_ << _IOC_TYPESHIFT) | (nr << _IOC_NRSHIFT) | (size << _IOC_SIZESHIFT)


def hidiocgfeature(length: int) -> int:
    return _IOC(_IOC_READ | _IOC_WRITE, ord("H"), 0x07, length)


def find_hidraw() -> str | None:
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        try:
            data = {}
            with open(uevent, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "=" in line:
                        k, v = line.rstrip("\n").split("=", 1)
                        data[k] = v
        except OSError:
            continue
        hid_id = data.get("HID_ID", "")
        hid_name = data.get("HID_NAME", "")
        if VENDOR in hid_id.lower() and PRODUCT in hid_id.lower() and NAME_RE.search(hid_name):
            hidraw_name = os.path.basename(os.path.dirname(os.path.dirname(uevent)))
            return f"/dev/{hidraw_name}"
    return None


def read_battery(device: str) -> int:
    buf = bytearray([REPORT_ID, 0])
    with open(device, "rb+", buffering=0) as fh:
        fcntl.ioctl(fh.fileno(), hidiocgfeature(len(buf)), buf, True)
    value = int(buf[1])
    if not 0 <= value <= 100:
        raise ValueError(f"battery value out of range: {value}")
    return value


def to_waybar_json(percent: int, device: str) -> str:
    cls = "normal"
    if percent <= 15:
        cls = "critical"
    elif percent <= 30:
        cls = "warning"
    payload = {
        "text": f"󰋋 {percent}%",
        "tooltip": f"JBL Quantum 910 battery: {percent}%\n{device}",
        "class": cls,
        "alt": "connected",
    }
    return json.dumps(payload, ensure_ascii=False)


def unavailable(message: str, waybar: bool) -> int:
    if waybar:
        print(json.dumps({
            "text": "󰋎 --",
            "tooltip": f"JBL Quantum 910 battery unavailable\n{message}",
            "class": "unavailable",
            "alt": "unavailable",
        }, ensure_ascii=False))
        return 0
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--waybar", action="store_true", help="emit Waybar JSON")
    parser.add_argument("--device", help="override hidraw device path")
    args = parser.parse_args()

    device = args.device or find_hidraw()
    if not device:
        return unavailable("device not found", args.waybar)
    try:
        percent = read_battery(device)
    except Exception as exc:
        return unavailable(str(exc), args.waybar)

    if args.waybar:
        print(to_waybar_json(percent, device))
    else:
        print(percent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
