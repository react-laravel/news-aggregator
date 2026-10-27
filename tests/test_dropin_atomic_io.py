"""Actual Host.maintenance crash probes; all service/network/DB adapters are fake.

Only the drop-in/marker paths are redirected to disposable directories. The
atomic helper performs real open/write/flush/chown/chmod/fsync/replace calls.
A child process dies with os._exit at each IO boundary, and a fresh child then
reenters the same real maintenance method. No production path is written.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

REPO = Path(__file__).resolve().parents[1]
CRASH_EXIT = 87
NEW = b'[Unit]\nConditionPathExists=!/var/lib/dogeow-news-lock/legacy-no-start\n[Service]\nRestart=no\n'
OLD = b'# complete previously persisted barrier\n' + NEW
POINTS = ['after_temp_open', 'after_partial_write', 'after_complete_write_flush',
          'after_file_fsync', 'before_replace', 'after_replace_before_directory_fsync',
          'before_directory_fsync']


def load_host():
    spec = importlib.util.spec_from_file_location('news_actual_dropin_host_fixture', REPO / 'deployment/bootstrap-old-news.py')
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    return host


def fixture_root(value):
    root = Path(value).resolve()
    if not root.name.startswith('news-dropin-atomic-fixture-') or (root / '.pure-fixture').read_text() != 'no-real-host-operations\n':
        raise RuntimeError('Only this test disposable fixture is accepted')
    return root


def metadata(path):
    info = Path(path).lstat()
    return [info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)]


def temporary_for(path, target):
    value = Path(path)
    return value.parent == target.parent and value.name.startswith('.' + target.name + '.') and value.name.endswith('.new')


class FileProxy:
    def __init__(self, file, on_write, on_flush):
        self.file = file
        self.on_write = on_write
        self.on_flush = on_flush
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return self.file.__exit__(*args)
    def write(self, data):
        return self.on_write(self.file, data)
    def flush(self):
        self.file.flush()
        self.on_flush(self.file)
    def __getattr__(self, name):
        return getattr(self.file, name)


def worker(value, point=''):
    root = fixture_root(value)
    target = root / 'etc/systemd/system/news-web.service.d/90-news-bootstrap.conf'
    control = root / 'control'
    B = load_host()
    S = sys.modules[B.atomic_bytes.__module__]
    events = []
    counters = {'real_host_commands': 0, 'network_calls': 0, 'database_calls': 0,
                'mock_service_adapter_calls': 0, 'mock_http_adapter_calls': 0}
    tracked = set()
    real_open, real_fdopen = os.open, os.fdopen
    real_fsync, real_replace, real_fchmod, real_fchown = os.fsync, os.replace, os.fchmod, os.fchown
    real_dirsync = S.fsync_directory
    real_path_open = Path.open

    def report():
        (root / 'last-worker.json').write_text(json.dumps({'events': events, 'counters': counters, 'target_metadata': metadata(target)}))
    def die(where):
        if point == where:
            (root / 'fault-reached').write_text(where)
            report()
            os._exit(CRASH_EXIT)
    def guarded_path_open(path, mode='r', *args, **kwargs):
        if Path(path) == target and any(letter in mode for letter in ['w', 'a', 'x', '+']):
            raise AssertionError('Durable target must never be opened for in-place writing')
        return real_path_open(path, mode, *args, **kwargs)
    def opened(path, flags, *args, **kwargs):
        if Path(path) == target and flags & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC):
            raise AssertionError('Durable target must never be opened or truncated for writing')
        fd = real_open(path, flags, *args, **kwargs)
        if temporary_for(path, target):
            if not flags & os.O_NOFOLLOW or not flags & os.O_EXCL or flags & os.O_TRUNC:
                raise AssertionError('Temporary replacement requires NOFOLLOW and exclusive creation')
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise AssertionError('Temporary replacement is not a unique regular file')
            tracked.add(fd)
            events.append({'action': 'temp_open', 'name': Path(path).name})
            die('after_temp_open')
        return fd
    def wrote(file, data):
        if point == 'after_partial_write':
            cut = max(1, len(data) // 2)
            count = file.write(data[:cut])
            file.flush(); real_fsync(file.fileno())
            events.append({'action': 'partial_write', 'bytes': count})
            die('after_partial_write')
        count = file.write(data)
        events.append({'action': 'complete_write', 'bytes': count})
        return count
    def flushed(file):
        events.append({'action': 'complete_write_flush'})
        die('after_complete_write_flush')
    def fdopened(fd, *args, **kwargs):
        file = real_fdopen(fd, *args, **kwargs)
        return FileProxy(file, wrote, flushed) if fd in tracked else file
    def chmodded(fd, mode):
        result = real_fchmod(fd, mode)
        if fd in tracked: events.append({'action': 'fchmod', 'mode': mode})
        return result
    def chowned(fd, uid, gid):
        result = real_fchown(fd, uid, gid)
        if fd in tracked: events.append({'action': 'fchown', 'uid': uid, 'gid': gid})
        return result
    def synced(fd):
        result = real_fsync(fd)
        if fd in tracked and stat.S_ISREG(os.fstat(fd).st_mode):
            events.append({'action': 'file_fsync'})
            die('after_file_fsync')
        return result
    def replaced(source, destination, *args, **kwargs):
        if Path(destination) == target:
            if Path(source).read_bytes() != NEW:
                raise AssertionError('Replacement source is incomplete')
            events.append({'action': 'before_replace', 'source_metadata': metadata(source)})
            die('before_replace')
            result = real_replace(source, destination, *args, **kwargs)
            events.append({'action': 'after_replace', 'target_metadata': metadata(target)})
            die('after_replace_before_directory_fsync')
            return result
        return real_replace(source, destination, *args, **kwargs)
    def directory_synced(path):
        if Path(path) == target.parent:
            events.append({'action': 'before_directory_fsync'})
            die('before_directory_fsync')
        return real_dirsync(path)
    def no_command(*args, **kwargs):
        counters['real_host_commands'] += 1
        raise AssertionError('No real service, shell or database command may execute')
    def no_network(*args, **kwargs):
        counters['network_calls'] += 1
        raise AssertionError('No socket or DNS operation may execute')
    def no_database(*args, **kwargs):
        counters['database_calls'] += 1
        raise AssertionError('No database control session may be created')
    def fake_run(args):
        counters['mock_service_adapter_calls'] += 1
        if args == ['systemctl', 'show', B.UNIT, '-p', 'Restart', '--value']:
            return 'no'
        if args in [['systemctl', 'daemon-reload'], ['systemctl', 'stop', B.TIMER]]:
            return ''
        raise AssertionError('Unexpected service operation in actual maintenance')
    class ClosedPublicGate:
        def open(self, url, timeout=None):
            counters['mock_http_adapter_calls'] += 1
            raise urllib.error.HTTPError(url, 503, 'fixture maintenance', {}, None)
    patches = [
        mock.patch.object(B, 'CONTROL', control),
        mock.patch.object(B, 'MAINTENANCE', control / 'bootstrap-maintenance'),
        mock.patch.object(B, 'LEGACY_BLOCK', control / 'legacy-no-start'),
        mock.patch.object(B, 'DROPIN', target),
        mock.patch.object(B, 'CGROUP', root / 'no-real-cgroup'),
        mock.patch.object(B, 'root_preflight', return_value=None),
        mock.patch.object(B, 'run', side_effect=fake_run),
        mock.patch.object(B, 'PostgreSQL', side_effect=no_database),
        mock.patch.object(B.urllib.request, 'build_opener', return_value=ClosedPublicGate()),
        mock.patch.object(Path, 'open', guarded_path_open),
        mock.patch.object(os, 'open', opened),
        mock.patch.object(os, 'fdopen', fdopened),
        mock.patch.object(os, 'fchmod', chmodded),
        mock.patch.object(os, 'fchown', chowned),
        mock.patch.object(os, 'fsync', synced),
        mock.patch.object(os, 'replace', replaced),
        mock.patch.object(S, 'fsync_directory', directory_synced),
        mock.patch.object(subprocess, 'Popen', side_effect=no_command),
        mock.patch.object(subprocess, 'run', side_effect=no_command),
        mock.patch.object(os, 'system', side_effect=no_command),
        mock.patch.object(socket.socket, 'connect', no_network),
        mock.patch.object(socket.socket, 'connect_ex', no_network),
        mock.patch.object(socket, 'create_connection', no_network),
        mock.patch.object(socket, 'getaddrinfo', no_network),
    ]
    try:
        with contextlib_exit_stack(patches):
            # This is the actual production Host method, not a reproduction
            # of its writes. Committed reentry exercises the reported defect.
            B.Host().maintenance({'phase': 'kill_committed'}, lambda phase: None)
            report()
        return 0
    except BaseException as error:
        report()
        print(json.dumps({'error': type(error).__name__, 'message': str(error)}))
        return 2


class contextlib_exit_stack:
    def __init__(self, patches):
        self.patches = patches
        self.started = []
    def __enter__(self):
        for patch in self.patches:
            patch.start(); self.started.append(patch)
        return self
    def __exit__(self, *args):
        for patch in reversed(self.started): patch.stop()


class AtomicDropinIOFailures(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='news-dropin-atomic-fixture-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        (root / '.pure-fixture').write_text('no-real-host-operations\n')
        target = root / 'etc/systemd/system/news-web.service.d/90-news-bootstrap.conf'
        target.parent.mkdir(parents=True)
        (root / 'control').mkdir()
        target.write_bytes(OLD); target.chmod(0o640)
        # Exercise real group preservation whenever the current process is
        # allowed to assign a different fixture group. No system account or
        # external file is changed; root execution keeps the real root UID.
        choices = [group for group in os.getgroups() if group != target.stat().st_gid]
        if os.geteuid() == 0: choices.insert(0, 1 if target.stat().st_gid != 1 else 2)
        for group in choices:
            try: os.chown(target, -1, group)
            except PermissionError: continue
            break
        (root / 'expected-metadata.json').write_text(json.dumps(metadata(target)))
        return root, target

    def run_worker(self, root, point='', expected=0):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--atomic-worker', str(root), point],
                                env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if expected == CRASH_EXIT:
            self.assertEqual((root / 'fault-reached').read_text(), point)
        record = json.loads((root / 'last-worker.json').read_text())
        for key in ['real_host_commands', 'network_calls', 'database_calls']:
            self.assertEqual(record['counters'][key], 0)
        return record

    def test_actual_maintenance_survives_every_real_io_hard_exit(self):
        before_replace = set(POINTS[:5])
        for point in POINTS:
            with self.subTest(io_boundary=point):
                root, target = self.fixture()
                original_metadata = json.loads((root / 'expected-metadata.json').read_text())
                self.run_worker(root, point, CRASH_EXIT)
                self.assertIn(target.read_bytes(), [OLD, NEW])
                self.assertEqual(target.read_bytes(), OLD if point in before_replace else NEW)
                self.assertEqual(metadata(target), original_metadata)
                self.assertTrue((root / 'control/bootstrap-maintenance').is_file())
                self.assertTrue((root / 'control/legacy-no-start').is_file())
                leftovers = {p.name for p in target.parent.iterdir() if p.name.endswith('.new')}
                # A fresh actual-method run must ignore an interrupted writer's
                # unique scratch and atomically install the complete barrier.
                self.run_worker(root)
                self.assertEqual(target.read_bytes(), NEW)
                self.assertEqual(metadata(target), original_metadata)
                self.run_worker(root)
                self.assertEqual(target.read_bytes(), NEW)
                self.assertEqual(metadata(target), original_metadata)
                self.assertEqual({p.name for p in target.parent.iterdir() if p.name.endswith('.new')}, leftovers)

    def test_partial_temp_bytes_never_become_the_durable_target(self):
        root, target = self.fixture()
        self.run_worker(root, 'after_partial_write', CRASH_EXIT)
        scratch = [p for p in target.parent.iterdir() if p.name.endswith('.new')]
        self.assertEqual(len(scratch), 1)
        self.assertEqual(scratch[0].read_bytes(), NEW[:len(NEW) // 2])
        self.assertEqual(target.read_bytes(), OLD)
        self.assertEqual(metadata(target), json.loads((root / 'expected-metadata.json').read_text()))

    def test_replacement_preserves_real_fixture_uid_gid_and_restricted_mode(self):
        root, target = self.fixture()
        expected = metadata(target)
        record = self.run_worker(root)
        self.assertEqual(target.read_bytes(), NEW)
        self.assertEqual(metadata(target), expected)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertTrue(any(event['action'] == 'fchmod' and event['mode'] == 0o640 for event in record['events']))
        if expected[1] != target.parent.stat().st_gid:
            self.assertTrue(any(event['action'] == 'fchown' and event['gid'] == expected[1] for event in record['events']))


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--atomic-worker':
        raise SystemExit(worker(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''))
    unittest.main()
