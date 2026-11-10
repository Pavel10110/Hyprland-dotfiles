#!/usr/bin/env python3
"""Explicit, reviewed leaf-file installation from an existing Stow repository.

No discovery, network, Git mutation, service management, or privilege escalation.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import uuid


class Refused(ValueError):
    pass


MAX_BYTES = 2 * 1024 * 1024
STATE = '.local/state/dotfiles-sync'
MARKER = '.config/dotfiles-host'
FORBIDDEN = {'.ssh', '.gnupg', '.pki', '.cache', 'models', 'cache',
             'chromium', 'google-chrome', 'BraveSoftware', 'firefox', '.mozilla',
             'githubssh', 'githubssh.pub', '.git', 'credentials', 'tokens'}
PRIVATE_SUFFIXES = ('.bin', '.gguf', '.safetensors', '.pem', '.key')


def fail(message):
    raise Refused(message)


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        fail('expected nonempty POSIX relative path')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')):
        fail('absolute, empty, or traversal component: ' + value)
    if any(x in FORBIDDEN for x in p.parts):
        fail('secret/browser/cache/model/Git path excluded: ' + value)
    if any(x.endswith(PRIVATE_SUFFIXES) for x in p.parts):
        fail('private/model file excluded: ' + value)
    return p


def owned(path):
    if path.lstat().st_uid != os.getuid():
        fail('not owned by invoking user: ' + str(path))


def anchor(path):
    path = Path(os.path.abspath(path))
    # Reject aliases, even if a link happens to resolve inside the same tree.
    if path.resolve() != path or not path.is_dir():
        fail('root must be a real directory without symlink ancestors: ' + str(path))
    owned(path)
    return path


def parents(root, path):
    for part in path.relative_to(root).parts[:-1]:
        root = root / part
        if os.path.lexists(root):
            owned(root)
            if root.is_symlink() or not root.is_dir():
                fail('parent is not an owned real directory: ' + str(root))


def digest(path):
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size > MAX_BYTES:
        fail('only regular configuration files <= 2 MiB allowed: ' + str(path))
    owned(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def link_state(path, link):
    try:
        resolved = (path.parent / link).resolve(strict=False)
    except (OSError, RuntimeError):
        fail('cyclic or invalid symlink: ' + str(path))
    if (any(x in FORBIDDEN - {'cache'} for x in resolved.parts)
            or any(x.endswith(PRIVATE_SUFFIXES) for x in resolved.parts)):
        fail('refusing sensitive symlink referent: ' + str(path))
    referent = None
    if resolved.exists():
        referent = {'sha256': digest(resolved), 'mode': stat.S_IMODE(resolved.stat().st_mode)}
    return {'resolved': str(resolved), 'referent': referent}


def snapshot(path, resolve_link=True):
    """lstat identity plus link resolution/referent, without dereference writes."""
    path = Path(path)
    if not os.path.lexists(path):
        return {'kind': 'missing'}
    owned(path)
    s = path.lstat()
    result = {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid}
    if stat.S_ISLNK(s.st_mode):
        result.update(kind='symlink', link=os.readlink(path))
        if resolve_link:
            result.update(link_state(path, result['link']))
    elif stat.S_ISREG(s.st_mode):
        result.update(kind='file', sha256=digest(path))
    else:
        fail('not a regular file or leaf symlink: ' + str(path))
    return result


def object_identity(value):
    # Relative link resolution changes while stored in objects/, not its identity.
    return {k: v for k, v in value.items() if k not in ('resolved', 'referent')}


def validate(home, repo, manifest):
    home, repo = anchor(home), anchor(repo)
    if manifest.get('version') != 1 or manifest.get('host') not in ('pc', 'laptop'):
        fail('version 1 and explicit pc/laptop host required')
    marker = home / MARKER
    parents(home, marker)
    if marker.is_symlink() or not marker.is_file():
        fail('missing real host marker: ' + str(marker))
    owned(marker)
    if marker.read_text().strip() != manifest['host']:
        fail('host marker does not match manifest')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        fail('nonempty explicit files list required')
    planned = []
    targets = []
    for entry in files:
        src, dst = relative(entry['source']), relative(entry['target'])
        if len(src.parts) < 2:
            fail('source must be package/path in existing Stow layout')
        if src.parts[0].startswith('host-') and src.parts[0] != 'host-' + manifest['host']:
            fail('wrong host package')
        if str(dst) == MARKER or str(dst).startswith(STATE) or dst.parts[0] == 'dotfiles':
            fail('reserved control/source target')
        source, target = repo / src, home / dst
        if target == repo or repo in target.parents:
            fail('HOME target overlaps source repository')
        parents(repo, source)
        parents(home, target)
        if source.is_symlink() or not source.is_file():
            fail('source must be a real regular leaf file')
        if entry['sha256'] != digest(source):
            fail('source hash mismatch: ' + str(src))
        mode = entry['mode']
        if type(mode) is not int or mode < 0 or mode > 0o777 or stat.S_IMODE(source.stat().st_mode) != mode:
            fail('source mode mismatch or special mode forbidden')
        if entry.get('kind') not in ('copy', 'symlink') or not isinstance(entry.get('before'), dict):
            fail('kind and reviewed before snapshot required')
        desired = {'kind': 'file', 'mode': mode, 'uid': os.getuid(), 'sha256': entry['sha256']}
        if entry['kind'] == 'symlink':
            desired = {'kind': 'symlink', 'mode': 0o777, 'uid': os.getuid(),
                       'link': str(source), 'resolved': str(source),
                       'referent': {'sha256': entry['sha256'], 'mode': mode}}
        targets.append(dst)
        planned.append((entry, source, target, desired))
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            if a == b or a in b.parents or b in a.parents:
                fail('duplicate or ancestor targets')
    # Reject dependency transactions rather than letting our own writes invalidate
    # the original-referent rollback guard. Include aliases and broken referents;
    # shared old referents are conservatively refused too. Installed no-ops need
    # no preservation and may legitimately share a repository source.
    for _, _, target, desired in planned:
        if not target.is_symlink():
            continue
        current = snapshot(target)
        if current == desired:
            continue
        referent = Path(current['resolved'])
        for _, _, other, _ in planned:
            if other != target:
                for candidate in (other, other.resolve(strict=False)):
                    if candidate == referent or candidate in referent.parents:
                        fail('inter-target referent dependency: ' + str(target))
    return home, repo, planned


def check(home, repo, manifest):
    _, _, planned = validate(home, repo, manifest)
    return all(snapshot(target) == desired for _, _, target, desired in planned)


def mkdirs(root, path, private=False):
    parents(root, path / '_leaf')
    path.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
    if private:
        # Do not silently fix an unsafe preexisting state directory.
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            fail('private state directory must have mode 0700: ' + str(path))


@contextlib.contextmanager
def locked(home):
    state = home / STATE
    mkdirs(home, state, private=True)
    lock = state / 'lock'
    if lock.is_symlink():
        fail('symlink lock forbidden')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        owned(lock)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield state
    finally:
        os.close(fd)


def save(run, journal):
    temp = run / 'journal.tmp'
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(journal, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, run / 'journal.json')


def create(target, source, kind, mode):
    if kind == 'symlink':
        os.symlink(str(source), target)
    else:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'wb') as out:
            out.write(source.read_bytes())
            os.fchmod(out.fileno(), mode)
            out.flush()
            os.fsync(out.fileno())


def install(home, repo, manifest, dry_run=False):
    home, repo, planned = validate(home, repo, manifest)

    def pending():
        todo = []
        for entry, source, target, desired in planned:
            current = snapshot(target)
            if current == desired:
                continue
            if current != entry['before']:
                fail('unreviewed conflict: ' + str(target))
            todo.append((entry, source, target, desired))
        return todo

    todo = pending()
    if dry_run or not todo:
        return None
    with locked(home) as state:
        # Revalidate sources/ownership and conflicts after acquiring our lock.
        home, repo, planned = validate(home, repo, manifest)
        todo = pending()
        if not todo:
            return None
        run = state / uuid.uuid4().hex
        run.mkdir(mode=0o700)
        (run / 'objects').mkdir(mode=0o700)
        journal = {'version': 1, 'home': str(home), 'host': manifest['host'],
                   'status': 'applying', 'files': [], 'created_dirs': []}
        save(run, journal)
        try:
            for entry, source, target, desired in todo:
                if snapshot(target) != entry['before'] or digest(source) != entry['sha256']:
                    fail('changed during installation: ' + str(target))
                missing = []
                parent = target.parent
                while not parent.exists():
                    missing.append(str(parent.relative_to(home)))
                    parent = parent.parent
                journal['created_dirs'].extend(reversed(missing))
                row = {'target': entry['target'], 'before': entry['before'],
                       'after': desired, 'object': str(len(journal['files'])), 'phase': 'prepared'}
                journal['files'].append(row)
                save(run, journal)  # Recovery intent persisted before mutation.
                mkdirs(home, target.parent)
                if entry['before']['kind'] != 'missing':
                    os.rename(target, run / 'objects' / row['object'])
                create(target, source, entry['kind'], entry['mode'])
                if snapshot(target) != desired:
                    fail('post-install verification failed: ' + str(target))
                row['phase'] = 'installed'
                save(run, journal)
            journal['status'] = 'installed'
            save(run, journal)
        except Exception as exc:
            raise Refused(f'{exc}; retained recovery journal: {run}') from exc
        return run


def rollback(home, run):
    home = anchor(home)
    run = Path(os.path.abspath(run))
    state = home / STATE
    if run.parent != state or not run.name.isalnum():
        fail('rollback must name a direct private state run')
    parents(home, run / 'journal.json')
    with locked(home):
        owned(run)
        if run.is_symlink() or stat.S_IMODE(run.stat().st_mode) != 0o700:
            fail('unsafe rollback run directory')
        jpath = run / 'journal.json'
        if jpath.is_symlink():
            fail('symlink journal forbidden')
        owned(jpath)
        journal = json.loads(jpath.read_text())
        if journal['home'] != str(home) or journal['version'] != 1:
            fail('journal home/version mismatch')
        marker = home / MARKER
        parents(home, marker)
        if marker.is_symlink() or marker.read_text().strip() != journal['host']:
            fail('wrong host for rollback')
        rows = []
        # Preflight every object and target before changing any target.
        for row in journal['files']:
            target = home / relative(row['target'])
            parents(home, target)
            if not str(row['object']).isdigit():
                fail('invalid backup object')
            backup = run / 'objects' / row['object']
            parents(home, backup)
            before, current = row['before'], snapshot(target)
            restored = current == before
            if journal['status'] == 'rolled-back' and not restored:
                fail('target changed after rollback: ' + str(target))
            interrupted = (journal['status'] == 'applying' and row['phase'] == 'prepared'
                           and current == {'kind': 'missing'} and os.path.lexists(backup))
            if not restored and current != row['after'] and not interrupted:
                fail('target changed since install; rollback refused: ' + str(target))
            if before['kind'] != 'missing' and not restored:
                if object_identity(snapshot(backup, resolve_link=False)) != object_identity(before):
                    fail('backup changed: ' + str(backup))
                if before['kind'] == 'symlink':
                    expected_link = {k: before[k] for k in ('resolved', 'referent')}
                    if link_state(target, before['link']) != expected_link:
                        fail('original link referent changed; rollback refused: ' + str(target))
            rows.append((target, backup, before, restored))
        for target, backup, before, restored in reversed(rows):
            if restored:
                continue
            if os.path.lexists(target):
                target.unlink()  # Never follow a destination link.
            if before['kind'] == 'symlink':
                os.symlink(before['link'], target)
            elif before['kind'] == 'file':
                create(target, backup, 'copy', before['mode'])
            if snapshot(target) != before:
                fail('restoration identity mismatch: ' + str(target))
        for name in reversed(journal['created_dirs']):
            path = home / relative(name)
            parents(home, path / '_leaf')
            try:
                path.rmdir()  # Only empty directories created by this run.
            except (FileNotFoundError, OSError):
                pass
        journal['status'] = 'rolled-back'
        save(run, journal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'sync', 'check', 'inspect', 'rollback'])
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--target', help='one relative HOME path, inspect only')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            home = anchor(args.home)
            target = home / relative(args.target)
            parents(home, target)
            print(json.dumps(snapshot(target), indent=2))
        elif args.command == 'rollback':
            if args.dry_run:
                fail('rollback dry-run unsupported; rollback always preflights all targets')
            rollback(args.home, args.run)
            print('rollback verified; backup objects retained')
        else:
            manifest = json.loads(args.manifest.read_text())
            if args.command == 'check':
                ok = check(args.home, args.repo, manifest)
                print('installed and verified' if ok else 'not installed / differs')
                return 0 if ok else 1
            run = install(args.home, args.repo, manifest, args.dry_run)
            print(str(run) if run else ('dry-run preflight passed' if args.dry_run else 'already installed; no changes'))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
