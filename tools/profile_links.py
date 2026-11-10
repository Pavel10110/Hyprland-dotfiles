#!/usr/bin/env python3
"""Narrow, journaled replacement of folded host-profile directory links."""
import argparse
import json
import os
from pathlib import Path
import stat
import uuid


class Refusal(ValueError):
    """A guard failed; no force mode exists."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def owned(path, kind):
    s = path.lstat()
    require(s.st_uid == os.getuid(), f'not owned: {path}')
    require(kind(s.st_mode), f'wrong object type: {path}')
    return s


def directory(path, private=False):
    s = owned(path, stat.S_ISDIR)
    require(not s.st_mode & 0o022, f'writable by others: {path}')
    if private:
        require(stat.S_IMODE(s.st_mode) == 0o700, f'not private 0700: {path}')


def anchor(path, private=False):
    path = Path(os.path.abspath(path))
    require(path != Path('/'), 'root anchor forbidden')
    require(path.resolve() == path, f'non-real anchor: {path}')
    directory(path, private)
    return path


def chain(base, relative):
    directory(base)
    current = base
    for part in Path(relative).parts:
        current = current / part
        directory(current)


def identity(path):
    s = owned(path, stat.S_ISLNK)
    return {'literal': os.readlink(path), 'uid': s.st_uid, 'mode': stat.S_IMODE(s.st_mode)}


def regular_json(path):
    s = owned(path, stat.S_ISREG)
    require(not s.st_mode & 0o022, f'unsafe file: {path}')
    return json.loads(path.read_text())


def replace_link(target, literal):
    """Fresh same-parent symlink, atomically replacing the directory entry."""
    temporary = target.parent / ('.profile-link-' + uuid.uuid4().hex)
    os.symlink(literal, temporary)
    try:
        os.replace(temporary, target)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def run(action, home, repo, journal, host, marker, manifest):
    require(action in ('check', 'apply', 'rollback'), 'unknown action')
    require(os.getuid() != 0, 'root execution forbidden')
    require(host in ('pc', 'laptop'), 'host must be pc or laptop')
    home = anchor(home)
    repo = anchor(repo)
    require(repo == home / 'dotfiles', 'repo must be the real HOME/dotfiles anchor')
    journal = Path(os.path.abspath(journal))
    private = anchor(journal.parent, private=True)
    require(journal.name not in ('', '.', '..'), 'invalid run name')
    require(not journal.is_relative_to(repo) and not journal.is_relative_to(home / '.config'),
            'journal must be outside repository and config targets')
    marker = Path(os.path.abspath(marker))
    require(marker.resolve() == marker, 'marker must not be a symlink')
    ms = owned(marker, stat.S_ISREG)
    require(not ms.st_mode & 0o022, 'unsafe host marker')
    require(marker.read_text().strip() == host, 'host marker mismatch')
    require(type(manifest) is dict and set(manifest) == {'version', 'host', 'files'}, 'manifest keys')
    require(type(manifest['version']) is int and manifest['version'] == 1, 'manifest version')
    require(manifest['host'] == host, 'manifest host mismatch')
    require(type(manifest['files']) is list, 'files must be a list')
    names = ('swaync', 'fastfetch') if host == 'pc' else ('swaync',)
    require(len(manifest['files']) == len(names), 'wrong profile link count')
    by_target = {}
    for entry in manifest['files']:
        require(type(entry) is dict and set(entry) == {'target', 'before_link', 'source'}, 'entry keys')
        require(all(type(v) is str for v in entry.values()), 'entry values must be strings')
        require(entry['target'] not in by_target, 'duplicate target')
        by_target[entry['target']] = entry
    require(set(by_target) == {f'.config/{n}' for n in names}, 'unsupported targets')
    entries = []
    for name in names:
        e = by_target[f'.config/{name}']
        require(e['source'] == f'host-{host}/.config/{name}', 'noncanonical source')
        require(e['before_link'] == f'../dotfiles/{name}/.config/{name}', 'unexpected old literal')
        chain(home, '.config')
        chain(repo, e['source'])
        target = home / e['target']
        before = {'literal': e['before_link'], 'uid': os.getuid(), 'mode': 0o777}
        after = dict(before, literal=os.path.relpath(repo / e['source'], target.parent))
        entries.append(dict(e, before=before, after=after))
    # All target/source/parent validation precedes creating even the run directory.
    actual = [identity(home / e['target']) for e in entries]
    binding = {'version': 1, 'host': host, 'home': str(home), 'repo': str(repo),
               'journal': str(journal), 'marker': str(marker), 'entries': entries}
    exists = os.path.lexists(journal)
    if exists:
        directory(journal, private=True)
        directory(journal / 'backups', private=True)
        require(regular_json(journal / 'journal.json') == binding, 'journal binding mismatch')
        for i, e in enumerate(entries):
            require(identity(journal / 'backups' / str(i)) == e['before'], 'backup changed')
        for observed, e in zip(actual, entries):
            require(observed in (e['before'], e['after']), 'link edited outside migration')
    else:
        require(action != 'rollback', 'no journal to roll back')
        require(all(observed == e['before'] for observed, e in zip(actual, entries)),
                'all original links must match before first apply')
    states = ['old' if observed == e['before'] else 'installed' for observed, e in zip(actual, entries)]
    state = states[0] if len(set(states)) == 1 else 'partial'
    if action == 'check':
        return {'state': state, 'changed': 0, 'links': len(entries)}
    if not exists:
        journal.mkdir(mode=0o700)
        (journal / 'backups').mkdir(mode=0o700)
        # Persist originals before replacing a single target. Never resolve backups:
        # their relative literals are meaningful only at the original HOME entry.
        fd = os.open(journal / 'journal.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(binding, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for i, e in enumerate(entries):
            os.link(home / e['target'], journal / 'backups' / str(i), follow_symlinks=False)
    desired = 'after' if action == 'apply' else 'before'
    # Recheck the whole batch after journal creation, before the first mutation.
    require([identity(home / e['target']) for e in entries] == actual, 'links changed during preflight')
    changed = 0
    for observed, e in zip(actual, entries):
        if observed != e[desired]:
            replace_link(home / e['target'], e[desired]['literal'])
            changed += 1
    require(all(identity(home / e['target']) == e[desired] for e in entries), 'post-write verification failed')
    return {'state': 'installed' if action == 'apply' else 'old', 'changed': changed, 'links': len(entries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='No force mode. Cooperating user writers only; not a hostile-filesystem or power-loss transaction.')
    parser.add_argument('action', choices=('check', 'apply', 'rollback'))
    parser.add_argument('--host', required=True, choices=('pc', 'laptop'))
    parser.add_argument('--home', required=True, type=Path, help='real owned HOME anchor')
    parser.add_argument('--repo', required=True, type=Path, help='real owned HOME/dotfiles anchor')
    parser.add_argument('--journal', required=True, type=Path, help='run directory under an existing owned 0700 parent')
    parser.add_argument('--host-marker', required=True, type=Path, help='owned regular file containing pc or laptop')
    parser.add_argument('--manifest', required=True, type=Path, help='owned regular JSON manifest version 1')
    args = parser.parse_args()
    try:
        manifest = regular_json(args.manifest)
        print(json.dumps(run(args.action, args.home, args.repo, args.journal, args.host, args.host_marker, manifest), sort_keys=True))
    except (Refusal, OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'refused: {error}\n')


if __name__ == '__main__':
    main()
