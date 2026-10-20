# Desktop memory and idle tuning

ZRAM is half physical RAM, uses LZ4 for low latency, and has swap priority 100.
The existing 16 GiB /swapfile is preserved as the lower-priority fallback.
ZRAM size is logical uncompressed capacity, not reserved physical RAM.
Swappiness 100 and page-cluster 0 favor compressed swap without aggressive 180 settings for mixed disk/ZRAM swap.

## Restore
Install zram-generator using the normal full Arch upgrade/package workflow.
From this directory:
```
sudo install -m 644 zram-generator.conf /etc/systemd/zram-generator.conf
sudo install -m 644 90-vexa-memory.conf /etc/sysctl.d/90-vexa-memory.conf
sudo sysctl -p /etc/sysctl.d/90-vexa-memory.conf
```
Reboot at your convenience; do not blindly restart occupied ZRAM on a memory-constrained session.
Preserve or recreate the disk swapfile separately; this does not create disk swap.
Verify using `swapon --show`, `zramctl`, and `sysctl vm.swappiness vm.page-cluster`.

## Desktop
Hypridle and Hyprland configs are symlinked from the existing hypr Stow package.
Monitor timeout remains 400 seconds, DPMS-only; suspend timeout remains 1800 seconds.
Suspend locks before sleep with compositor-confirmed readiness; no idle lock listener exists.
Discord, Obsidian, and Yandex Music no longer auto-launch; existing processes are not closed.

## Rollback
The timestamped ~/backups/memory-idle-* directory contains pre-change live/repo/system configs and a paths manifest.
Restore those files, reapply previous sysctls, and reboot to restore the previous ZRAM size.
No package removal, no automatic reboot, and no Git commit/push is performed.
