#!/usr/bin/env python3
"""Local, reviewed Git-bundle transport. Never installs HOME or starts services."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import uuid


class Refused(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Refused(message)


def git(repo, *args):
    p = subprocess.run(['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
                        '-c', 'core.fsmonitor=false', '-C', str(repo), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(p.returncode == 0, p.stderr.decode(errors='replace').strip())
    return p.stdout


def text(repo, *args):
    return git(repo, *args).decode().strip()


def pathcheck(value):
    p = PurePosixPath(value)
    require(value and not p.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/'))
            and '\\' not in value and '\x00' not in value, 'invalid relative path')
    require(not any(x.lower() in {'.git', '.ssh', '.gnupg', 'models', 'private', 'credentials', 'tokens'}
                    or x.lower().endswith(('.key', '.pem', '.gguf', '.safetensors')) for x in p.parts),
            'private/control path excluded: ' + value)
    return value


def leaf(repo, value):
    pathcheck(value)
    p = repo / value
    for parent in p.parents:
        if parent == repo:
            break
        require(not parent.is_symlink() and (not parent.exists() or parent.is_dir()),
                'unsafe source ancestor: ' + str(parent))
    return p


def identity(path):
    if not os.path.lexists(path):
        return {'kind': 'missing'}
    s = path.lstat()
    if stat.S_ISLNK(s.st_mode):
        return {'kind': 'symlink', 'link': os.readlink(path)}
    require(stat.S_ISREG(s.st_mode) and s.st_size <= 2 * 1024 * 1024, 'not a configuration leaf: ' + str(path))
    return {'kind': 'file', 'mode': stat.S_IMODE(s.st_mode),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def indexpath(repo):
    return Path(text(repo, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))


def entries(repo, *args):
    result = {}
    for record in git(repo, *args).split(b'\0'):
        if record:
            meta, name = record.split(b'\t', 1)
            fields = meta.decode().split()
            result[name.decode()] = fields
    return result


def capture(repo, paths):
    repo = Path(repo).absolute()
    require(repo.resolve() == repo and text(repo, 'rev-parse', '--show-toplevel') == str(repo), 'real worktree root required')
    idx = entries(repo, 'ls-files', '--stage', '-z')
    require(all(v[2] == '0' for v in idx.values()), 'unmerged index')
    # Only named review paths plus already-dirty tracked configuration leaves.
    # Gitlinks are opaque; never scan/hash ignored runtime files or AUR contents.
    dirty = git(repo, 'diff-files', '--name-only', '-z').decode().split('\0')
    known = sorted(set(paths) | {p for p in dirty if p and idx.get(p, [''])[0] != '160000'})
    return {'head': text(repo, 'rev-parse', 'HEAD'),
            'ref': text(repo, 'rev-parse', '--symbolic-full-name', 'HEAD'),
            'index_sha256': hashlib.sha256(indexpath(repo).read_bytes()).hexdigest(),
            'status': git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all').hex(),
            'leaves': {p: identity(leaf(repo, p)) for p in known}}


@contextlib.contextmanager
def locked(repo):
    lock = Path(text(repo, 'rev-parse', '--path-format=absolute', '--git-path', 'dotfiles-deploy.lock'))
    with lock.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def save(backup, state):
    temp = backup / 'state.next'
    temp.write_text(json.dumps(state, indent=2) + '\n')
    temp.replace(backup / 'state.json')


def load(backup):
    backup = Path(backup).absolute()
    require(backup.is_dir() and not backup.is_symlink() and backup.stat().st_uid == os.getuid()
            and backup.stat().st_mode & 0o077 == 0, 'private owned backup directory required')
    return backup, json.loads((backup / 'state.json').read_text())


def guard(repo, state):
    require(capture(repo, state['paths']) == state['expected'],
            'HEAD/index/status/source changed after snapshot; refusing (no force override)')


def prepare(repo, bundle, commit, manifest, baseline, backup, branch):
    repo, bundle, backup = Path(repo).absolute(), Path(bundle).absolute(), Path(backup).absolute()
    require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit) is not None, 'full lowercase commit ID required')
    require(bundle.is_file() and not bundle.is_symlink(), 'local bundle file required')
    paths = [pathcheck(e['path']) for e in manifest]
    require(paths and len(paths) == len(set(paths)), 'nonempty unique reviewed manifest required')
    require(all(e.get('phase') in ('source', 'entrypoint') for e in manifest), 'explicit source/entrypoint phases required')
    require(all(not (a != b and b.startswith(a + '/')) for a in paths for b in paths), 'ancestor path transition requires separate reviewed migration')
    require(set(paths) <= set(baseline['leaves']), 'missing reviewed before hashes')
    require(not backup.exists() and not backup.is_relative_to(repo), 'fresh backup outside source repository required')
    text(repo, 'check-ref-format', '--branch', branch)
    require(not git(repo, 'for-each-ref', '--format=%(refname)', 'refs/heads/' + branch).strip(), 'branch already exists')
    with locked(repo):
        require(capture(repo, paths) == baseline, 'baseline mismatch; obtain owner review of new snapshot')
        for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
            require(not Path(text(repo, 'rev-parse', '--path-format=absolute', '--git-path', marker)).exists(), 'unfinished Git operation: ' + marker)
        git(repo, 'bundle', 'verify', str(bundle))
        advertised = {line.split()[0] for line in text(repo, 'bundle', 'list-heads', str(bundle)).splitlines()}
        require(commit in advertised, 'exact target commit must be advertised by bundle')
        token = uuid.uuid4().hex
        incoming = 'refs/dotfiles-sync/incoming/' + token
        git(repo, 'fetch', '--no-tags', '--no-write-fetch-head', str(bundle), commit + ':' + incoming)
        require(text(repo, 'rev-parse', incoming + '^{commit}') == commit, 'bundle target mismatch')
        git(repo, 'merge-base', '--is-ancestor', baseline['head'], commit)
        idx = entries(repo, 'ls-files', '--stage', '-z')
        tree = entries(repo, 'ls-tree', '-r', '-z', commit)
        changes = {p for p in set(idx) | set(tree)
                   if idx.get(p, [])[:2] != ([tree[p][0], tree[p][2]] if p in tree else [])}
        require(changes <= set(paths), 'manifest omits changed index paths: ' + repr(sorted(changes - set(paths))))
        for p in paths:
            require(p in idx or p in tree, 'manifest path not tracked: ' + p)
            require(idx.get(p, [''])[0] != '160000' and tree.get(p, [''])[0] != '160000', 'gitlink mutation forbidden')
            require(p in idx or identity(leaf(repo, p))['kind'] == 'missing', 'untracked/ignored collision: ' + p)
            require(p not in tree or tree[p][0] in ('100644', '100755', '120000'), 'unsupported target mode')
        require(capture(repo, paths) == baseline, 'new edit during bundle preflight')
        backup.mkdir(mode=0o700, parents=True)
        (backup / 'leaves').mkdir(mode=0o700)
        shutil.copyfile(indexpath(repo), backup / 'index')
        os.chmod(backup / 'index', 0o600)
        for p in paths:
            source = leaf(repo, p)
            if os.path.lexists(source):
                dest = backup / 'leaves' / p
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest, follow_symlinks=False)
        oldref = 'refs/dotfiles-sync/backups/' + token
        git(repo, 'update-ref', oldref, baseline['head'], '0' * len(commit))
        state = {'version': 1, 'repo': str(repo), 'target': commit, 'branch': branch,
                 'incoming_ref': incoming, 'old_ref': oldref, 'before': baseline, 'expected': baseline,
                 'paths': paths, 'manifest': manifest, 'target_paths': sorted(tree), 'done': [], 'phase': 'prepared'}
        save(backup, state)
    return state


def status_except(snapshot, selected):
    records = bytes.fromhex(snapshot['status']).split(b'\0')
    result = []
    i = 0
    while i < len(records) and records[i]:
        record = records[i]
        name = record[3:].decode()
        i += 1
        extra = b''
        if record[:1] in (b'R', b'C') or record[1:2] in (b'R', b'C'):
            extra = records[i]
            i += 1
        if name != selected and extra.decode() != selected:
            result.append((record, extra))
    return result


def advance(backup, phase):
    backup, state = load(backup)
    repo = Path(state['repo'])
    with locked(repo):
        guard(repo, state)
        require(not state.get('retired_restored'), 'retired restoration started; rollback only')
        require((phase == 'source' and state['phase'] == 'prepared') or
                (phase == 'finalize' and state['phase'] == 'source'), 'invalid phase order')
        for entry in state['manifest']:
            p = entry['path']
            if p in state['done'] or (phase == 'source' and entry['phase'] != 'source'):
                continue
            guard(repo, state)
            previous = state['expected']
            old_index = entries(repo, 'ls-files', '--stage', '-z')
            source = leaf(repo, p)
            if p in state['target_paths']:
                # Git preserves executable bits and symlink objects. No directory checkout.
                git(repo, '--literal-pathspecs', 'checkout', state['target'], '--', p)
            else:
                if os.path.lexists(source):
                    dest = backup / 'retired' / p
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(dest)
                git(repo, '--literal-pathspecs', 'update-index', '--force-remove', '--', p)
            current = capture(repo, state['paths'])
            desired = {'kind': 'missing'}
            if p in state['target_paths']:
                target_entry = entries(repo, '--literal-pathspecs', 'ls-tree', '-z', state['target'], '--', p)[p]
                blob = git(repo, 'cat-file', 'blob', target_entry[2])
                if target_entry[0] == '120000':
                    desired = {'kind': 'symlink', 'link': os.fsdecode(blob)}
                else:
                    desired = {'kind': 'file', 'mode': 0o755 if target_entry[0] == '100755' else 0o644,
                               'sha256': hashlib.sha256(blob).hexdigest()}
            actual = current['leaves'][p].copy()
            if actual['kind'] == 'file':
                # Git records only the owner's executable bit, not POSIX rwx
                # permissions. Keep exact modes in current for guards/rollback.
                actual['mode'] = 0o755 if actual['mode'] & stat.S_IXUSR else 0o644
            require(actual == desired, 'selected source differs from target blob; retain backup')
            new_index = entries(repo, 'ls-files', '--stage', '-z')
            require(all(current[k] == previous[k] for k in ('head', 'ref'))
                    and {k: v for k, v in current['leaves'].items() if k != p}
                    == {k: v for k, v in previous['leaves'].items() if k != p}
                    and status_except(current, p) == status_except(previous, p)
                    and {k: v for k, v in old_index.items() if k != p}
                    == {k: v for k, v in new_index.items() if k != p},
                    'concurrent edit during path transition; retain backup for reviewed recovery')
            state['done'].append(p)
            state['expected'] = current
            save(backup, state)
        if phase == 'finalize':
            require(text(repo, 'write-tree') == text(repo, 'rev-parse', state['target'] + '^{tree}'), 'selected index does not equal target tree')
            # Checkout prepared every changed leaf; switch must not discard remaining dirt.
            git(repo, '-c', 'submodule.recurse=false', 'switch', '--no-recurse-submodules', '-c', state['branch'], state['target'])
            require(text(repo, 'rev-parse', 'HEAD') == state['target'], 'branch activation failed')
        state['phase'] = phase
        state['expected'] = capture(repo, state['paths'])
        save(backup, state)
    return state


def verify_originals(repo, backup, state):
    """Preflight every original needed by recovery, before any source write."""
    before = state['before']
    require(text(repo, 'rev-parse', state['old_ref']) == before['head'], 'backup ref changed')
    require(not (backup / 'index').is_symlink()
            and hashlib.sha256((backup / 'index').read_bytes()).hexdigest() == before['index_sha256'],
            'backup index changed')
    if before['ref'] != 'HEAD':
        require(text(repo, 'rev-parse', before['ref']) == before['head'], 'old branch moved')
    require((backup / 'leaves').is_dir() and not (backup / 'leaves').is_symlink(),
            'unsafe backup leaves directory')
    for p in state['paths']:
        require(identity(leaf(backup / 'leaves', p)) == before['leaves'][p], 'backup source changed: ' + p)


def restore_retired(backup):
    """Restore old referents without removing new assets or touching HEAD/index."""
    backup, state = load(backup)
    repo = Path(state['repo'])
    with locked(repo):
        require(state['phase'] != 'rolled-back', 'already rolled back')
        guard(repo, state)
        verify_originals(repo, backup, state)
        selected = [p for p in state['done'] if p not in state['target_paths']
                    and state['before']['leaves'][p]['kind'] != 'missing']
        # Even an idempotent retry verifies all recovery objects first. The moved
        # copies are retained too; never consume/rename either backup into source.
        if selected:
            require((backup / 'retired').is_dir() and not (backup / 'retired').is_symlink(),
                    'unsafe retired backup directory')
        for p in selected:
            require(identity(leaf(backup / 'retired', p)) == state['before']['leaves'][p],
                    'retired backup changed: ' + p)
        for p in selected:
            if p in state.get('retired_restored', []):
                continue
            guard(repo, state)
            previous = state['expected']
            require(previous['leaves'][p] == {'kind': 'missing'}, 'retired source is not missing: ' + p)
            old, dest = leaf(backup / 'leaves', p), leaf(repo, p)
            if os.path.lexists(old):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, dest, follow_symlinks=False)
            current = capture(repo, state['paths'])
            require(current['leaves'][p] == state['before']['leaves'][p]
                    and all(current[k] == previous[k] for k in ('head', 'ref', 'index_sha256'))
                    and {k: v for k, v in current['leaves'].items() if k != p}
                    == {k: v for k, v in previous['leaves'].items() if k != p}
                    and status_except(current, p) == status_except(previous, p),
                    'concurrent edit during retired restoration; retain backup for reviewed recovery')
            state.setdefault('retired_restored', []).append(p)
            state['expected'] = current
            save(backup, state)
    return state


def rollback(backup):
    backup, state = load(backup)
    repo = Path(state['repo'])
    with locked(repo):
        require(state['phase'] != 'rolled-back', 'already rolled back')
        guard(repo, state)
        before = state['before']
        verify_originals(repo, backup, state)
        # Preserve full old index including staged owner changes; a two-tree switch
        # here could reject that legitimate dirt. Restore exact leaves/index, then
        # explicitly restore HEAD's original symbolic binding without a checkout.
        for p in reversed(state['done']):
            dest = leaf(repo, p)
            old = backup / 'leaves' / p
            if os.path.lexists(dest):
                dest.unlink()
            if os.path.lexists(old):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, dest, follow_symlinks=False)
        shutil.copyfile(backup / 'index', indexpath(repo))
        before = state['before']
        require(text(repo, 'rev-parse', state['old_ref']) == before['head'], 'backup ref changed')
        if before['ref'] == 'HEAD':
            git(repo, 'update-ref', '--no-deref', 'HEAD', before['head'])
        else:
            require(text(repo, 'rev-parse', before['ref']) == before['head'], 'old branch moved')
            git(repo, 'symbolic-ref', 'HEAD', before['ref'])
        require(capture(repo, state['paths']) == before, 'rollback verification failed; retain backup')
        state['phase'] = 'rolled-back'
        state['expected'] = before
        save(backup, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--repo', required=True)
    c.add_argument('--manifest', required=True)
    p = sub.add_parser('prepare')
    for name in ('repo', 'bundle', 'commit', 'manifest', 'baseline', 'backup', 'branch'):
        p.add_argument('--' + name, required=True)
    for name in ('source', 'finalize', 'restore-retired', 'rollback'):
        sub.add_parser(name).add_argument('--backup', required=True)
    a = parser.parse_args()
    try:
        if a.command == 'capture':
            manifest = json.loads(Path(a.manifest).read_text())
            result = capture(a.repo, [e['path'] for e in manifest])
        elif a.command == 'prepare':
            result = prepare(a.repo, a.bundle, a.commit, json.loads(Path(a.manifest).read_text()),
                             json.loads(Path(a.baseline).read_text()), a.backup, a.branch)
        elif a.command == 'rollback':
            result = rollback(a.backup)
        elif a.command == 'restore-retired':
            result = restore_retired(a.backup)
        else:
            result = advance(a.backup, a.command)
        print(json.dumps(result, indent=2))
    except (Refused, OSError, KeyError) as e:
        parser.exit(2, 'REFUSED: ' + str(e) + '\n')


if __name__ == '__main__':
    main()
