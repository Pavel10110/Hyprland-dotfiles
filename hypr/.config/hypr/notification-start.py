#!/usr/bin/env python3
"""Start SwayNC through its vendor user unit, only from a Wayland session.

Leave any existing same-user daemon alone (including a legacy standalone one).
Migration of that daemon and historical failed-unit state belongs to deployment,
not a login hook. No direct-binary fallback, restart or D-Bus activation probe.
"""
import os
import subprocess
import sys


def main():
    existing = subprocess.run(
        ['pgrep', '-u', str(os.getuid()), '-x', 'swaync'],
        stdout=subprocess.DEVNULL,
    ).returncode
    if existing == 0:
        return 0
    if existing != 1:
        return existing
    if not os.environ.get('WAYLAND_DISPLAY'):
        print('notification-start: no WAYLAND_DISPLAY; not starting swaync', file=sys.stderr)
        return 1
    # SwayNC needs the Wayland socket and GTK desktop identity, not the entire
    # caller environment or Hyprland's private IPC signature. Import by name:
    # systemctl reads each value from this ordinary session process environment.
    names = [name for name in ('WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP') if os.environ.get(name)]
    imported = subprocess.run(['systemctl', '--user', 'import-environment', *names])
    if imported.returncode:
        return imported.returncode
    # Type=dbus / BusName is provided by the installed swaync.service. A start
    # is idempotent even if another caller concurrently requests the same unit.
    return subprocess.run(['systemctl', '--user', 'start', 'swaync.service']).returncode


if __name__ == '__main__':
    raise SystemExit(main())
