#!/usr/bin/env python3
"""Run AS desktop user AFTER private transfer; never executes trusted originals.

--source-dir contains preserved PC haTemp.sh, monLight.sh, launch_temp_slider.sh
and waybar-module-pomodoro. Outputs key names/counts/booleans only. Existing
files must match bytes, owner and exact private mode; otherwise refuse. Does
not install shared helpers, change active configs, invoke HA, or start timer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys

POMODORO_SHA256 = 'bad8418350ae7fed9c3c5d79c31a430ec827f0fe5a6a8ada26abc99e2b1c3f51'
DEFAULTS = {'HA_URL':'https://ha.local.nexuszone.org',
            'HA_TEMP_URL':'http://192.168.20.100:8123',
            'HA_ENTITY_ID':'light.bedroom_monitor_light',
            'HA_TEMP_ENTITY_ID':'sensor.bedroom_air_sensor_temperature'}

class Refused(Exception): pass


def literal(text, key):
    # Restrict to literal quoted assignment; no eval, shell expansion or sourcing.
    matches = re.findall(r"(?m)^\s*(?:export\s+)?" + re.escape(key) + r"=([\"'])([^\"'\n]*)\1[ \t]*(?:#.*)?$", text)
    matches = [value for quote, value in matches]
    if len(matches)!=1 or not matches[0] or any(c in matches[0] for c in '$`\\\r\n'):
        raise Refused('source assignment missing, ambiguous or nonliteral')
    return matches[0]


def extract(source):
    tokens = []
    for name in ('haTemp.sh','monLight.sh','launch_temp_slider.sh'):
        text=(Path(source)/name).read_text()
        key='HA_TOKEN' if re.search(r'(?m)^\s*(?:export\s+)?HA_TOKEN=', text) else 'TOKEN'
        tokens.append(literal(text,key))
    if len(set(tokens))!=1: raise Refused('source token mismatch; nothing written')
    # Preserve both existing HA endpoints and entity workflow, not a new setup.
    config=dict(DEFAULTS,HA_TOKEN=tokens[0])
    for name, mapping in [('haTemp.sh',{'HA_URL':'HA_TEMP_URL','ENTITY_ID':'HA_TEMP_ENTITY_ID'}),
                          ('launch_temp_slider.sh',{'HA_URL':'HA_URL','HA_ENTITY_ID':'HA_ENTITY_ID'})]:
        text=(Path(source)/name).read_text()
        for old,new in mapping.items():
            if re.search(r'(?m)^\s*(?:export\s+)?'+old+'=',text): config[new]=literal(text,old)
    for key, value in config.items():
        if any(ord(c) < 32 for c in value): raise Refused('control character refused')
        if key.endswith('_URL') and not re.fullmatch(r'https?://[A-Za-z0-9.:-]+', value): raise Refused('invalid URL')
        if key.endswith('_ID') and not re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value): raise Refused('invalid entity')
    return config


def env_bytes(config):
    return ''.join(k+'='+json.dumps(v)+'\n' for k,v in sorted(config.items())).encode()


def check_existing(path, data, mode):
    path = Path(path)
    # Stow directory symlinks are permitted only to user-owned safe directories.
    parent = path.parent
    while not parent.exists() and not parent.is_symlink(): parent = parent.parent
    s = parent.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o022:
        raise Refused('destination parent ownership/mode invalid')
    if path.is_symlink(): raise Refused('destination symlink refused')
    if path.exists():
        s=path.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=mode or path.read_bytes()!=data:
            raise Refused('existing destination conflicts; preserve and resolve privately')
        return True
    return False


def install(path, data, mode):
    path=Path(path)
    if check_existing(path,data,mode): return
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    os.fchmod(fd, mode)  # New file only; never loosen an existing file.
    with os.fdopen(fd,'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    if path.read_bytes()!=data: raise Refused('private write verification failed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',required=True,type=Path)
    p.add_argument('--check-only',action='store_true')
    args=p.parse_args()
    try:
        config=extract(args.source_dir)
        binary=(args.source_dir/'waybar-module-pomodoro').read_bytes()
        if hashlib.sha256(binary).hexdigest()!=POMODORO_SHA256: raise Refused('pomodoro hash mismatch')
        if platform.machine()!='x86_64' or not Path('/lib64/ld-linux-x86-64.so.2').is_file(): raise Refused('pomodoro platform unsupported')
        targets=[(Path.home()/'.config/waybar/private.env',env_bytes(config),0o600),
                 (Path.home()/'.local/lib/waybar/waybar-module-pomodoro',binary,0o700)]
        # Check ALL conflicts before ANY writes, and preserve every original.
        for path,data,mode in targets: check_existing(path,data,mode)
        if not args.check_only:
            for path,data,mode in targets: install(path,data,mode)
        print(json.dumps({'keys':sorted(config),'source_token_count':3,'tokens_equal':True,
                          'pomodoro_hash_matches':True,'check_only':args.check_only,'ready':True}))
        return 0
    except Exception:
        print('Private Waybar preparation refused; check source, platform and destination conflicts privately',file=sys.stderr)
        return 1

if __name__=='__main__': sys.exit(main())
