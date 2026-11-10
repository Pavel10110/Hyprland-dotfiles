# Package classification (collected inventory, not installation instructions)

`audit/build_manifests.py` recomputes set intersections/differences and asserts every staged list matches its derivation. `audit/package-classification.json` enumerates all 1,361 unique installed package names from the collected snapshots, with per-host version, native/foreign repository class, explicit/dependency reason, both/host-only presence and a review category. It is complete for those snapshots, not a claim about future repository availability or package health.

| Snapshot | Installed | Foreign installed | Explicit native | Explicit foreign | Native extras | Foreign extras |
|---|---:|---:|---:|---:|---:|---:|
| PC | 1266 | 24 | 251 | 23 | 24 | 16 |
| Laptop | 1199 | 21 | 255 | 15 | 28 | 8 |

Common explicitly installed intersection: **227 native + 7 foreign = 234**, asserted against `pacman.txt`, `aur.txt` and their union `pkglist.txt`. `*-explicit-*.txt` are complete per-host explicit inventories; `*-extra.txt` are only differences from the common intersection. Full installed inventory additionally includes dependencies, which must not all become explicitly installed packages on restore. Native/foreign means pacman's snapshot classification; foreign does not imply every package is currently in AUR or trustworthy.

## Review classes
- `hardware-driver-review`: microcode, NVIDIA/CUDA, Intel media/Vulkan, Broadcom, laptop power/fingerprint choices. Common presence is **not** evidence that both machines require the same driver. Never blindly install both vendors' microcode/GPU stacks or copy PC NVIDIA packages to the Intel laptop.
- `installer-rescue-review`: archinstall/installation, recovery/live-media, firmware-recovery, VM guest and rescue utilities present in existing inventories. Quarantine from an everyday-desktop restore plan pending owner review; do not uninstall them during this task.
- `desktop-session-choice`: compositor/session/startup/portal/notification choices. Dunst inventory presence is not a recommendation to launch it beside SwayNC. Competing portal or session alternatives require explicit selection.
- `noncore-config-runtime`: direct shell/editor/launcher/terminal/palette/runtime dependencies. Presence does not provision Oh My Zsh, Powerlevel10k custom trees, Mason binaries, external assets or private SSH keys. Guarded optional tools can remain absent.
- `dictation-optional-runtime`: the existing optional audio/transcription/overlay stack; GPU backend is host-specific. Models, recordings and overlays are not automatically installed by an inventory.
- `other-explicit-review`: remaining explicitly selected apps/libraries/tools. This deliberately avoids invented purpose/necessity judgments from names alone; these remain inventoried with exact host/version/repository axes and need owner selection.
- `dependency-inventory-only`: not explicitly selected on either snapshot. Let a reviewed package manager solve dependencies; do not convert the full dependency closure into an installation command.

The review categories are conservative local policy tags, not fetched package descriptions. Every record carries `inventory-only; explicit owner review required`. No extra package metadata downloads, package installations, compiler builds, cache cleanup, plugin updates or network package research occurred.

## Historical manifests and boundaries
`audit/historical-manifests.json` preserves earlier package-list content for comparison; the source hash manifests pin the original files. Old mixed native/foreign/installer/driver lists have no install authority. The newly derived lists replace them as inventory documentation only. This task does not generate `pacman -S $(cat ...)`, `paru` bulk-install commands or enable services.

Collected snapshots are private operational evidence. Git credentials, SSH/HA/MQTT secrets, browser data, shell history, model binaries, recordings and generated caches remain outside public dotfiles. Version/name metadata can still reveal workloads; review it before publication.
