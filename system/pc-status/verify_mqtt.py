#!/usr/bin/python3
"""Controlled MQTT test publisher: does NOT suspend/shutdown the PC.
Run sudo python3 verify_mqtt.py {awake,asleep,shutdown} {boot,resume,sleep,shutdown,state-only}
Uses root-only /etc/pc-status/mqtt.env. Never prints credentials.
"""
import argparse
import json
import shlex
import time
import uuid
from pathlib import Path
import paho.mqtt.client as mqtt
p=argparse.ArgumentParser();p.add_argument('state',choices=['awake','asleep','shutdown']);p.add_argument('event',choices=['boot','resume','sleep','shutdown','state-only']);p.add_argument('--clock-offset',type=float,default=0);args=p.parse_args()
c={}
for line in Path('/etc/pc-status/mqtt.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        k,v=line.split('=',1);parts=shlex.split(v);c[k.strip()]=parts[0] if parts else ''
client=mqtt.Client('archyper-pc-status-controlled-test')
client.username_pw_set(c['MQTT_USER'],c['MQTT_PASS'])
client.connect(c['MQTT_HOST'],int(c.get('MQTT_PORT',1883)),20);client.loop_start()
def pub(topic,payload,retain=False):
    msg=client.publish('archyper/pc-status/'+topic,payload,qos=1,retain=retain);msg.wait_for_publish(timeout=5)
    assert msg.is_published(), 'Broker acknowledgement timeout'
pub('state',args.state,True)
if args.event!='state-only':
    pub('event',json.dumps({'event':args.event,'ts':time.time()+args.clock_offset,'id':str(uuid.uuid4())}))
client.disconnect();client.loop_stop()
print('Broker acknowledged controlled intent:',args.state,args.event)
