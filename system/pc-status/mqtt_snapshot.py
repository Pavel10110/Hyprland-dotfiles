#!/usr/bin/python3
"""Check broker retained lifecycle snapshot, without changing PC or light."""
import json
import shlex
import time
from pathlib import Path
import paho.mqtt.client as mqtt
c={}
for l in Path('/etc/pc-status/mqtt.env').read_text().splitlines():
    if l and not l.startswith('#') and '=' in l:
        k,v=l.split('=',1);v=shlex.split(v);c[k.strip()]=v[0] if v else ''
messages=[]
client=mqtt.Client('archyper-pc-status-snapshot')
client.username_pw_set(c['MQTT_USER'],c['MQTT_PASS'])
def connected(client,u,f,rc):
    assert rc==0
    client.subscribe('archyper/pc-status/#',qos=1)
def message(client,u,m):
    messages.append({'topic':m.topic,'payload':m.payload.decode(),'retained':bool(m.retain)})
client.on_connect=connected;client.on_message=message
client.connect(c['MQTT_HOST'],int(c.get('MQTT_PORT',1883)),20)
client.loop_start();time.sleep(2);client.disconnect();client.loop_stop()
assert any(m['topic'].endswith('/state') and m['retained'] for m in messages)
assert not any(m['topic'].endswith('/event') and m['retained'] for m in messages), 'Retained wake event is unsafe'
print(json.dumps(messages))
