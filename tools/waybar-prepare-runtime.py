#!/usr/bin/env python3
"""Generate the untracked palette symlink as the target desktop user; no services."""
import argparse
from pathlib import Path


def prepare(home, repo):
    home, repo = Path(home).absolute(), Path(repo).absolute()
    palette = home / '.cache/wal/colors-waybar.css'
    if not palette.is_file():
        raise FileNotFoundError('Generate the host Pywal colors-waybar.css first')
    target = repo / 'waybar/.config/waybar/colors.css'
    if not target.parent.is_dir():
        raise FileNotFoundError('Merge the Waybar package into the target repo first')
    if target.is_symlink():
        if target.readlink() == palette:
            return target
        raise FileExistsError('Refusing to replace a different palette symlink')
    if target.exists():
        raise FileExistsError('Refusing to overwrite an existing palette file')
    target.symlink_to(palette)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home()/'dotfiles')
    args = parser.parse_args()
    print(prepare(Path.home(), args.repo))
