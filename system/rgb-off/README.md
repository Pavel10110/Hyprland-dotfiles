RGB-off lifecycle worker

Install with sudo bash system/rgb-off/install.sh. The original OpenRGB/I2C
algorithm is included unchanged as rgb-off.sh. A Type=simple worker waits
10 seconds and runs it; boot targets do not wait for completion. The post-sleep
hook only queues systemctl restart --no-block, so logind and NetworkManager
can resume immediately. The same service serializes boot/resume requests.

Safe verification: systemd-analyze verify, bash -n, systemctl restart rgb-off,
then inspect systemctl status/journal. This only turns existing RGB hardware
off; it never sleeps, reboots, changes networking or controls the monitor light.
Installer backs up old unit, hook and worker directory under /var/backups.
The Hypridle after_sleep command must only restore DPMS, not duplicate RGB.

Actual next boot/resume timing still requires a user-approved lifecycle test.
The logind 5-second pre-suspend timeout belongs to Hypridle; do not disable
lock-before-sleep inhibition to disguise it. Investigate the missing local
hyprlock.conf and lock readiness separately without forcing a user lock.
