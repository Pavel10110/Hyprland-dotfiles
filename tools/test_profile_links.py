import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import profile_links as p


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        (self.home / '.config').mkdir()
        self.repo = self.home / 'dotfiles'
        self.repo.mkdir()
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        self.marker = self.root / 'host'
        self.marker.write_text('pc\n')
        self.journal = self.private / 'run'
        self.manifest = {'version': 1, 'host': 'pc', 'files': []}
        for name in ('swaync', 'fastfetch'):
            old = self.repo / name / '.config' / name
            old.mkdir(parents=True)
            (old / 'sentinel').write_text('untouched')
            new = self.repo / 'host-pc' / '.config' / name
            new.mkdir(parents=True)
            literal = f'../dotfiles/{name}/.config/{name}'
            (self.home / '.config' / name).symlink_to(literal)
            self.manifest['files'].append({'target': f'.config/{name}', 'before_link': literal,
                                          'source': f'host-pc/.config/{name}'})

    def run_action(self, action='apply'):
        return p.run(action, self.home, self.repo, self.journal, 'pc', self.marker, self.manifest)

    def literals(self):
        return [os.readlink(self.home / f['target']) for f in self.manifest['files']]

    def test_apply_check_repeat_and_exact_rollback(self):
        originals = self.literals()
        resolved = [(self.home / f['target']).resolve() for f in self.manifest['files']]
        self.assertEqual(self.run_action('check')['state'], 'old')
        self.assertEqual(self.run_action()['changed'], 2)
        self.assertEqual(self.run_action()['changed'], 0)
        self.assertEqual(self.run_action('check')['state'], 'installed')
        self.assertEqual(self.run_action('rollback')['changed'], 2)
        self.assertEqual(self.literals(), originals)
        self.assertEqual([(self.home / f['target']).resolve() for f in self.manifest['files']], resolved)
        self.assertEqual(self.run_action('rollback')['changed'], 0)
        self.assertEqual(len(list((self.journal / 'backups').iterdir())), 2)
        for folder in resolved:
            self.assertEqual((folder / 'sentinel').read_text(), 'untouched')

    def test_stale_second_refuses_before_any_write(self):
        target = self.home / '.config/fastfetch'
        target.unlink()
        target.symlink_to('unknown')
        before = self.literals()
        with self.assertRaises(p.Refusal):
            self.run_action()
        self.assertEqual(self.literals(), before)
        self.assertFalse(self.journal.exists())

    def test_mixed_without_journal_refuses(self):
        target = self.home / '.config/fastfetch'
        target.unlink()
        target.symlink_to('../dotfiles/host-pc/.config/fastfetch')
        with self.assertRaises(p.Refusal):
            self.run_action()
        self.assertFalse(self.journal.exists())

    def test_external_edit_rollback_all_or_nothing(self):
        self.run_action()
        target = self.home / '.config/fastfetch'
        target.unlink()
        target.symlink_to('external')
        before = self.literals()
        with self.assertRaises(p.Refusal):
            self.run_action('rollback')
        self.assertEqual(self.literals(), before)

    def test_resume_partial_apply_and_partial_rollback(self):
        real = p.replace_link
        counter = 0
        def interrupted(*args):
            nonlocal counter
            counter += 1
            if counter == 2:
                raise OSError('simulated interruption')
            return real(*args)
        with patch.object(p, 'replace_link', interrupted):
            with self.assertRaises(OSError):
                self.run_action()
        self.assertEqual(self.run_action('check')['state'], 'partial')
        self.assertEqual(self.run_action()['changed'], 1)
        counter = 0
        with patch.object(p, 'replace_link', interrupted):
            with self.assertRaises(OSError):
                self.run_action('rollback')
        self.assertEqual(self.run_action('rollback')['changed'], 1)

    def test_unsafe_parent(self):
        (self.home / '.config').chmod(0o777)
        with self.assertRaises(p.Refusal):
            self.run_action()
        self.assertFalse(self.journal.exists())

    def test_source_symlink_refused(self):
        folder = self.repo / 'host-pc/.config/swaync'
        folder.rmdir()
        folder.symlink_to(self.repo / 'swaync/.config/swaync')
        with self.assertRaises(p.Refusal):
            self.run_action()

    def test_host_and_manifest_guards(self):
        for host in ('laptop', 'bogus'):
            self.manifest['host'] = host
            with self.assertRaises(p.Refusal):
                self.run_action()
        self.manifest['host'] = 'pc'
        self.marker.write_text('laptop\n')
        with self.assertRaises(p.Refusal):
            self.run_action()
        self.assertFalse(self.journal.exists())

    def test_original_backup_objects_retained(self):
        inodes = [(self.home / e['target']).lstat().st_ino for e in self.manifest['files']]
        self.run_action()
        for i, inode in enumerate(inodes):
            self.assertEqual((self.journal / 'backups' / str(i)).lstat().st_ino, inode)
        self.run_action('rollback')
        for i, inode in enumerate(inodes):
            self.assertEqual((self.journal / 'backups' / str(i)).lstat().st_ino, inode)

    def test_ascii_asset_alias_not_traversed_or_replaced(self):
        alias = self.repo / 'host-pc/.config/fastfetch/ascii'
        alias.symlink_to('../../../fastfetch/.config/fastfetch/ascii')
        original = (os.readlink(alias), alias.lstat().st_ino)
        self.run_action()
        self.run_action('rollback')
        self.assertEqual((os.readlink(alias), alias.lstat().st_ino), original)

    def test_unsafe_source_or_private_anchor(self):
        for folder in (self.repo / 'host-pc/.config', self.private, self.home, self.repo):
            original = folder.stat().st_mode & 0o777
            folder.chmod(0o777)
            try:
                with self.assertRaises(p.Refusal):
                    self.run_action()
                self.assertFalse(self.journal.exists())
            finally:
                folder.chmod(original)

    def test_real_directory_target_and_symlink_marker_refused(self):
        target = self.home / '.config/fastfetch'
        target.unlink()
        target.mkdir()
        with self.assertRaises(p.Refusal):
            self.run_action()
        target.rmdir()
        target.symlink_to('../dotfiles/fastfetch/.config/fastfetch')
        marker_real = self.root / 'marker-real'
        self.marker.rename(marker_real)
        self.marker.symlink_to(marker_real)
        with self.assertRaises(p.Refusal):
            self.run_action()
        self.assertFalse(self.journal.exists())

    def test_manifest_scope_and_journal_binding(self):
        entry = self.manifest['files'][0]
        for key, value in [('target', '.config/other'), ('source', 'host-laptop/.config/swaync'),
                           ('before_link', '/outside')]:
            previous = entry[key]
            entry[key] = value
            with self.assertRaises(p.Refusal):
                self.run_action()
            entry[key] = previous
        self.run_action()
        log = self.journal / 'journal.json'
        record = json.loads(log.read_text())
        record['home'] = '/different-home'
        log.write_text(json.dumps(record))
        before = self.literals()
        with self.assertRaises(p.Refusal):
            self.run_action('rollback')
        self.assertEqual(self.literals(), before)

    def test_cli_fixture_roundtrip(self):
        manifest = self.private / 'manifest.json'
        manifest.write_text(json.dumps(self.manifest))
        command = [sys.executable, str(Path(p.__file__)), '--host', 'pc', '--home', str(self.home),
                   '--repo', str(self.repo), '--journal', str(self.journal), '--host-marker',
                   str(self.marker), '--manifest', str(manifest)]
        for action, changed in [('check', 0), ('apply', 2), ('apply', 0), ('rollback', 2)]:
            result = subprocess.run(command + [action], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['changed'], changed)

    def test_laptop_one_link(self):
        self.marker.write_text('laptop\n')
        folder = self.repo / 'host-laptop/.config/swaync'
        folder.mkdir(parents=True)
        self.manifest['host'] = 'laptop'
        self.manifest['files'] = [dict(self.manifest['files'][0], source='host-laptop/.config/swaync')]
        result = p.run('apply', self.home, self.repo, self.journal, 'laptop', self.marker, self.manifest)
        self.assertEqual(result['changed'], 1)
        self.assertEqual(os.readlink(self.home / '.config/swaync'), '../dotfiles/host-laptop/.config/swaync')
        result = p.run('rollback', self.home, self.repo, self.journal, 'laptop', self.marker, self.manifest)
        self.assertEqual(result['changed'], 1)
        self.assertEqual(os.readlink(self.home / '.config/swaync'), '../dotfiles/swaync/.config/swaync')


if __name__ == '__main__':
    unittest.main()
