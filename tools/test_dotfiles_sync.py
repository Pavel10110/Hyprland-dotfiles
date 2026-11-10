import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('sync', HERE / 'dotfiles_sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.repo = self.root / 'dotfiles'
        self.home.mkdir()
        self.repo.mkdir()
        (self.home / '.config').mkdir()
        (self.home / '.config/dotfiles-host').write_text('pc\n')
        self.source = self.repo / 'hypr/.config/hypr/test.conf'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('new\n')
        self.source.chmod(0o640)
        self.target = self.home / '.config/hypr/test.conf'
        self.target.parent.mkdir()

    def manifest(self, kind='symlink'):
        return {'version': 1, 'host': 'pc', 'files': [{
            'source': str(self.source.relative_to(self.repo)),
            'target': str(self.target.relative_to(self.home)),
            'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'mode': 0o640, 'kind': kind, 'before': sync.snapshot(self.target)}]}

    def apply(self, manifest, dry_run=False):
        return sync.install(self.home, self.repo, manifest, dry_run=dry_run)

    def test_existing_file_backup_restore_mode_and_idempotence(self):
        self.target.write_text('old\n')
        self.target.chmod(0o600)
        m = self.manifest()
        run = self.apply(m)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.target.read_text(), 'new\n')
        self.assertIsNone(self.apply(m))
        sync.rollback(self.home, run)
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(self.target.read_text(), 'old\n')
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        sync.rollback(self.home, run)

    def test_existing_and_broken_symlink_retained(self):
        for dest in ['missing', str(self.source)]:
            with self.subTest(dest=dest):
                self.target.symlink_to(dest)
                m = self.manifest(kind='copy')
                run = self.apply(m)
                self.assertFalse(self.target.is_symlink())
                self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)
                sync.rollback(self.home, run)
                self.assertEqual(os.readlink(self.target), dest)
                self.target.unlink()

    def test_dry_run_does_not_write(self):
        m = self.manifest()
        self.assertIsNone(self.apply(m, dry_run=True))
        self.assertFalse(self.target.exists())
        self.assertFalse((self.home / '.local').exists())

    def test_wrong_host_traversal_secret_and_parent_symlink_rejected(self):
        for field, value in [('host', 'laptop'), ('target', '../escape'),
                             ('source', '../escape'), ('target', '.ssh/config'),
                             ('source', 'githubssh')]:
            m = self.manifest()
            if field == 'host':
                m[field] = value
            else:
                m['files'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(sync.Refused):
                self.apply(m)
        outside = self.root / 'outside'
        outside.mkdir()
        self.target.parent.rmdir()
        self.target.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(sync.Refused):
            self.apply(self.manifest())
        self.assertEqual(list(outside.iterdir()), [])

    def test_conflict_source_hash_and_mode_guard(self):
        m = self.manifest()
        self.target.write_text('unexpected')
        with self.assertRaises(sync.Refused):
            self.apply(m)
        self.target.unlink()
        self.source.write_text('changed')
        with self.assertRaises(sync.Refused):
            self.apply(m)
        self.source.write_text('new\n')
        self.source.chmod(0o600)
        with self.assertRaises(sync.Refused):
            self.apply(m)

    def test_changed_before_rollback_refused(self):
        self.target.write_text('original')
        m = self.manifest('copy')
        run = self.apply(m)
        self.target.write_text('user edit')
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)
        self.assertEqual(self.target.read_text(), 'user edit')
        self.assertTrue((run / 'objects/0').exists())

    def test_referent_change_before_rollback_refused(self):
        run = self.apply(self.manifest())
        self.source.write_text('edited repository')
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)

    def test_missing_file_rollback_and_private_backups(self):
        run = self.apply(self.manifest('copy'))
        self.assertEqual(run.stat().st_mode & 0o777, 0o700)
        self.assertEqual((run / 'journal.json').stat().st_mode & 0o777, 0o600)
        sync.rollback(self.home, run)
        self.assertFalse(os.path.lexists(self.target))

    def test_duplicate_and_ancestor_targets_rejected(self):
        m = self.manifest()
        m['files'].append(dict(m['files'][0]))
        with self.assertRaises(sync.Refused):
            self.apply(m)
        m['files'][1]['target'] = '.config/hypr'
        with self.assertRaises(sync.Refused):
            self.apply(m)

    def test_relative_symlink_restore_and_referent_edit_preflight(self):
        old = self.target.parent / 'old.conf'
        old.write_text('old referent')
        self.target.symlink_to('old.conf')
        run = self.apply(self.manifest('copy'))
        old.write_text('edited referent')
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)
        self.assertFalse(self.target.is_symlink())
        old.write_text('old referent')
        sync.rollback(self.home, run)
        self.assertEqual(os.readlink(self.target), 'old.conf')
        self.assertTrue((run / 'objects/0').is_symlink())

    def test_deletion_and_second_rollback_user_edit_refused(self):
        self.target.write_text('old')
        run = self.apply(self.manifest('copy'))
        self.target.unlink()
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)
        self.target.write_text('new\n')
        self.target.chmod(0o640)
        sync.rollback(self.home, run)
        self.target.write_text('post rollback edit')
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)

    def test_wrong_owner_rejected(self):
        from unittest.mock import patch
        uid = os.getuid()
        with patch.object(sync.os, 'getuid', return_value=uid + 1):
            with self.assertRaises(sync.Refused):
                self.apply(self.manifest())

    def test_source_symlink_and_sensitive_referent_rejected(self):
        m = self.manifest()
        real = self.source.with_suffix('.real')
        self.source.rename(real)
        self.source.symlink_to(real)
        with self.assertRaises(sync.Refused):
            self.apply(m)
        secret = self.home / '.ssh/config'
        secret.parent.mkdir()
        secret.write_text('fixture only')
        self.target.symlink_to(secret)
        with self.assertRaises(sync.Refused):
            sync.snapshot(self.target)
        self.target.unlink()
        self.target.symlink_to(self.home / 'githubssh')
        with self.assertRaises(sync.Refused):
            sync.snapshot(self.target)

    def test_sensitive_suffix_referents_refused_before_digest_or_read(self):
        from unittest.mock import patch
        for suffix in ('.pem', '.key', '.bin', '.gguf', '.safetensors'):
            for exists in (True, False):
                with self.subTest(suffix=suffix, exists=exists):
                    fake = self.home / ('fixture' + suffix)
                    if exists:
                        fake.write_text('fake fixture only, not private material')
                    self.target.symlink_to(fake)
                    try:
                        with patch.object(sync, 'digest') as digest, \
                                patch.object(Path, 'read_bytes') as read:
                            with self.assertRaisesRegex(sync.Refused, 'sensitive symlink referent'):
                                sync.snapshot(self.target)
                            digest.assert_not_called()
                            read.assert_not_called()
                    finally:
                        self.target.unlink()
                        if exists:
                            fake.unlink()

    def test_inter_target_relative_referents_refused_before_any_write(self):
        for exists in (True, False):
            for reverse in (False, True):
                with self.subTest(exists=exists, reverse=reverse):
                    other = self.target.parent / 'second.conf'
                    if exists:
                        other.write_text('old second')
                    self.target.symlink_to('second.conf')
                    m = self.manifest('copy')
                    m['files'].append(dict(m['files'][0],
                                          target=str(other.relative_to(self.home)),
                                          before=sync.snapshot(other)))
                    if reverse:
                        m['files'].reverse()
                    before = [sync.snapshot(self.target), sync.snapshot(other)]
                    try:
                        for dry_run in (False, True):
                            with self.assertRaisesRegex(sync.Refused, 'inter-target referent dependency'):
                                self.apply(m, dry_run=dry_run)
                            self.assertEqual([sync.snapshot(self.target), sync.snapshot(other)], before)
                            self.assertFalse((self.home / '.local').exists())
                    finally:
                        self.target.unlink()
                        if os.path.lexists(other):
                            other.unlink()

    def test_independent_multi_leaf_rollback_both_orders(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                old = self.target.parent / 'old.conf'
                old.write_text('independent old referent')
                self.target.symlink_to('old.conf')
                other = self.target.parent / 'second.conf'
                other.write_text('old second')
                other.chmod(0o600)
                missing = self.target.parent / 'third.conf'
                m = self.manifest('copy')
                for target in (other, missing):
                    m['files'].append(dict(m['files'][0],
                                          target=str(target.relative_to(self.home)),
                                          before=sync.snapshot(target)))
                if reverse:
                    m['files'].reverse()
                before = [sync.snapshot(t) for t in (self.target, other, missing)]
                run = self.apply(m)
                self.assertTrue(sync.check(self.home, self.repo, m))
                sync.rollback(self.home, run)
                self.assertEqual([sync.snapshot(t) for t in (self.target, other, missing)], before)
                self.assertEqual(os.readlink(self.target), 'old.conf')
                sync.rollback(self.home, run)
                self.target.unlink()
                other.unlink()
                old.unlink()

    def test_backup_tamper_refused(self):
        self.target.write_text('old')
        run = self.apply(self.manifest('copy'))
        (run / 'objects/0').write_text('tamper')
        with self.assertRaises(sync.Refused):
            sync.rollback(self.home, run)
        self.assertEqual(self.target.read_text(), 'new\n')

    def test_incomplete_operation_recoverable(self):
        from unittest.mock import patch
        self.target.write_text('old')
        m = self.manifest()
        with patch.object(sync, 'create', side_effect=OSError('fixture interruption')):
            with self.assertRaises(sync.Refused):
                self.apply(m)
        runs = list((self.home / sync.STATE).glob('*/journal.json'))
        self.assertEqual(len(runs), 1)
        sync.rollback(self.home, runs[0].parent)
        self.assertEqual(self.target.read_text(), 'old')
        self.assertEqual((runs[0].parent / 'objects/0').read_text(), 'old')

    def test_all_conflicts_preflight_before_writes(self):
        m = self.manifest()
        second = dict(m['files'][0], target='.config/hypr/second.conf')
        m['files'].append(second)
        (self.target.parent / 'second.conf').write_text('unreviewed')
        with self.assertRaises(sync.Refused):
            self.apply(m)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.home / sync.STATE).exists())

    def test_unsafe_state_symlink_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.home / '.local').symlink_to(outside)
        with self.assertRaises(sync.Refused):
            self.apply(self.manifest())
        self.assertEqual(list(outside.iterdir()), [])

    def test_cli_inspect_dry_run_sync_check_and_rollback(self):
        import subprocess
        self.target.write_text('old')
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps(self.manifest('copy')))
        base = ['sh', str(HERE / 'dotfiles-sync')]
        options = ['--home', str(self.home), '--repo', str(self.repo),
                   '--manifest', str(manifest)]

        def run(command, extra=(), code=0):
            result = subprocess.run(base + [command] + options + list(extra),
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, code, result.stderr)
            return result.stdout.strip()

        before = run('inspect', ['--target', '.config/hypr/test.conf'])
        self.assertEqual(json.loads(before), sync.snapshot(self.target))
        run('check', code=1)
        self.assertEqual(run('install', ['--dry-run']), 'dry-run preflight passed')
        self.assertEqual(self.target.read_text(), 'old')
        path = run('sync')
        self.assertTrue(Path(path).is_dir())
        self.assertEqual(run('check'), 'installed and verified')
        self.assertEqual(run('install'), 'already installed; no changes')
        run('rollback', ['--run', path])
        self.assertEqual(self.target.read_text(), 'old')
        bad = json.loads(manifest.read_text())
        bad['host'] = 'laptop'
        manifest.write_text(json.dumps(bad))
        run('install', code=2)

    def test_laptop_host_success_and_missing_marker(self):
        m = self.manifest()
        (self.home / sync.MARKER).unlink()
        with self.assertRaises(sync.Refused):
            self.apply(m)
        (self.home / sync.MARKER).write_text('laptop\n')
        m['host'] = 'laptop'
        run = self.apply(m)
        self.assertTrue(sync.check(self.home, self.repo, m))
        sync.rollback(self.home, run)

    def test_check_and_host_specific_package(self):
        m = self.manifest()
        self.assertFalse(sync.check(self.home, self.repo, m))
        self.apply(m)
        self.assertTrue(sync.check(self.home, self.repo, m))
        m['files'][0]['source'] = 'host-laptop/.config/hypr/host.conf'
        with self.assertRaises(sync.Refused):
            self.apply(m)


if __name__ == '__main__':
    unittest.main(verbosity=2)
