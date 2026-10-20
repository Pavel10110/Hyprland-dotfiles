#!/usr/bin/env python3
"""Deploy versioned HA automation configs using HA's authenticated config API.
Use --env-file for a HASS_URL/HASS_TOKEN file; secrets never go in git.
Requires requests? No: Python stdlib only. YAML is documentation; JSON exact API payload.
"""
import argparse
import json
from pathlib import Path
import urllib.request
import urllib.error

p=argparse.ArgumentParser();p.add_argument('--env-file',required=True);p.add_argument('--backup-dir',required=True);args=p.parse_args()
c={}
for l in Path(args.env_file).read_text().splitlines():
    if '=' in l and not l.startswith('#'):
        k,v=l.split('=',1);c[k.strip()]=v.strip().strip('\"\'')
def api(path,data=None,method=None):
    req=urllib.request.Request(c['HASS_URL'].rstrip('/')+'/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+c['HASS_TOKEN'],'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=30) as r:
        b=r.read();return json.loads(b) if b else None
backup=Path(args.backup_dir);backup.mkdir(parents=True,exist_ok=True)
def ws_cmd(command):
    import websocket
    w=websocket.create_connection(c['HASS_URL'].rstrip('/').replace('http:', 'ws:').replace('https:', 'wss:')+'/api/websocket',timeout=15)
    try:
        w.recv();w.send(json.dumps({'type':'auth','access_token':c['HASS_TOKEN']}))
        assert json.loads(w.recv())['type']=='auth_ok'
        w.send(json.dumps(dict(command,id=1)));result=json.loads(w.recv())
        assert result.get('success'), 'Helper/registry API failed'
        return result['result']
    finally:
        w.close()
try:
    api('states/input_text.monitor_light_last_lifecycle_event')
except urllib.error.HTTPError as e:
    if e.code!=404: raise
    ws_cmd({'type':'input_text/create','name':'Monitor light last lifecycle event','min':0,'max':255,'mode':'text'})
try:
    api('states/binary_sensor.archyper_pc_awake')
except urllib.error.HTTPError as e:
    if e.code!=404: raise
    ws_cmd({'type':'config/entity_registry/update','entity_id':'binary_sensor.archyper_lifecycle_archyper_pc_awake','new_entity_id':'binary_sensor.archyper_pc_awake'})
for ident in ['1758390564573','1758390707714','1761816974036']:
    target=backup/(ident+'.json')
    if not target.exists():
        try: target.write_text(json.dumps(api('config/automation/config/'+ident),indent=2)+'\n')
        except urllib.error.HTTPError as e:
            if e.code!=404: raise
root=Path(__file__).resolve().parent
for name in ['lifecycle','morning']:
    cfg=json.loads((root/(name+'.json')).read_text())
    result=api('config/automation/config/'+cfg['id'],cfg,'POST')
    print('Applied',cfg['id'],result)
api('services/automation/reload',{})
entities={s['attributes'].get('id'):s for s in api('states') if s['entity_id'].startswith('automation.')}
assert entities['archyper_monitor_lifecycle_v2']['state']=='on', 'New automation not enabled: leaving old configs untouched'
assert api('states/binary_sensor.archyper_pc_awake')['state'] in ['on','off']
for ident in ['1758390564573','1758390707714']:
    try: print('Retired',ident,api('config/automation/config/'+ident,method='DELETE'))
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
api('services/automation/reload',{})
print('Deployment complete; scoped backups:',backup)
