#!/usr/bin/env python3
"""Private HA environment loader and bounded HTTP; never log credentials/responses.

private.env is inert KEY="JSON string" data, NOT a shell script. No sourcing/eval.
"""
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.request

KEYS = {'HA_TOKEN', 'HA_URL', 'HA_TEMP_URL', 'HA_ENTITY_ID', 'HA_TEMP_ENTITY_ID'}
DEFAULTS = {'HA_URL': 'https://ha.local.nexuszone.org',
            'HA_TEMP_URL': 'http://192.168.20.100:8123',
            'HA_ENTITY_ID': 'light.bedroom_monitor_light',
            'HA_TEMP_ENTITY_ID': 'sensor.bedroom_air_sensor_temperature'}

class Unavailable(Exception):
    pass


def load_env(path=None):
    path = Path(path) if path is not None else Path.home()/'.config/waybar/private.env'
    result = dict(DEFAULTS)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r') as stream:
            s = os.fstat(stream.fileno())
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_size > 16384:
                raise Unavailable('private environment ownership/mode invalid')
            seen = set()
            for line in stream:
                if not line.strip() or line.startswith('#'): continue
                key, sep, value = line.strip().partition('=')
                if not sep or key not in KEYS or key in seen: raise Unavailable('private environment invalid')
                seen.add(key)
                value = json.loads(value)
                if not isinstance(value, str) or not value or any(ord(c)<32 for c in value):
                    raise Unavailable('private environment invalid')
                result[key] = value
    except (OSError, ValueError, TypeError):
        raise Unavailable('private environment missing or invalid') from None
    if not result.get('HA_TOKEN'): raise Unavailable('private HA_TOKEN missing')
    for k in ('HA_URL','HA_TEMP_URL'):
        if not re.fullmatch(r'https?://[A-Za-z0-9.:-]+', result[k]): raise Unavailable('HA URL invalid')
    for k in ('HA_ENTITY_ID','HA_TEMP_ENTITY_ID'):
        if not re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+',result[k]): raise Unavailable('HA entity invalid')
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Unavailable('HA redirect refused')


def request(config, path, data=None, temp=False):
    base = config['HA_TEMP_URL' if temp else 'HA_URL']
    req = urllib.request.Request(base + '/api/' + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Authorization': 'Bearer ' + config['HA_TOKEN'], 'Content-Type': 'application/json'})
    # Keep LAN requests direct; never hand Authorization to environment proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=5) as response:
        raw = response.read(65537)
        if len(raw)>65536: raise Unavailable('HA response too large')
        return json.loads(raw)


def unavailable():
    print(json.dumps({'text':'N/A','class':'unavailable','tooltip':'Home Assistant unavailable: check private.env / connectivity'}))


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    try:
        config = load_env()
        action = args[0] if args else ''
        if action == 'temp':
            state = request(config, 'states/'+config['HA_TEMP_ENTITY_ID'], temp=True)['state']
            if state in ('unknown','unavailable'): raise Unavailable()
            print(json.dumps({'text': str(float(state))}))
        elif action == 'light':
            entity = config['HA_ENTITY_ID']
            if args[1:] == ['--toggle']:
                request(config, 'services/light/toggle', {'entity_id':entity})
            elif args[1:] in (['--brightness','up'], ['--brightness','down']):
                current = request(config,'states/'+entity).get('attributes',{}).get('brightness',0)
                delta = 25 if args[-1]=='up' else -25
                request(config, 'services/light/turn_on', {'entity_id':entity,'brightness':max(1,min(254,int(current)+delta))})
            elif args[1:]: raise Unavailable()
            state = request(config,'states/'+entity)
            if state['state'] not in ('on','off'): raise Unavailable()
            on = state['state']=='on'
            tooltip = 'Light is OFF'
            if on: tooltip='Light is ON (%d%%)' % (int(state.get('attributes',{}).get('brightness',0))*100//254)
            print(json.dumps({'text':'󰌵' if on else '󰌶','tooltip':tooltip}))
        elif action == 'slider':
            os.environ.update(config)
            # Credential values stay out of argv and stdout; preserve existing UI.
            os.execv(sys.executable,[sys.executable,str(Path(__file__).resolve().with_name('vexa-light-temp-slider.py')),'--pos-x','810','--pos-y','45'])
        elif action == 'open':
            os.execvp('xdg-open',['xdg-open',config['HA_URL']])
        else: raise Unavailable()
        return 0
    except Exception:
        # Never include exception text (HTTP bodies/headers may contain secrets).
        if args in (['temp'], ['light']):
            unavailable()
            return 0
        print('Waybar HA action unavailable; check private environment and dependencies',file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
