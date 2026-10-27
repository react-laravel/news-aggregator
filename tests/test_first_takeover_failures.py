"""Crash/reentry tests of the real durable controller with filesystem-only hosts.

Workers deliberately use os._exit: no Python finally handler or old object can
repair a simulated interruption. Service, PostgreSQL, cgroup and HTTP actions
are ONLY FakeHost transitions under a disposable fixture root. A second worker
always imports the actual state machine again from a fresh interpreter.
"""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[1]
STATE_MODULE = REPO / 'deployment/news_first_state.py'
SPEC = importlib.util.spec_from_file_location('news_first_state_fixture', STATE_MODULE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
REVISION = '2' * 40
NONCE = 'a' * 32
LEGACY = 'source-30191069708-1'
LATER = '3' * 40
PAYLOAD = b'approved locked News fixture, no executable application\n'
CRASH_EXIT = 87
BUSY_EXIT = 88


class FixtureBusy(RuntimeError):
    pass


def read(path):
    return json.loads(Path(path).read_text())


def mutate_host(root, **fields):
    path = Path(root) / 'host.json'
    with M.file_lock(Path(root) / 'host-json.lock'):
        value = read(path)
        value.update(fields)
        M.atomic_json(path, value)
    return value


def checked_root(root):
    root = Path(root).resolve()
    if not root.name.startswith('news-first-fixture-') or (root / '.pure-fixture').read_text() != 'filesystem-only\n':
        raise RuntimeError('This worker only accepts its disposable pure fixture')
    return root


def install_pure_worker_guards(root):
    # Guard the fixture worker itself as well as using FakeHost, so an
    # accidental socket or real service/psql command fails before execution.
    def forbidden_socket(*args, **kwargs):
        data = read(root / 'host.json')
        mutate_host(root, application_socket_calls=data['application_socket_calls'] + 1)
        raise AssertionError('Pure fixture forbids every application socket')
    def forbidden_command(*args, **kwargs):
        data = read(root / 'host.json')
        mutate_host(root, host_command_calls=data['host_command_calls'] + 1)
        raise AssertionError('Pure fixture forbids real service/database commands')
    socket.socket.connect = forbidden_socket
    socket.socket.connect_ex = forbidden_socket
    socket.create_connection = forbidden_socket
    socket.getaddrinfo = forbidden_socket
    subprocess.Popen = forbidden_command
    subprocess.run = forbidden_command
    os.system = forbidden_command


class FakeHost:
    """No real application, network, database, privilege or cgroup operations."""
    enforce_root = False

    def __init__(self, root):
        self.root = checked_root(root)
        self.lease_held = False

    @property
    def data(self):
        return read(self.root / 'host.json')

    def change(self, event, **fields):
        with M.file_lock(self.root / 'host-json.lock'):
            value = read(self.root / 'host.json')
            value.update(fields)
            value['trace'].append(event)
            M.atomic_json(self.root / 'host.json', value)
        return value

    def claim_path(self, state):
        expected = self.root / 'control/claims' / (state['revision'] + '-' + state['nonce'])
        if state.get('claim_root') != str(expected):
            raise M.ProtocolError('Claim path or identity changed')
        return expected

    def verify_claim(self, state):
        claim = self.claim_path(state)
        identity = M.read_json(claim / 'identity.json')
        if not M.identity(identity, state['revision'], state['nonce']):
            raise M.ProtocolError('Canonical SHA/nonce differs')
        archive = claim / 'runtime.tar.gz'
        if archive.is_symlink() or not archive.is_file():
            raise M.ProtocolError('Canonical archive is missing or not regular')
        if hashlib.sha256(archive.read_bytes()).hexdigest() != state['archive_sha256']:
            raise M.ProtocolError('Canonical archive hash changed')
        if identity['archive_sha256'] != state['archive_sha256']:
            raise M.ProtocolError('Canonical expected digest changed')

    def cancelled(self, state):
        path = self.root / 'publisher-cancel.json'
        return (path.exists() and M.identity(read(path), state['revision'], state['nonce'])) or time.time() >= state['expires_at']

    def maintenance(self, state, checkpoint):
        self.change('close_ingress', maintenance=True, start_block=True, restart_enabled=False)
        checkpoint('after_maintenance')
        self.change('pause_timer', timer=False)
        checkpoint('after_timer_stop')
        if state['phase'] not in M.COMMITTED and self.data['frozen']:
            self.change('resume_old_work_for_fresh_proof', frozen=False)

    def drain_and_stop(self, state, commit, checkpoint):
        committed = state['phase'] in M.COMMITTED
        if not committed and self.cancelled(state):
            return False
        data = self.data
        if data['current'] != LEGACY:
            raise M.ProtocolError('Current changed before frozen proof')
        if not data['populated']:
            return committed
        self.change('freeze_old', frozen=True)
        checkpoint('after_freeze')
        data = self.data
        if data['old_running_jobs'] or data['database_active'] or data['database_transactions']:
            self.change('release_barrier_then_thaw_for_existing_work', frozen=False)
            raise FixtureBusy('A real host would wait for the existing task')
        with M.file_lock(self.root / 'publish.lock'):
            if state['phase'] not in M.COMMITTED and self.cancelled(state):
                return False
            # The state module performs canonical verification and durable
            # irreversible commit. Actual phase checkpoints happen in it.
            commit()
            if not self.data['frozen'] or self.data['old_running_jobs']:
                raise AssertionError('Kill without an intact frozen task-free proof')
            self.verify_claim(state)
            data = self.data
            pending = data.get('defer_kill_completion', False) and not data['kill_pending']
            self.change('kill_old', old_running=False, kill_pending=pending,
                        populated=pending, kills=data['kills'] + 1)
            checkpoint('after_kill')
            if pending:
                self.change('kernel_finishes_old_kill', populated=False, kill_pending=False)
            return True

    @contextlib.contextmanager
    def activation_lease(self, state):
        self.change('close_admission_before_activation', maintenance=True)
        try:
            with M.file_lock(self.root / 'publish.lock'), M.file_lock(self.root / 'ingest.lock', nonblocking=True):
                if self.data['active_ingest']:
                    raise AssertionError('Fixture task counter has no matching real lease')
                self.lease_held = True
                self.change('acquire_activation_lease')
                try:
                    yield
                finally:
                    self.lease_held = False
                    self.change('release_activation_lease')
        except BlockingIOError:
            self.change('wait_for_existing_ingest')
            raise FixtureBusy('Existing pure fixture task still owns the real lock')

    def require_lease(self):
        if not self.lease_held or self.data['active_ingest']:
            raise AssertionError('Activation without exclusive task lifetime lease')

    def install_launcher(self, state):
        self.require_lease()
        if self.data['old_running'] or self.data['populated']:
            raise AssertionError('Old in-process HTTP survived launcher replacement')
        self.change('install_locked_launcher', launcher='locked')

    def place_release(self, state):
        self.require_lease()
        release = self.root / 'releases' / state['revision']
        if not release.exists():
            # Missing expanded copies are rebuilt from the root canonical
            # source; deleting an uploader-owned stage cannot remove it.
            self.verify_claim(state)
            runtime = self.claim_path(state) / 'runtime'
            if not runtime.exists():
                runtime.mkdir()
                (runtime / 'payload').write_bytes((self.claim_path(state) / 'runtime.tar.gz').read_bytes())
            if hashlib.sha256((runtime / 'payload').read_bytes()).hexdigest() != state['archive_sha256']:
                raise M.ProtocolError('Claimed expanded runtime differs')
            os.rename(runtime, release)
        if hashlib.sha256((release / 'payload').read_bytes()).hexdigest() != state['archive_sha256']:
            raise M.ProtocolError('Expanded release differs from canonical package')
        self.change('place_locked_release')

    def switch_new(self, state):
        self.require_lease()
        if self.data['current'] not in [LEGACY, state['revision']]:
            raise M.ProtocolError('Unrelated release during first activation')
        self.change('switch_locked_current', current=state['revision'], start_block=False)

    def ensure_new_healthy(self, state):
        self.require_lease()
        data = self.data
        if data['current'] != state['revision'] or data['launcher'] != 'locked':
            raise AssertionError('New runtime started in a mixed collector protocol')
        if not data['healthy']:
            self.change('restart_locked_web', restarts=data['restarts'] + 1, healthy=True)
        self.change('verify_locked_health')

    def restore_new_schedule(self, state, checkpoint):
        self.require_lease()
        if not self.data['maintenance']:
            raise AssertionError('Persistent timer was restored after opening admission')
        self.change('restore_new_timer_under_gate', timer=True, restart_enabled=True)
        checkpoint('after_timer_restore')

    def remove_legacy(self, state):
        self.require_lease()
        if not self.data['healthy']:
            raise AssertionError('Deleted old runtime before verified new health')
        old = self.root / 'releases' / LEGACY
        if old.exists():
            shutil.rmtree(old)
        self.change('retire_legacy_runtime', old_removed=True)

    def open_ingress(self, state):
        self.require_lease()
        data = self.data
        if not data['healthy'] or data['current'] != state['revision'] or data['launcher'] != 'locked':
            raise AssertionError('Opened ingress before a consistent locked runtime')
        self.change('open_locked_ingress', maintenance=False)

    def restore_legacy(self, state, checkpoint):
        data = self.data
        if state['phase'] in M.COMMITTED or data['current'] != LEGACY or data['kills']:
            raise AssertionError('Attempted legacy restoration after irreversible kill')
        self.change('abort_close_gate_restore_original_launcher', maintenance=True, launcher='legacy')
        checkpoint('abort_launcher')
        self.change('abort_thaw_existing_old_web', frozen=False)
        checkpoint('abort_thaw')
        self.change('abort_restore_old_start_conditions', start_block=False, restart_enabled=True, old_running=True, populated=True)
        self.change('abort_verify_original_legacy_contract')
        if not self.data['maintenance']:
            raise AssertionError('Restored old Persistent timer without maintenance condition')
        self.change('abort_restore_timer_under_start_condition', timer=True)
        checkpoint('abort_timer')
        self.change('abort_open_original_protocol', maintenance=False)
        checkpoint('abort_open')

    def cleanup_claim(self, state):
        if state['phase'] not in ['completed', 'aborted']:
            raise AssertionError('Premature canonical package cleanup')
        claim = self.claim_path(state)
        if claim.exists():
            shutil.rmtree(claim)
        self.change('cleanup_terminal_own_claim')


def initialize(root):
    root = Path(root)
    (root / '.pure-fixture').write_text('filesystem-only\n')
    for path in ['control/claims', 'releases', 'uploads']:
        (root / path).mkdir(parents=True)
    claim = root / 'control/claims' / (REVISION + '-' + NONCE)
    claim.mkdir()
    (claim / 'runtime.tar.gz').write_bytes(PAYLOAD)
    (claim / 'runtime').mkdir()
    (claim / 'runtime/payload').write_bytes(PAYLOAD)
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    M.atomic_json(claim / 'identity.json', {'revision': REVISION, 'nonce': NONCE, 'archive_sha256': digest})
    (root / 'uploads/runtime.tar.gz').write_bytes(PAYLOAD)
    M.atomic_json(root / 'uploads/ready.json', {'revision': REVISION, 'nonce': NONCE})
    (root / 'releases' / LEGACY).mkdir()
    (root / 'releases' / LEGACY / 'payload').write_text('original legacy runtime')
    M.atomic_json(root / 'state.json', {
        'schema': 2, 'revision': REVISION, 'nonce': NONCE, 'phase': 'claimed',
        'legacy': LEGACY, 'claim_root': str(claim), 'archive_sha256': digest,
        'expires_at': time.time() + 3600, 'public_open': False,
    })
    M.atomic_json(root / 'host.json', {
        'current': LEGACY, 'launcher': 'legacy', 'old_running': True, 'populated': True,
        'frozen': False, 'kill_pending': False, 'maintenance': False, 'timer': True,
        'start_block': False, 'restart_enabled': True, 'healthy': False,
        'kills': 0, 'restarts': 0, 'old_removed': False, 'active_ingest': 0,
        'old_running_jobs': 0, 'database_active': 0, 'database_transactions': 0,
        'application_socket_calls': 0, 'host_command_calls': 0, 'database_writes': 0, 'tasks_interrupted': 0,
        'tasks_completed': 0, 'trace': [],
    })


def worker(root, crash_point=''):
    root = checked_root(root)
    install_pure_worker_guards(root)
    def checkpoint(point):
        if point == crash_point:
            # The marker is only evidence of the reached hook; no finally or
            # recovery code runs in this process after this kernel exit.
            (root / 'crash-reached').write_text(point)
            os._exit(CRASH_EXIT)
    try:
        result = M.DurableTakeover(root / 'state.json', FakeHost(root), checkpoint).run()
        print(json.dumps({'phase': result['phase'], 'revision': result['revision'], 'nonce': result['nonce']}))
        return 0
    except FixtureBusy:
        return BUSY_EXIT
    except BaseException as error:
        print(json.dumps({'error': type(error).__name__, 'message': str(error)}))
        return 2


def task_worker(root):
    root = checked_root(root)
    install_pure_worker_guards(root)
    host = FakeHost(root)
    with M.file_lock(root / 'ingest.lock'):
        data = host.data
        if data['maintenance'] or data['current'] != REVISION or data['launcher'] != 'locked':
            return 3
        host.change('begin_independent_fixture_task', active_ingest=1)
        print('task-ready', flush=True)
        sys.stdin.read()
        host.change('finish_independent_fixture_task', active_ingest=0, tasks_completed=host.data['tasks_completed'] + 1)
    return 0


class DurableFirstFailureMatrix(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='news-first-fixture-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        initialize(root)
        return root

    def run_worker(self, root, crash_point='', expected=0):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--fixture-worker', str(root), crash_point],
                                env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if expected == CRASH_EXIT:
            self.assertEqual((root / 'crash-reached').read_text(), crash_point)
        return result

    def cancel(self, root, nonce=NONCE):
        # Cancellation writers serialize with irreversible commit, as on B.
        with M.file_lock(root / 'publish.lock'):
            M.atomic_json(root / 'publisher-cancel.json', {'revision': REVISION, 'nonce': nonce})

    def assert_no_external_side_effects(self, root):
        data = read(root / 'host.json')
        self.assertEqual(data['application_socket_calls'], 0)
        self.assertEqual(data['host_command_calls'], 0)
        self.assertEqual(data['database_writes'], 0)
        self.assertEqual(data['tasks_interrupted'], 0)

    def assert_completed(self, root):
        state = read(root / 'state.json'); data = read(root / 'host.json')
        self.assertEqual((state['revision'], state['nonce'], state['phase']), (REVISION, NONCE, 'completed'))
        self.assertTrue(state['public_open']); self.assertEqual(data['current'], REVISION)
        self.assertEqual(data['launcher'], 'locked'); self.assertTrue(data['healthy'])
        self.assertFalse(data['old_running']); self.assertFalse(data['populated'])
        self.assertFalse(data['maintenance']); self.assertTrue(data['timer']); self.assertFalse(data['start_block'])
        self.assertEqual(data['kills'], 1); self.assertTrue(data['old_removed'])
        self.assertEqual(sorted(p.name for p in (root / 'releases').iterdir()), [REVISION])
        self.assert_no_external_side_effects(root)

    def assert_aborted(self, root):
        state = read(root / 'state.json'); data = read(root / 'host.json')
        self.assertEqual(state['phase'], 'aborted'); self.assertTrue(state['public_open'])
        self.assertEqual(data['current'], LEGACY); self.assertEqual(data['launcher'], 'legacy')
        self.assertTrue(data['old_running']); self.assertTrue(data['populated']); self.assertFalse(data['frozen'])
        self.assertFalse(data['maintenance']); self.assertTrue(data['timer']); self.assertFalse(data['start_block'])
        self.assertTrue(data['restart_enabled']); self.assertEqual(data['kills'], 0)
        self.assertFalse(data['old_removed']); self.assertEqual(data['restarts'], 0)
        self.assert_no_external_side_effects(root)

    def test_fresh_process_recovers_every_success_checkpoint(self):
        points = ['maintenance', 'after_maintenance', 'after_timer_stop', 'draining', 'after_freeze',
                  'kill_committed', 'after_kill', 'old_dead', 'launcher_ready', 'release_ready',
                  'switch_intent', 'after_switch', 'starting', 'after_restart', 'healthy',
                  'after_timer_restore', 'open_intent', 'after_open', 'completed']
        for point in points:
            with self.subTest(checkpoint=point):
                root = self.fixture()
                self.run_worker(root, point, CRASH_EXIT)
                self.run_worker(root)
                self.assert_completed(root)

    def test_fresh_process_recovers_every_abort_checkpoint(self):
        for point in ['aborting', 'abort_launcher', 'abort_thaw', 'abort_timer', 'abort_open', 'aborted']:
            with self.subTest(checkpoint=point):
                root = self.fixture()
                mutate_host(root, frozen=True, maintenance=True, timer=False, start_block=True, restart_enabled=False)
                self.cancel(root)
                self.run_worker(root, point, CRASH_EXIT)
                self.run_worker(root)
                self.assert_aborted(root)

    def test_cancel_after_freeze_before_commit_restores_complete_legacy_protocol(self):
        root = self.fixture(); self.run_worker(root, 'after_freeze', CRASH_EXIT)
        self.assertTrue(read(root / 'host.json')['frozen'])
        self.cancel(root); self.run_worker(root); self.assert_aborted(root)

    def test_expiry_before_commit_aborts_but_after_commit_completes(self):
        for checkpoint, expected in [('after_freeze', 'aborted'), ('kill_committed', 'completed')]:
            with self.subTest(checkpoint=checkpoint):
                root = self.fixture(); self.run_worker(root, checkpoint, CRASH_EXIT)
                state = read(root / 'state.json'); state['expires_at'] = 0; M.atomic_json(root / 'state.json', state)
                self.run_worker(root)
                (self.assert_aborted if expected == 'aborted' else self.assert_completed)(root)

    def test_late_cancel_never_restores_legacy_after_kill_commit(self):
        for point in ['kill_committed', 'after_kill', 'launcher_ready', 'after_switch', 'after_restart', 'healthy', 'after_open']:
            with self.subTest(checkpoint=point):
                root = self.fixture(); self.run_worker(root, point, CRASH_EXIT)
                self.cancel(root); self.run_worker(root); self.assert_completed(root)
                self.assertFalse(any(x.startswith('abort_') for x in read(root / 'host.json')['trace']))

    def test_pending_kernel_kill_is_not_misread_as_cancellable_live_legacy(self):
        root = self.fixture(); mutate_host(root, defer_kill_completion=True)
        self.run_worker(root, 'after_kill', CRASH_EXIT)
        data = read(root / 'host.json')
        self.assertTrue(data['populated']); self.assertTrue(data['kill_pending']); self.assertFalse(data['old_running'])
        self.cancel(root); self.run_worker(root)
        data = read(root / 'host.json')
        self.assertEqual(read(root / 'state.json')['phase'], 'completed')
        self.assertEqual(data['current'], REVISION); self.assertFalse(data['maintenance'])
        self.assertFalse(any(x.startswith('abort_') for x in data['trace']))
        self.assert_no_external_side_effects(root)

    def test_publisher_timeout_deletion_or_replacement_cannot_remove_claimed_package(self):
        for action in ['delete', 'replace']:
            with self.subTest(upload_action=action):
                root = self.fixture(); self.run_worker(root, 'after_freeze', CRASH_EXIT)
                if action == 'delete': shutil.rmtree(root / 'uploads')
                else:
                    (root / 'uploads/runtime.tar.gz').write_bytes(b'untrusted replacement after claim')
                    M.atomic_json(root / 'uploads/ready.json', {'revision': LATER, 'nonce': 'b' * 32})
                self.run_worker(root); self.assert_completed(root)
                self.assertEqual((root / 'releases' / REVISION / 'payload').read_bytes(), PAYLOAD)

    def test_missing_expanded_candidate_is_rebuilt_from_root_canonical_source(self):
        root = self.fixture(); self.run_worker(root, 'after_freeze', CRASH_EXIT)
        # A lost expanded copy is recoverable from the protected archive;
        # no uploader process is needed to rebuild it.
        claim = Path(read(root / 'state.json')['claim_root'])
        shutil.rmtree(claim / 'runtime')
        self.run_worker(root); self.assert_completed(root)
        self.assertEqual((root / 'releases' / REVISION / 'payload').read_bytes(), PAYLOAD)

    def test_canonical_corruption_fails_before_any_legacy_termination(self):
        for action in ['corrupt', 'symlink']:
            with self.subTest(action=action):
                root = self.fixture(); state = read(root / 'state.json')
                archive = Path(state['claim_root']) / 'runtime.tar.gz'
                if action == 'corrupt': archive.write_bytes(b'corrupt canonical source')
                else:
                    archive.unlink(); archive.symlink_to(root / 'uploads/runtime.tar.gz')
                self.run_worker(root, expected=2)
                data = read(root / 'host.json')
                self.assertEqual(data['kills'], 0); self.assertTrue(data['old_running'])
                self.assertEqual(data['current'], LEGACY); self.assertEqual(data['trace'], [])
                self.assert_no_external_side_effects(root)

    def test_nonce_or_revision_substitution_is_rejected_without_host_actions(self):
        for field, value in [('nonce', 'b' * 32), ('revision', LATER)]:
            with self.subTest(field=field):
                root = self.fixture(); state = read(root / 'state.json'); state[field] = value
                M.atomic_json(root / 'state.json', state)
                self.run_worker(root, expected=2)
                self.assertEqual(read(root / 'host.json')['trace'], [])

    def test_stale_result_ready_and_reused_pid_are_not_activation_authority(self):
        root = self.fixture()
        M.atomic_json(root / 'uploads/result.json', {'revision': LATER, 'nonce': 'b' * 32, 'state': 'healthy'})
        M.atomic_json(root / 'uploads/ready.json', {'revision': LATER, 'nonce': 'b' * 32, 'publisher_pid': os.getpid()})
        state = read(root / 'state.json'); state['publisher_pid'] = os.getpid()
        M.atomic_json(root / 'state.json', state)
        self.run_worker(root); self.assert_completed(root)
        self.assertEqual(read(root / 'state.json')['nonce'], NONCE)

    def test_stale_cancel_nonce_cannot_cancel_the_claimed_identity(self):
        root = self.fixture(); self.cancel(root, nonce='b' * 32)
        self.run_worker(root); self.assert_completed(root)

    def test_completed_historical_reentry_never_rewinds_later_current(self):
        root = self.fixture(); self.run_worker(root); self.assert_completed(root)
        before = read(root / 'host.json'); restart_count = before['restarts']; kill_count = before['kills']
        later = root / 'releases' / LATER; later.mkdir(); (later / 'payload').write_text('later ordinary locked deployment')
        shutil.rmtree(root / 'releases' / REVISION)
        mutate_host(root, current=LATER)
        self.run_worker(root); self.run_worker(root)
        data = read(root / 'host.json')
        self.assertEqual(data['current'], LATER); self.assertTrue(later.is_dir())
        self.assertEqual(data['restarts'], restart_count); self.assertEqual(data['kills'], kill_count)
        self.assertFalse(data['maintenance']); self.assertTrue(data['timer'])
        self.assertEqual(read(root / 'state.json')['phase'], 'completed')
        self.assert_no_external_side_effects(root)

    def test_aborted_historical_reentry_does_not_touch_future_locked_current(self):
        root = self.fixture(); self.cancel(root); self.run_worker(root); self.assert_aborted(root)
        mutate_host(root, current=LATER, launcher='locked', healthy=True)
        self.run_worker(root)
        self.assertEqual(read(root / 'host.json')['current'], LATER)
        self.assertFalse(read(root / 'host.json')['maintenance'])

    def test_after_open_crash_waits_for_real_fixture_task_lease_before_restart(self):
        root = self.fixture(); self.run_worker(root, 'after_open', CRASH_EXIT)
        mutate_host(root, healthy=False)
        task = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--fixture-task', str(root)],
                                env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(task.stdout.readline().strip(), 'task-ready')
            restarts = read(root / 'host.json')['restarts']
            self.run_worker(root, expected=BUSY_EXIT)
            data = read(root / 'host.json')
            self.assertEqual(data['active_ingest'], 1); self.assertEqual(data['restarts'], restarts)
            self.assertTrue(data['maintenance']); self.assertIn('wait_for_existing_ingest', data['trace'])
            task.stdin.close(); self.assertEqual(task.wait(timeout=5), 0, task.stderr.read())
            self.run_worker(root); self.assert_completed(root)
            data = read(root / 'host.json')
            self.assertEqual(data['tasks_completed'], 1); self.assertEqual(data['active_ingest'], 0)
            self.assertEqual(data['restarts'], restarts + 1)
        finally:
            if task.poll() is None:
                task.kill(); task.wait(timeout=5)
            for stream in [task.stdin, task.stdout, task.stderr]:
                if stream is not None and not stream.closed: stream.close()

    def test_running_database_work_prevents_commit_or_kill(self):
        for key in ['old_running_jobs', 'database_active', 'database_transactions']:
            with self.subTest(proof_field=key):
                root = self.fixture(); mutate_host(root, **{key: 1})
                self.run_worker(root, expected=BUSY_EXIT)
                data = read(root / 'host.json')
                self.assertEqual(data['kills'], 0); self.assertTrue(data['old_running'])
                self.assertFalse(data['frozen']); self.assertNotIn(read(root / 'state.json')['phase'], M.COMMITTED)
                mutate_host(root, **{key: 0}); self.run_worker(root); self.assert_completed(root)


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--fixture-worker':
        raise SystemExit(worker(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''))
    if len(sys.argv) == 3 and sys.argv[1] == '--fixture-task':
        raise SystemExit(task_worker(sys.argv[2]))
    unittest.main()
