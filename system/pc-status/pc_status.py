#!/usr/bin/python3
"""Root-owned logind lifecycle -> MQTT. No light commands, no polling presence."""
import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import paho.mqtt.client as mqtt
from policy import Policy

LOG = logging.getLogger('pc-status')
BASE = 'archyper/pc-status'
DISCOVERY = 'homeassistant/binary_sensor/archyper_pc_awake/config'
CONFIG = {'name': 'Archyper PC awake', 'unique_id': 'archyper_pc_awake_v2',
          'default_entity_id': 'binary_sensor.archyper_pc_awake',
          'state_topic': BASE+'/state', 'payload_on': 'awake',
          'payload_off': 'asleep',
          'value_template': "{{ 'asleep' if value == 'shutdown' else value }}",
          'device_class': 'running',
          'device': {'identifiers': ['archyper_pc_status_v2'], 'name': 'Archyper lifecycle'}}

class Daemon:
    def __init__(self):
        self.marker = Path('/run/pc-status/boot-wake-delivered')
        self.policy = Policy(self.marker.exists())
        if self.policy.pending == 'boot':
            event_file = self.marker.with_name('boot-event-id')
            if event_file.exists():
                self.policy.pending_id = event_file.read_text().strip()
            else:
                event_file.write_text(self.policy.pending_id)
        self.connected = False
        self.flushing = False
        self.inhibitor = None
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1'), 'org.freedesktop.login1.Manager')
        self.manager.connect_to_signal('PrepareForSleep', self.sleep_signal)
        self.manager.connect_to_signal('PrepareForShutdown', self.shutdown_signal)
        self.inhibit()
        self.client = mqtt.Client(client_id='archyper-pc-status-v2', clean_session=True)
        self.client.username_pw_set(os.environ['MQTT_USER'], os.environ['MQTT_PASS'])
        # Availability is diagnostic only. It is NEVER an off intent.
        self.client.will_set(BASE+'/availability', 'offline', qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        # NetworkManager wakes after logind's resume signal. Keep recovery
        # bounded instead of sleeping up to 15s once the network is ready.
        self.client.reconnect_delay_set(min_delay=1, max_delay=2)
        self.client.connect_async(os.environ['MQTT_HOST'], int(os.environ.get('MQTT_PORT', '1883')), keepalive=20)
        self.client.loop_start()
        self.loop = GLib.MainLoop()
        GLib.timeout_add_seconds(1, self.retry)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self.stop)

    def inhibit(self):
        if self.inhibitor is None:
            self.inhibitor = self.manager.Inhibit('sleep:shutdown', 'pc-status', 'Publish lifecycle intent before network teardown', 'delay').take()

    def release(self):
        if self.inhibitor is not None:
            os.close(self.inhibitor)
            self.inhibitor = None

    def on_connect(self, client, userdata, flags, rc):
        self.connected = rc == 0
        if self.connected:
            GLib.idle_add(self.reconnected)
        else:
            LOG.warning('MQTT connection rejected (code %s)', rc)

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        LOG.info('MQTT disconnected; light intent unchanged')

    def publish(self, topic, payload, retain=False, timeout=0.5):
        if not self.connected:
            return False
        info = self.client.publish(topic, payload, qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return False
        try:
            info.wait_for_publish(timeout=timeout)
            return info.is_published()
        except (RuntimeError, ValueError):
            return False

    def event(self, kind, timeout=0.5, event_id=None):
        return self.publish(BASE+'/event', json.dumps({'event': kind, 'ts': time.time(), 'id': event_id or str(uuid.uuid4())}), timeout=timeout)

    def reconnected(self):
        self.publish(DISCOVERY, json.dumps(CONFIG), True)
        self.publish(BASE+'/availability', 'online', True)
        self.flush()
        LOG.info('MQTT connected; retained state=%s (reconnect is not wake)', self.policy.state)
        return False

    def flush(self):
        if self.flushing:
            return
        self.flushing = True
        try:
            if not self.publish(BASE+'/state', self.policy.state, True):
                return
            if self.policy.pending:
                reason = self.policy.pending
                if self.event(reason, event_id=self.policy.pending_id):
                    # /run persists service restart, not OS reboot. Keep marker
                    # on all successful wake deliveries to prevent restart wakes.
                    self.marker.touch(mode=0o600)
                    self.policy.delivered()
                    LOG.info('Wake delivered: %s', reason)
        finally:
            self.flushing = False

    def retry(self):
        if self.policy.pending and self.connected:
            self.flush()
        return True

    def quiesce(self, kind):
        # logind defaults to 5s; release our delay FD within 3s even
        # if the broker or network is down. Never suspend the machine ourselves.
        deadline = time.monotonic()+3
        try:
            while not self.connected and time.monotonic() < deadline:
                time.sleep(0.05)
            if self.connected:
                remaining = max(0.01, deadline-time.monotonic())
                ok = self.publish(BASE+'/state', self.policy.state, True, remaining/2)
                remaining = max(0.01, deadline-time.monotonic())
                if ok:
                    ok = self.event(kind, remaining)
                LOG.info('%s intent acknowledged=%s', kind, ok)
            else:
                LOG.warning('%s not delivered: broker unavailable; no network-loss off', kind)
        finally:
            self.release()

    def sleep_signal(self, preparing):
        if preparing:
            self.policy.sleep()
            self.quiesce('sleep')
        else:
            self.inhibit()
            self.policy.resume()
            self.flush()

    def shutdown_signal(self, preparing):
        if preparing:
            self.policy.shutdown()
            self.quiesce('shutdown')
        else:
            # Cancelled shutdown is an awake lifecycle transition.
            self.inhibit()
            self.policy.resume()
            self.flush()

    def stop(self):
        # Service maintenance is NOT OS shutdown and must not affect lights.
        self.release()
        self.publish(BASE+'/availability', 'offline', True, 1)
        self.client.disconnect()
        self.client.loop_stop()
        self.loop.quit()
        return False

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    Daemon().loop.run()
