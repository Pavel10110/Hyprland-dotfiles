#!/bin/bash
# sudo ./install.sh [source-directory] [private-mqtt-env-file]
set -euo pipefail
src=$(realpath "${1:-$(dirname "$0")}")
backup="/var/backups/pc-status-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup" /etc/pc-status
for file in /usr/lib/systemd/system-sleep/99-monitor-backlight /usr/local/bin/pc-monitor-backlight /etc/systemd/system/pc-status.service /usr/local/lib/pc-status/pc_status.py /usr/local/lib/pc-status/policy.py; do
  if [[ -e $file ]]; then cp -a --parents "$file" "$backup/"; fi
done
if [[ ! -e /etc/pc-status/mqtt.env ]]; then
  [[ -n ${2:-} && -f $2 ]] || { printf 'Provide private MQTT env file as second argument. See README.md.\n' >&2; exit 1; }
  install -m 0600 "$2" /etc/pc-status/mqtt.env
fi
chown root:root /etc/pc-status/mqtt.env
chmod 0600 /etc/pc-status/mqtt.env
/usr/bin/python3 -c 'import dbus; from gi.repository import GLib; import paho.mqtt.client'
install -d -m 0755 /usr/local/lib/pc-status
install -m 0644 "$src/policy.py" "$src/pc_status.py" /usr/local/lib/pc-status/
install -m 0644 "$src/pc-status.service" /etc/systemd/system/pc-status.service
systemd-analyze verify /etc/systemd/system/pc-status.service
systemctl daemon-reload
systemctl enable pc-status.service
systemctl restart pc-status.service
systemctl is-active --quiet pc-status.service
rm -f /usr/lib/systemd/system-sleep/99-monitor-backlight /usr/local/bin/pc-monitor-backlight
printf 'Backup: %s\n' "$backup"
