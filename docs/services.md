# Vexa user tools and services

Canonical package: `~/dotfiles/vexa`, deployed as file-level symlinks using
`stow --no-folding --dir="$HOME/dotfiles" --target="$HOME" vexa`.
Do not use `--adopt`: back up conflicts outside Git and move only conflicting
files aside first. Models and unrelated live files remain outside this package.
The arch-setup Vexa snapshots are legacy; its installer excludes them and uses
this package (override clone path with `VEXA_DOTFILES`). Neither repository was
committed or pushed during consolidation.

## Contents and dependencies

`.local/share/vexa/bin/`: dictation toggle, Whisper status helper, Eww colors and
level meter, legacy GTK bubble, Firefox UI helper, JBL battery helper,
hyprsunset controller and optional media auto-pause daemon.
`.local/share/vexa/eww/`: window definitions and default stylesheet.
`.config/systemd/user/`: `hyprsunset-controller.service`, `media-autopause.service`.
RGB/monitor hooks, HA and pc-status are deliberately not managed by this package.

Dictation needs Bash, Python 3, whisper.cpp (`whisper-cli`), PipeWire
(`pw-record`), ffmpeg, wl-clipboard (`wl-copy`), wtype, Eww and Hyprland
(`hyprctl`). Live meter needs `parec` (Arch package `libpulse`); notifications
use `notify-send` (`libnotify`). Optional GTK bubble needs python-gobject and
GTK4; JBL uses Python standard-library hidraw access. Hyprsunset needs
`hyprsunset`; optional media daemon needs `playerctl`. Install GNU Stow (`stow`).

Copy a privately obtained Whisper model to
`~/.local/share/vexa/models/ggml-small.bin` separately; do not add models, keys,
recordings, caches, environment secrets or browser profiles to Git.
Dictation captures only when its toggle is invoked. Recordings/logs stay in
`/tmp/vexa-dictation-$UID`. On invocation the colors helper copies the Yuck
configuration and generates SCSS in `${XDG_CACHE_HOME:-$HOME/.cache}/vexa/eww`;
it reads the optional wal cache. The Git stylesheet is a static fallback, not
a generated copy of the current palette. No recordings were made for testing.

## Service policy

After restoring files, run `systemctl --user daemon-reload`. Only explicitly
enable desired services: `systemctl --user enable --now hyprsunset-controller.service`.
The existing hyprsunset enabled state and process were preserved during migration.
Media auto-pause is faulty/optional and MUST remain off by default:
`systemctl --user disable --now media-autopause.service`, then re-run the Stow
command and daemon-reload (disable may remove the canonical file link). No wants symlink is
packaged for it. The old arch-setup bootstrap now disables it rather than
enabling it. Existing commented Hyprland examples are inert. To opt in later,
review/fix the code and deliberately run `systemctl --user enable --now
media-autopause.service`; this is not part of installation or migration.
Check with `systemctl --user is-enabled media-autopause.service` (`linked`,
exit 1, for an external Stow symlink; `disabled` for a regular unit file).
Both mean NOT enabled; only `enabled` is an autostart state here. Also check
`systemctl --user is-active media-autopause.service` (inactive), and
`systemctl --user show media-autopause.service -p MainPID` (0).

## Fresh restore

1. Clone dotfiles into `~/dotfiles`, install the dependencies above.
2. Back up/move conflicts outside the repository; run the Stow command above.
3. Restore the private model to the live models directory separately.
4. Reload user systemd, keep media auto-pause disabled, and optionally enable
   hyprsunset. Do not run dictation just to syntax-check.
5. `bash -n ~/.local/share/vexa/bin/vexa-dictate-toggle.sh`; compile Python
   scripts in memory with `compile(path.read_text(), str(path), 'exec')`.

## Undo this migration

Backup directory: `/home/archyper/backups/vexa-consolidation-20261011-084719`.
It contains original affected files beneath `home/`, `manifest.json`, the
before-state Git status/diffs, and hashes of existing dirty dotfiles. Keep
this backup private and outside Git. Do not use blanket git reset/checkout.

To undo, run `stow --no-folding --dir="$HOME/dotfiles" --target="$HOME" -D vexa`,
then restore only each path listed in `manifest.json` from its matching
`home/` backup (preserve metadata, do not copy through remaining symlinks).
Remove only the newly created `dotfiles/vexa` package and `docs/services.md`
if desired, retaining all pre-existing modifications. Restore `.gitignore`
and the four arch-setup files from their backups only if no later edits have
been made. Run `systemctl --user daemon-reload` and explicitly
`systemctl --user disable --now media-autopause.service`. If retaining the
Stow package instead of undoing, re-stow afterward to restore the file link. The original
arch-setup installer enabled media auto-pause, so never execute that old
installer without removing its auto-enable command again.
