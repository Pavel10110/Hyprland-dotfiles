import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('deploy_repo', Path(__file__).with_name('deploy_repo.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.STDOUT).decode().strip()


class Deployment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        git(self.repo, 'init', '-b', 'main')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        git(self.repo, 'config', 'user.name', 'Fixture')
        for name, text in {'.gitignore': 'private/\n', 'entry': 'old\n', 'obsolete': 'retire\n', 'dirty': 'base\n', 'staged': 'base\n'}.items():
            (self.repo / name).write_text(text)
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'update-index', '--add', '--cacheinfo', '160000,' + self.base + ',aur/paru')
        git(self.repo, 'commit', '-m', 'gitlink')
        self.old = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'clone', '--no-hardlinks', str(self.repo), str(self.root / 'author'))
        author = self.root / 'author'
        git(author, 'config', 'user.email', 'fixture@example.invalid')
        git(author, 'config', 'user.name', 'Fixture')
        (author / 'asset').write_text('dependency\n')
        (author / 'asset').chmod(0o755)
        (author / 'relative').symlink_to('asset')
        (author / 'entry').write_text('merged dirty owner choice\n')
        git(author, 'rm', 'obsolete')
        git(author, 'add', '.')
        git(author, 'commit', '-m', 'reviewed')
        self.target = git(author, 'rev-parse', 'HEAD')
        self.bundle = self.root / 'final.bundle'
        git(author, 'bundle', 'create', str(self.bundle), 'HEAD')
        (self.repo / 'entry').write_text('dirty owner choice\n')
        (self.repo / 'dirty').write_text('retained unstaged\n')
        (self.repo / 'staged').write_text('retained staged\n')
        git(self.repo, 'add', 'staged')
        # Target must include the original staged content, otherwise finalization
        # cannot truthfully claim its index equals the reviewed target tree.
        (author / 'staged').write_text('retained staged\n')
        git(author, 'add', 'staged')
        git(author, 'commit', '-m', 'include reviewed staged change')
        git(author, 'branch', 'desktop-final')
        git(author, 'checkout', '-b', 'laptop-history', self.base)
        (author / 'host-asset').write_text('other host history\n')
        git(author, 'add', 'host-asset')
        git(author, 'commit', '-m', 'independent laptop history')
        self.laptop = git(author, 'rev-parse', 'HEAD')
        git(author, 'checkout', 'desktop-final')
        git(author, 'merge', '--no-ff', 'laptop-history', '-m', 'preserve both histories')
        self.target = git(author, 'rev-parse', 'HEAD')
        self.bundle.unlink()
        git(author, 'bundle', 'create', str(self.bundle), 'HEAD')
        (self.repo / 'private').mkdir()
        (self.repo / 'private/secret.key').write_text('DO NOT READ OR TOUCH')
        (self.repo / 'untracked').write_text('keep')
        # Real populated, dirty submodule; its commit is unchanged by deployment.
        sub = self.repo / 'aur/paru'
        sub.mkdir(parents=True)
        git(sub, 'init')
        git(sub, 'fetch', str(self.repo), self.base)
        git(sub, 'checkout', self.base)
        (sub / 'dirty').write_text('dirty AUR source\n')
        self.paths = [{'path': 'host-asset', 'phase': 'source'}, {'path': 'asset', 'phase': 'source'}, {'path': 'relative', 'phase': 'source'},
                      {'path': 'entry', 'phase': 'entrypoint'}, {'path': 'obsolete', 'phase': 'entrypoint'}]
        self.baseline = d.capture(self.repo, [x['path'] for x in self.paths])
        self.backup = self.root / 'backup'

    def prepare(self):
        return d.prepare(self.repo, self.bundle, self.target, self.paths, self.baseline, self.backup, 'reviewed-final')

    def test_roundtrip(self):
        before = d.capture(self.repo, [x['path'] for x in self.paths])
        self.prepare()
        d.advance(self.backup, 'source')
        self.assertEqual((self.repo / 'entry').read_text(), 'dirty owner choice\n')
        self.assertTrue((self.repo / 'relative').is_symlink())
        d.advance(self.backup, 'finalize')
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), self.target)
        git(self.repo, 'merge-base', '--is-ancestor', self.old, self.target)
        git(self.repo, 'merge-base', '--is-ancestor', self.laptop, self.target)
        self.assertEqual(len(git(self.repo, 'rev-list', '--parents', '-n', '1', self.target).split()), 3)
        self.assertEqual(git(self.repo, 'write-tree'), git(self.repo, 'rev-parse', self.target + '^{tree}'))
        self.assertIn('dirty', git(self.repo, 'status', '--porcelain'))
        self.assertEqual((self.repo / 'asset').stat().st_mode & 0o777, 0o755)
        self.assertFalse((self.repo / 'obsolete').exists())
        self.assertTrue((self.backup / 'leaves/obsolete').exists())
        d.rollback(self.backup)
        self.assertEqual(d.capture(self.repo, [x['path'] for x in self.paths]), before)
        self.assertEqual((self.repo / 'private/secret.key').read_text(), 'DO NOT READ OR TOUCH')
        self.assertEqual((self.repo / 'aur/paru/dirty').read_text(), 'dirty AUR source\n')
        self.assertEqual((self.repo / 'untracked').read_text(), 'keep')

    def umask_roundtrip(self, mask):
        # Noncanonical original permissions must survive exact snapshot/rollback;
        # target permissions, unlike snapshots, follow Git plus the caller's umask.
        for name, mode in {'entry': 0o604, 'obsolete': 0o640,
                           'dirty': 0o600, 'staged': 0o660}.items():
            (self.repo / name).chmod(mode)
        self.baseline = d.capture(self.repo, [x['path'] for x in self.paths])
        old_mask = os.umask(mask)
        try:
            self.prepare()
            source = d.advance(self.backup, 'source')
            self.assertEqual(source['phase'], 'source')
            self.assertEqual(d.capture(self.repo, source['paths']), source['expected'])
            self.assertEqual((self.repo / 'entry').read_text(), 'dirty owner choice\n')
            self.assertEqual((self.repo / 'entry').stat().st_mode & 0o7777, 0o604)
            self.assertEqual((self.repo / 'host-asset').stat().st_mode & 0o7777, 0o666 & ~mask)
            self.assertEqual((self.repo / 'asset').stat().st_mode & 0o7777, 0o777 & ~mask)
            self.assertTrue((self.repo / 'relative').is_symlink())
            final = d.advance(self.backup, 'finalize')
            self.assertEqual(final['phase'], 'finalize')
            self.assertEqual(d.capture(self.repo, final['paths']), final['expected'])
            self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), self.target)
            self.assertEqual(git(self.repo, 'write-tree'), git(self.repo, 'rev-parse', self.target + '^{tree}'))
            self.assertEqual((self.repo / 'entry').stat().st_mode & 0o7777, 0o666 & ~mask)
            self.assertFalse((self.repo / 'obsolete').exists())
            restored = d.rollback(self.backup)
            self.assertEqual(restored['phase'], 'rolled-back')
            self.assertEqual(d.capture(self.repo, restored['paths']), self.baseline)
            self.assertEqual((self.repo / 'private/secret.key').read_text(), 'DO NOT READ OR TOUCH')
            self.assertEqual((self.repo / 'aur/paru/dirty').read_text(), 'dirty AUR source\n')
            self.assertEqual((self.repo / 'untracked').read_text(), 'keep')
        finally:
            os.umask(old_mask)

    def test_umask_0002_roundtrip(self):
        self.umask_roundtrip(0o002)

    def test_umask_0027_roundtrip(self):
        self.umask_roundtrip(0o027)

    def test_umask_0077_roundtrip(self):
        self.umask_roundtrip(0o077)

    def test_checkout_rejects_wrong_executable_bit(self):
        self.prepare()
        original = d.git
        def wrong_mode(repo, *args):
            result = original(repo, *args)
            if 'checkout' in args and args[-1] == 'asset':
                (self.repo / 'asset').chmod(0o644)
            return result
        from unittest.mock import patch
        with patch.object(d, 'git', wrong_mode):
            with self.assertRaisesRegex(d.Refused, 'selected source differs from target blob'):
                d.advance(self.backup, 'source')

    def test_rollback_refuses_permission_only_edit(self):
        self.prepare()
        d.advance(self.backup, 'source')
        source = self.repo / 'host-asset'
        source.chmod((source.stat().st_mode & 0o7777) ^ 0o020)
        changed = d.capture(self.repo, [x['path'] for x in self.paths])
        with self.assertRaisesRegex(d.Refused, 'HEAD/index/status/source changed'):
            d.rollback(self.backup)
        self.assertEqual(d.capture(self.repo, [x['path'] for x in self.paths]), changed)

    def test_restore_retired_preserves_symlink_literal_and_new_assets(self):
        obsolete = self.repo / 'obsolete'
        obsolete.unlink()
        obsolete.symlink_to('./entry')
        self.baseline = d.capture(self.repo, [x['path'] for x in self.paths])
        self.prepare()
        d.advance(self.backup, 'source')
        d.advance(self.backup, 'finalize')
        final = d.capture(self.repo, [x['path'] for x in self.paths])
        restored = d.restore_retired(self.backup)
        self.assertEqual(os.readlink(obsolete), './entry')
        self.assertEqual(os.readlink(self.backup / 'leaves/obsolete'), './entry')
        self.assertEqual(os.readlink(self.backup / 'retired/obsolete'), './entry')
        for name, identity in final['leaves'].items():
            if name != 'obsolete':
                self.assertEqual(restored['expected']['leaves'][name], identity)
        self.assertEqual((self.repo / 'entry').read_text(), 'merged dirty owner choice\n')
        self.assertEqual(restored, d.restore_retired(self.backup))
        d.rollback(self.backup)
        self.assertEqual(d.capture(self.repo, [x['path'] for x in self.paths]), self.baseline)

    def test_restore_retired_missing_original_is_noop(self):
        (self.repo / 'obsolete').unlink()
        self.baseline = d.capture(self.repo, [x['path'] for x in self.paths])
        self.prepare()
        d.advance(self.backup, 'source')
        final = d.advance(self.backup, 'finalize')
        self.assertEqual(d.restore_retired(self.backup), final)
        d.rollback(self.backup)
        self.assertEqual(d.capture(self.repo, [x['path'] for x in self.paths]), self.baseline)

    def test_restore_retired_rejects_edit_on_idempotent_retry(self):
        self.prepare()
        d.advance(self.backup, 'source')
        d.advance(self.backup, 'finalize')
        d.restore_retired(self.backup)
        (self.repo / 'obsolete').write_text('edited restored original\n')
        changed = d.capture(self.repo, [x['path'] for x in self.paths])
        with self.assertRaisesRegex(d.Refused, 'HEAD/index/status/source changed'):
            d.restore_retired(self.backup)
        self.assertEqual(d.capture(self.repo, [x['path'] for x in self.paths]), changed)

    def test_snapshot_guard(self):
        (self.repo / 'entry').write_text('edit after review')
        with self.assertRaises(d.Refused):
            self.prepare()
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), self.old)

    def test_rollback_refuses_edit(self):
        self.prepare()
        d.advance(self.backup, 'source')
        d.advance(self.backup, 'finalize')
        (self.repo / 'entry').write_text('intervening user edit')
        with self.assertRaises(d.Refused):
            d.rollback(self.backup)
        self.assertEqual((self.repo / 'entry').read_text(), 'intervening user edit')

    def test_wrong_commit(self):
        with self.assertRaises(d.Refused):
            d.prepare(self.repo, self.bundle, 'deadbeef', self.paths, self.baseline, self.backup, 'reviewed-final')

    def test_incomplete_manifest(self):
        with self.assertRaises(d.Refused):
            d.prepare(self.repo, self.bundle, self.target, self.paths[:-1], self.baseline, self.backup, 'reviewed-final')

    def test_untracked_collision(self):
        (self.repo / 'asset').write_text('untracked user file')
        self.baseline = d.capture(self.repo, [x['path'] for x in self.paths])
        with self.assertRaises(d.Refused):
            self.prepare()

    def test_edit_during_checkout_is_not_absorbed(self):
        self.prepare()
        original = d.git
        def concurrent(repo, *args):
            result = original(repo, *args)
            if 'checkout' in args:
                (self.repo / 'dirty').write_text('edit during checkout')
            return result
        from unittest.mock import patch
        with patch.object(d, 'git', concurrent):
            with self.assertRaises(d.Refused):
                d.advance(self.backup, 'source')
        self.assertEqual((self.repo / 'dirty').read_text(), 'edit during checkout')

    def test_rollback_refuses_moved_old_branch_before_writes(self):
        self.prepare()
        d.advance(self.backup, 'source')
        d.advance(self.backup, 'finalize')
        git(self.repo, 'update-ref', 'refs/heads/main', self.base)
        with self.assertRaises(d.Refused):
            d.rollback(self.backup)
        self.assertEqual((self.repo / 'entry').read_text(), 'merged dirty owner choice\n')
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), self.target)

    def test_private_manifest_refused(self):
        with self.assertRaises(d.Refused):
            d.capture(self.repo, ['private/secret.key'])

    def test_source_phase_edit_guard(self):
        self.prepare()
        d.advance(self.backup, 'source')
        (self.repo / 'dirty').write_text('new unrelated edit')
        # Status alone is unchanged: content guard must catch tracked dirty edits.
        with self.assertRaises(d.Refused):
            d.advance(self.backup, 'finalize')


if __name__ == '__main__':
    unittest.main(verbosity=2)
