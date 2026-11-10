#!/usr/bin/env python3
"""Read-only laptop dependency preflight. Never contacts HA or starts any UI/timer."""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import stat
import subprocess
import sys

SHA256='bad8418350ae7fed9c3c5d79c31a430ec827f0fe5a6a8ada26abc99e2b1c3f51'
COMMANDS=['python3','xdg-open','swaync-client','which','kitty','nmtui','htop','pavucontrol','pkill']
HELPERS=['vexa-light-temp-slider.py','ha_runtime.py','pomodoro_runtime.py','peripheral_battery.py','jbl_reader.py']

def check(config):
    config=Path(config)
    commands={c:shutil.which(c) is not None for c in COMMANDS}
    helpers={name:(config/'scripts'/name).is_file() for name in HELPERS}
    executable={name:os.access(config/'scripts'/name,os.X_OK) for name in HELPERS if name.endswith('.sh')}
    env=config/'private.env'
    env_ok=False
    try:
        if not env.is_symlink():
            s=env.stat()
            env_ok=stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600
    except OSError: pass
    env_valid=False
    if env_ok and helpers["ha_runtime.py"]:
        try:
            sys.dont_write_bytecode=True
            spec=importlib.util.spec_from_file_location("ha_preflight",config/"scripts/ha_runtime.py")
            m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            m.load_env(env)  # Inert parse only: no network, values never emitted.
            env_valid=True
        except Exception: pass
    binary=Path.home()/'.local/lib/waybar/waybar-module-pomodoro'
    binary_ok=False
    try:
        s=binary.stat()
        binary_ok=not binary.is_symlink() and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700 and hashlib.sha256(binary.read_bytes()).hexdigest()==SHA256
    except OSError: pass
    dependencies_ok=False
    if binary_ok and platform.machine()=='x86_64' and shutil.which('ldd'):
        try:
            deps=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,timeout=5)
            dependencies_ok=deps.returncode==0 and 'not found' not in deps.stdout+deps.stderr
        except (OSError, subprocess.TimeoutExpired): pass
    gtk=subprocess.run([sys.executable,'-c',"import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk"],capture_output=True).returncode==0
    result={'commands':commands,'helpers':helpers,'executable_helpers':executable,'private_env_owner_mode_ok':env_ok,'private_env_valid':env_valid,'pomodoro_private_hash_mode_ok':binary_ok,'pomodoro_dynamic_dependencies_ok':dependencies_ok,'python_gtk3_import':gtk,'ha_connectivity':'not-tested','live_rendering':'not-tested'}
    result['ready']=all(commands.values()) and all(helpers.values()) and all(executable.values()) and env_valid and binary_ok and dependencies_ok and gtk
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=Path.home()/'.config/waybar')
    result=check(p.parse_args().config)
    print(json.dumps(result,indent=2))
    sys.exit(0 if result['ready'] else 1)
