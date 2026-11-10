# Shared PC and laptop dotfiles

One configuration history, shared application settings, and explicit host profiles. This repository remains the source of truth; private credentials, models, caches and rollback snapshots stay outside Git.

## Layout

- `host-pc/`, `host-laptop/`: monitor/input/power policy, Waybar modules, terminal/prompt/Fastfetch/notification differences.
- `hypr/`: shared Lua configuration plus the laptop's legacy configuration and version-aware IPC helpers. Hyprland 0.56 uses the preserved legacy path; 0.57 uses Lua. Unknown IPC versions fail rather than trying destructive fallbacks.
- `nvim/`, `rofi/`, `scripts/`, `wal/`, `waybar/`, `zsh/`, `vexa/`: shared source. Host prompts and notification layouts remain distinct.
- `fastfetch/`: shared ASCII assets. The PC profile's asset alias preserves its existing folded-directory layout.
- `hermes-browser/`: PC-only manual browser/tunnel integration. Browser profiles, cookies and SSH keys are not included.
- `packages/`: inventories, **not** a command to install every package or driver.
- `back/`, `system/`, `home-assistant/`: retained historical/PC integration material; not blanket-installed on the laptop.
- `tools/`: opt-in checked deployment and rollback helpers. Nothing automatically pulls, commits, pushes, installs packages or reboots.

All original package directories and their roles are recorded in `docs/package-roles.json`.

## Host selection

The owned regular file `~/.config/dotfiles-host` contains exactly `pc` or `laptop`. Select only the matching host profile. Do not blanket-Stow both profiles or use `--adopt`, `git reset --hard`, `git clean`, or deletion-based synchronization over live user files.

The deployment preserves already-correct relative links instead of normalizing them. Folded Nvim/Rofi/script directories remain folded; the SwayNC and PC Fastfetch parents point to their matching host profile.

## Quick checks

```sh
git -C "$HOME/dotfiles" status --short
hyprctl configerrors
"$HOME/dotfiles/tools/dotfiles-sync" check \
  --home "$HOME" --repo "$HOME/dotfiles" \
  --manifest "$HOME/.local/state/vexa-dotfiles-sync/current-home-manifest.json"
```

The last command verifies the explicitly installed leaf transaction. It is not a microphone, visual, fresh-login or reboot test. The per-host deployment receipt and exact rollback commands are kept privately under `~/.local/state/vexa-dotfiles-sync/`; retain them with the backups.

## Dictation and private Waybar runtime

- Primary dictation is **Super+V**. The PC's existing **Super+Alt+V** streaming shortcut remains separate.
- The local Whisper model lives under `~/.local/share/vexa/models/`, not this repository. Laptop CPU settings live in its host profile. Eww is optional.
- File-only transcription forces microphone/UI/paste actions off; use a synthetic sample for unattended tests, never the foreground application's clipboard.
- Waybar's HA settings are an owned regular `~/.config/waybar/private.env`, mode `0600`. This is inert JSON-string assignment data, not a file to source in a shell.
- The preserved Pomodoro binary lives under `~/.local/lib/waybar/`, mode `0700`, and is hash-checked before use.
- The ignored Waybar palette pointer is generated for each user's existing wal cache. Never commit a frozen host palette or copy credential-bearing legacy helpers into shared source.

## Future synchronization

Ordinary edits through existing source links remain ordinary Git work. Inspect both machines' changes, reconcile host-specific choices, review a canonical commit and transport that exact commit privately. No automatic bidirectional merge or GitHub publication is configured.

`tools/dotfiles-sync` means selected **repository → HOME** installation, not Git transport. `tools/deploy_repo.py` handles a separately reviewed local Git bundle and preserves old branches/index/source backups. These are separate phases; do not confuse a staged file or successful transfer with live acceptance.

Rollback order matters: restore retired original repository leaves first, then undo HOME/parent-link/state migrations in the recorded order, then roll back the remaining repository transition. Use the exact per-host rollback document; do not improvise a reset or delete backups.

## Optional laptop system update

Configuration migration does not grant sudo or authorize a reboot. A full update needs privileged boot/recovery evidence, a reviewed complete transaction, healthy power/disk/package state and an idle-enough workload window. Do not partially upgrade Arch or interrupt active work merely to finish an update.
