#!/bin/bash
# sudo ./install.sh: root-aware, preserves original hardware-off algorithm.
set -euo pipefail
[[ $(id -u) == 0 ]] || { printf 'Run with sudo.\n' >&2; exit 1; }
src=$(realpath "$(dirname "$0")")
backup="/var/backups/rgb-off-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "$backup"
for file in /etc/systemd/system/rgb-off.service /usr/lib/systemd/system-sleep/rgb-off /usr/local/lib/rgb-off; do
    [[ ! -e $file ]] || cp -a --parents "$file" "$backup/"
done
install -d -m 0755 /usr/local/lib/rgb-off
install -m 0755 "$src/worker.sh" "$src/rgb-off.sh" /usr/local/lib/rgb-off/
install -m 0755 "$src/sleep-hook" /usr/lib/systemd/system-sleep/rgb-off
install -m 0644 "$src/rgb-off.service" /etc/systemd/system/rgb-off.service
systemd-analyze verify /etc/systemd/system/rgb-off.service
systemctl daemon-reload
systemctl enable rgb-off.service
printf 'Backup: %s\n' "$backup"
# No implicit run/reboot/suspend: caller can test with systemctl restart.
