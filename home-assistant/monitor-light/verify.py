#!/usr/bin/env python3
"""Controlled real MQTT/HA integration test. NEVER suspends/reboots the PC.
Temporarily toggles only the monitor light, then restores original on/off.
"""
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--env-file',required=True);p.add_argument('--ssh',default='vexa@192.168.0.90');a=p.parse_args()
c={}
for l in Path(a.env_file).read_text().splitlines():
    if '=' in l and not l.startswith('#'):
        k,v=l.split('=',1);c[k.strip()]=v.strip().strip('\"\'')
def api(path,data=None):
    q=urllib.request.Request(c['HASS_URL'].rstrip('/')+'/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+c['HASS_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(q,timeout=20) as r:
        b=r.read();return json.loads(b) if b else None
def ssh(cmd):
    return subprocess.check_output(['ssh','-o','BatchMode=yes',a.ssh,cmd],text=True,timeout=20).strip()
def pub(state,event,clock_offset=0):
    print(ssh('sudo -n python3 /usr/local/lib/pc-status/verify_mqtt.py '+state+' '+event+' --clock-offset '+str(clock_offset)),flush=True)
def state():return api('states/light.bedroom_monitor_light')['state']
def wait(target,timeout=4):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if state()==target:return
        time.sleep(.2)
    raise AssertionError('Expected light '+target+', found '+state())
def light(action):api('services/light/turn_'+action,{'entity_id':'light.bedroom_monitor_light'})
def check(name,ok):
    assert ok,name
    print('PASS',name,flush=True)
original=state()
try:
    light('on');wait('on')
    t=time.monotonic();pub('asleep','sleep',clock_offset=1);time.sleep(5)
    check('sleep does not turn off before 10 seconds',state()=='on')
    wait('off',10);elapsed=time.monotonic()-t
    check('sleep turns off after 10 seconds',9.5<=elapsed<15)
    print('Measured off seconds from publish invocation:',round(elapsed,2),flush=True)
    t=time.monotonic();pub('awake','resume');wait('on');print('Measured resume-on seconds:',round(time.monotonic()-t,2),flush=True)
    pub('asleep','sleep');time.sleep(3);pub('awake','resume');time.sleep(11)
    check('wake cancels pending delayed off',state()=='on')
    # Last-will disconnect/reconnect cannot turn an ON light off.
    ssh('sudo -n systemctl kill --kill-whom=main --signal=SIGKILL pc-status.service')
    time.sleep(12);check('unexpected MQTT publisher loss does not turn light off',state()=='on')
    light('off');wait('off');pub('awake','state-only');time.sleep(2)
    check('retained awake refresh preserves manual off',state()=='off')
    pub('awake','resume',clock_offset=-60);time.sleep(2)
    check('stale wake is rejected',state()=='off')
    pub('awake','resume',clock_offset=60);time.sleep(2)
    check('far-future wake is rejected',state()=='off')
    last=api('states/input_text.monitor_light_last_lifecycle_event')['state']
    api('services/mqtt/publish',{'topic':'archyper/pc-status/event','payload':json.dumps({'event':'resume','ts':time.time(),'id':last}),'qos':1,'retain':False})
    time.sleep(2);check('duplicate QoS wake preserves manual off',state()=='off')
    ssh('sudo -n systemctl restart pc-status.service');time.sleep(3)
    check('service restart/reconnect preserves manual off',state()=='off')
    api('services/automation/reload',{});time.sleep(2)
    check('HA automation resubscription preserves manual off',state()=='off')
    snapshot=json.loads(ssh('sudo -n python3 /usr/local/lib/pc-status/mqtt_snapshot.py'))
    check('retained state but no retained events',any(m['topic'].endswith('/state') and m['retained'] for m in snapshot) and not any(m['topic'].endswith('/event') for m in snapshot))
    print('Broker snapshot:',json.dumps(snapshot),flush=True)

    # Template endpoint returns text, unlike other API endpoints.
    q=urllib.request.Request(c['HASS_URL'].rstrip('/')+'/api/template',data=json.dumps({'template':"{{ not is_state('binary_sensor.archyper_pc_awake', 'on') }}"}).encode(),headers={'Authorization':'Bearer '+c['HASS_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(q,timeout=20) as r:guard=r.read().decode().strip()
    check('morning delayed-off guard blocks while PC awake',guard=='False')
    light('on');wait('on')
    t=time.monotonic();pub('shutdown','shutdown');time.sleep(5);check('shutdown waits 10 seconds',state()=='on')
    wait('off',10)
    elapsed=time.monotonic()-t;check('shutdown intent turns off after delay',9.5<=elapsed<15)
    pub('awake','boot');wait('on');check('explicit boot turns light on',state()=='on')
    print('All controlled integration checks passed. No real suspend/shutdown/reboot performed.',flush=True)
finally:
    pub('awake','state-only')
    light(original if original in ['on','off'] else 'off')
    wait(original if original in ['on','off'] else 'off')
    print('Restored real PC retained state awake and original light state:',original,flush=True)
