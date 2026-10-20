# PC lifecycle and monitor light

Canonical source: this directory in the desktop dotfiles repository. Installed runtime: root-owned `/usr/local/lib/pc-status/`, `/etc/systemd/system/pc-status.service`, and private `/etc/pc-status/mqtt.env` (0600). Desktop login is not required.

## Behavior

Logind PrepareForSleep/PrepareForShutdown signals publish retained awake/asleep/shutdown state and non-retained lifecycle events over MQTT. A bounded delay inhibitor gives publications up to three seconds before sleep/shutdown proceeds. HA turns the monitor light off ten seconds after receiving sleep/shutdown; boot/resume turns it on. Wake cancels pending off. Lock/display off, connection loss, and service maintenance do not change light intent. Brightness/color are not set. Morning light routine remains; its delayed off is blocked while PC awake.

QoS event IDs are deduplicated using an HA input_text helper. Retained state alone never turns on the light, preserving manual off across reconnects and automation reloads. The boot delivery marker lives in /run/pc-status and survives service restart, not reboot. If the broker is unavailable during suspend/shutdown, that off event may be lost; there is deliberately no network-loss fallback.

## Fresh restore

Arch dependencies: python, python-dbus, python-gobject, python-paho-mqtt (the implementation uses Paho 1.x callback signatures; verify against the installed version before upgrade).

Create a private file outside Git with MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS lines. Restore/obtain credentials securely, then run:

```sh
sudo ./install.sh "$PWD" /path/to/private-mqtt.env
sudo systemctl status pc-status.service
sudo journalctl -u pc-status.service -n 30
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_policy test_daemon
```

Existing credentials are preserved on reinstall. System files are copies, not user-writable symlinks; rerun installer to deploy source updates. The installer backs up displaced hooks/units in /var/backups. First migration backup on this PC is /home/archyper/backups/pc-status-20261011-085234.

HA source lives in ../../home-assistant/monitor-light. Restore HA separately; do not assume cloning PC dotfiles deploys HA. deploy.py requires websocket-client plus a private HASS_URL/HASS_TOKEN env file, a backup directory outside Git, and API access:

```sh
python3 ../../home-assistant/monitor-light/deploy.py --env-file /path/to/private-ha.env --backup-dir /path/to/private-backup
```

JSON files are exact deployment payloads; automations.yaml documents the same configuration. The script creates the deduplication helper if missing, applies lifecycle and morning automations, and retires only the known old PC-light rules. IDs and entity names currently describe this household: review them before restoring onto a different HA installation. HA MQTT integration must already use the same broker.

## Testing and rollback

verify.py in the HA directory intentionally toggles the monitor light and restarts/kills the publisher to check recovery; it restores original light state, and never suspends or shuts down the PC. It expects the verifier scripts installed under /usr/local/lib/pc-status and SSH access. Actual suspend/resume and shutdown/boot need a coordinated human test and remain unverified as of deployment.

To roll back: disable the new service, restore backed-up original hook/helper and HA JSON configs, and reload HA automations. Do not run both old direct-light hooks and the new lifecycle automation. Legacy MQTT sensor configuration may remain dormant if HA filesystem access is unavailable; it is not used by the replacement.
