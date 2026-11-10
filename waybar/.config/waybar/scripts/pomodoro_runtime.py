#!/usr/bin/env python3
"""Delegate to preserved private pomodoro 0.3.0; never replace timer semantics."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SHA256='bad8418350ae7fed9c3c5d79c31a430ec827f0fe5a6a8ada26abc99e2b1c3f51'

def main():
    path=Path.home()/'.local/lib/waybar/waybar-module-pomodoro'
    try:
        if path.is_symlink(): raise ValueError()
        s=path.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700: raise ValueError()
        if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256: raise ValueError()
        os.execv(str(path),[str(path)]+sys.argv[1:])
    except (OSError, ValueError):
        if sys.argv[1:] in (['toggle'],['reset']):
            print('Waybar pomodoro private runtime unavailable',file=sys.stderr)
            return 1
        print(json.dumps({'text':'N/A','class':'unavailable','tooltip':'Pomodoro private runtime missing or unverified'}))
        return 0

if __name__=='__main__': sys.exit(main())
