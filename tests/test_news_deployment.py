import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

P = load('publisher', 'deployment/publish-news.py')
C = load('collector', 'deployment/news-collect.py')
G = load('gateway', 'deployment/news-ssh-gateway.py')
B = load('bootstrap', 'deployment/bootstrap-old-news.py')

class NewsDeployment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.app = self.root / 'app'; self.releases = self.app / 'releases'
        self.state = self.root / 'state'; self.incoming = self.state / 'incoming'
        for p in [self.releases, self.incoming, self.state / 'gate', self.app / 'shared/cache']:
            p.mkdir(parents=True, exist_ok=True)
        self.lock = self.root / 'ingest.lock'; self.lock.touch(); self.lock.chmod(0o644)
        self.gate = self.state / 'gate/maintenance'
        self.old = '1' * 40; self.new = '2' * 40
        (self.releases / self.old).mkdir(); (self.releases / self.old / 'marker').write_text('old')
        (self.releases / 'current').symlink_to(self.old); (self.app / 'current').symlink_to('releases/current')
        self.patchers = [mock.patch.object(P, n, v) for n, v in {'APP': self.app, 'RELEASES': self.releases, 'STATE': self.state, 'INCOMING': self.incoming, 'GATE': self.gate, 'INGEST_LOCK': self.lock, 'FIRST_STATE': self.root/'first-state.json', 'BOOTSTRAP_GATE': self.root/'bootstrap-maintenance'}.items()]
        self.real_fstat = os.fstat
        def root_info(fd):
            value = self.real_fstat(fd)
            fields = list(value); fields[4] = 0
            return os.stat_result(fields)
        self.patchers += [mock.patch.object(os, 'fstat', root_info)]
        for p in self.patchers: p.start()
    def tearDown(self):
        for p in reversed(self.patchers): p.stop()
        self.tmp.cleanup()
    def archive(self, mutate=None):
        files = {name: b'fixture' for name in P.REQUIRED}
        if mutate: mutate(files)
        manifest = {'schema': 1, 'revision': self.new, 'files': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}
        path = self.incoming / (self.new + '.tar.gz')
        with tarfile.open(path, 'w:gz') as tar:
            for name, data in {**files, 'deploy-manifest.json': json.dumps(manifest).encode()}.items():
                item = tarfile.TarInfo(name); item.size = len(data); tar.addfile(item, io.BytesIO(data))
        return path
    def test_gateway_rejects_shell_and_other_services(self):
        self.assertEqual(G.parse_command('publish ' + self.new), ('publish', self.new))
        for value in ['publish '+self.new+'; id', 'restart nginx', 'receive ../x', 'publish '+self.new+'\n', 'bash', 'validate '+self.new+' extra']:
            with self.assertRaises(ValueError): G.parse_command(value)
    def test_private_and_traversal_paths_rejected(self):
        for value in ['../x', '/server.js', 'public/.env.local', 'node_modules/.ssh/key', '.next/cache/x', 'public/../x', 'public\\x', 'deployment/tool.py']:
            with self.assertRaises(P.DeployError): P.safe_path(value)
    def test_manifest_inspection_and_extract_hashes(self):
        archive = self.archive(); files, _ = P.inspect_archive(archive, self.new)
        stage = self.root / 'stage'; stage.mkdir(); P.extract_archive(archive, stage, files)
        self.assertEqual((stage / 'ingest.cjs').read_bytes(), b'fixture')
        self.assertEqual(os.readlink(stage / '.next/cache'), str(self.app / 'shared/cache'))
        files['ingest.cjs'] = '0' * 64
        second = self.root / 'second'; second.mkdir()
        with self.assertRaises(P.DeployError): P.extract_archive(archive, second, files)
    def test_symlink_and_duplicate_members_rejected(self):
        for kind in ['link', 'duplicate']:
            archive = self.incoming / (kind + '.tar.gz')
            with tarfile.open(archive, 'w:gz') as tar:
                item = tarfile.TarInfo('server.js')
                if kind == 'link': item.type = tarfile.SYMTYPE; item.linkname = '/etc/passwd'; tar.addfile(item)
                else:
                    item.size = 1; tar.addfile(item, io.BytesIO(b'x')); tar.addfile(item, io.BytesIO(b'x'))
            with self.assertRaises(P.DeployError): P.inspect_archive(archive, self.new)
    def test_publish_waits_whole_ingestion_and_closes_admission(self):
        held = os.open(self.lock, os.O_RDONLY); fcntl.flock(held, fcntl.LOCK_EX)
        result = []; errors = []
        def acquire():
            try: result.append(P.admission_gate())
            except BaseException as error: errors.append(error)
        thread = threading.Thread(target=acquire); thread.start()
        deadline = time.monotonic()+3
        while not self.gate.exists() and time.monotonic()<deadline: time.sleep(0.005)
        self.assertTrue(self.gate.exists()); self.assertEqual(result, [])
        with self.assertRaises(BlockingIOError): C.acquire(self.lock, self.gate)
        os.close(held); thread.join(3); self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        with self.assertRaises(BlockingIOError): C.acquire(self.lock, self.gate)
        os.close(result[0])
        # Even between lock release and marker removal a new task is rejected.
        with self.assertRaises(BlockingIOError): C.acquire(self.lock, self.gate)
        self.gate.unlink(); os.close(C.acquire(self.lock, self.gate))
    def test_ingest_lock_lives_until_exec_process_exit(self):
        code = '''import os,fcntl,sys
fd=os.open(sys.argv[1],os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX);os.set_inheritable(fd,True)
os.execv(sys.executable,[sys.executable,'-c',"import sys; print('ready',flush=True); sys.stdin.read()"])
'''
        child = subprocess.Popen([sys.executable, '-c', code, str(self.lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            with self.assertRaises(BlockingIOError): C.acquire(self.lock, self.gate)
            child.stdin.close(); child.wait(timeout=3)
            os.close(C.acquire(self.lock, self.gate))
        finally:
            if child.poll() is None: child.kill(); child.wait()
            child.stdout.close()
    def test_success_restarts_only_web_keeps_one_runtime_and_state(self):
        self.archive(); cache = self.app / 'shared/cache/sentinel'; cache.write_text('persistent')
        with mock.patch.object(P, 'restart_web') as restart, mock.patch.object(P, 'wait_health') as health:
            P.publish(self.new)
        self.assertEqual(restart.call_count, 1); health.assert_called_once_with(self.releases / self.new, self.new)
        self.assertEqual(P.current_release(), self.new); self.assertFalse((self.releases/self.old).exists())
        self.assertEqual(cache.read_text(), 'persistent'); self.assertEqual(list(self.incoming.iterdir()), []); self.assertFalse(self.gate.exists())
    def test_health_failure_rolls_back_before_release_gate(self):
        self.archive(); timeline=[]
        def health(release, revision):
            self.assertTrue(self.gate.exists())
            timeline.append(revision)
            if revision == self.new: raise P.DeployError('fixture health failure')
        with mock.patch.object(P, 'restart_web') as restart, mock.patch.object(P, 'wait_health', side_effect=health):
            with self.assertRaises(P.DeployError): P.publish(self.new)
        self.assertEqual(restart.call_count, 2); self.assertEqual(timeline, [self.new, self.old]); self.assertEqual(P.current_release(), self.old)
        self.assertFalse((self.releases/self.new).exists()); self.assertFalse(self.gate.exists()); self.assertEqual(list(self.incoming.iterdir()), [])
    def test_disk_floor_refuses_extraction_before_restart(self):
        self.archive()
        with mock.patch.object(P.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=P.MIN_FREE)), mock.patch.object(P, 'restart_web') as restart:
            with self.assertRaises(P.DeployError): P.publish(self.new)
        restart.assert_not_called(); self.assertEqual(P.current_release(), self.old)
    def test_unknown_release_never_deleted(self):
        unknown=self.releases/'unknown'; unknown.mkdir(); self.archive()
        with self.assertRaises(P.DeployError): P.publish(self.new)
        self.assertTrue(unknown.exists()); self.assertEqual(P.current_release(), self.old)
    def test_bootstrap_refuses_running_active_or_uncommitted_work(self):
        safe = {'running':0,'active':0,'transactions':0,'unknown_connections':0}
        self.assertTrue(B.safe_to_kill(safe, {'frozen':'1'}))
        self.assertFalse(B.safe_to_kill(safe, {'frozen':'0'}))
        for key in safe:
            unsafe = dict(safe); unsafe[key] = 1
            self.assertFalse(B.safe_to_kill(unsafe, {'frozen':'1'}))
    def test_unsafe_frozen_attempt_thaws_without_killing(self):
        cg=self.root/'cgroup'; cg.mkdir()
        for name in ['cgroup.freeze','cgroup.kill']: (cg/name).touch()
        database=mock.Mock(); database.query.return_value={'running':1,'active':0,'transactions':0,'unknown_connections':0}
        with mock.patch.object(B,'events',return_value={'frozen':'1','populated':'1'}), mock.patch.object(B,'run') as command:
            self.assertFalse(B.frozen_attempt(database,cg))
        database.close.assert_called_once(); command.assert_not_called()
        self.assertEqual((cg/'cgroup.freeze').read_text(),'0\n'); self.assertEqual((cg/'cgroup.kill').read_text(),'')
    def test_safe_frozen_kill_precedes_systemctl_stop(self):
        cg=self.root/'cgroup'; cg.mkdir()
        for name in ['cgroup.freeze','cgroup.kill']: (cg/name).touch()
        safe={'running':0,'active':0,'transactions':0,'unknown_connections':0}
        database=mock.Mock(); database.query.side_effect=[safe,{'terminated':2},{'connections':0},safe,{'committed':True}]
        def command(args):
            self.assertEqual((cg/'cgroup.freeze').read_text(),'1\n')
            self.assertEqual((cg/'cgroup.kill').read_text(),'1\n')
            self.assertEqual(args,['systemctl','stop','dogeow-test-news-web.service'])
        states=[{'frozen':'1','populated':'1'}]*3+[{'frozen':'1','populated':'0'}]
        with mock.patch.object(B,'events',side_effect=states),mock.patch.object(B,'run',side_effect=command):
            self.assertTrue(B.frozen_attempt(database,cg))
        self.assertIn('LOCK TABLE "IngestJob" IN ACCESS EXCLUSIVE MODE',database.query.call_args_list[0].args[0])
        self.assertIn('pg_terminate_backend',database.query.call_args_list[1].args[0])
    def test_first_publish_stages_only_archive_and_never_switches(self):
        (self.releases/'current').unlink(); (self.releases/self.old).rename(self.releases/P.LEGACY)
        (self.releases/'current').symlink_to(P.LEGACY); archive=self.archive()
        with mock.patch.object(P,'restart_web') as restart:
            nonce=P.stage_first(self.new)
            with self.assertRaises(P.DeployError):P.publish(self.new)
        self.assertEqual(len(nonce),32);restart.assert_not_called()
        self.assertTrue(archive.exists());self.assertFalse((self.releases/self.new).exists())
        ready=json.loads((self.state/'first-publish-ready.json').read_text())
        self.assertEqual(ready['nonce'],nonce);self.assertEqual(ready['schema'],2)
        P.cancel_first(self.new,nonce)
        self.assertFalse(archive.exists());self.assertFalse((self.state/'first-publish-ready.json').exists())
    def test_claimed_source_is_outside_observer_timeout_cleanup(self):
        (self.releases/'current').unlink(); (self.releases/self.old).rename(self.releases/P.LEGACY)
        (self.releases/'current').symlink_to(P.LEGACY);archive=self.archive();nonce=P.stage_first(self.new)
        canonical=self.root/'canonical.tar.gz';canonical.write_bytes(archive.read_bytes());digest=hashlib.sha256(canonical.read_bytes()).hexdigest()
        P.FIRST_STATE.write_text(json.dumps({'revision':self.new,'nonce':nonce,'phase':'draining'}));archive.unlink()
        P.cancel_first(self.new,nonce)
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),digest)
        self.assertEqual(json.loads((self.state/'first-cancel.json').read_text()),{'revision':self.new,'nonce':nonce})
    def test_stale_observer_nonce_does_not_cancel_or_delete_other_request(self):
        (self.releases/'current').unlink(); (self.releases/self.old).rename(self.releases/P.LEGACY)
        (self.releases/'current').symlink_to(P.LEGACY);archive=self.archive();nonce=P.stage_first(self.new)
        P.cancel_first(self.new,'f'*32)
        self.assertTrue(archive.exists());self.assertEqual(json.loads((self.state/'first-publish-ready.json').read_text())['nonce'],nonce)
    def test_observer_requires_open_gate_and_matching_root_completed_nonce(self):
        nonce='a'*32
        P.FIRST_STATE.write_text(json.dumps({'revision':self.new,'nonce':nonce,'phase':'completed','public_open':True}))
        P.BOOTSTRAP_GATE.touch()
        with mock.patch.object(P,'cancel_first') as cancel:
            with self.assertRaisesRegex(P.DeployError,'reopened'):P.observe_first(self.new,nonce)
        cancel.assert_called_once_with(self.new,nonce)
        P.BOOTSTRAP_GATE.unlink()
        with mock.patch.object(P,'cancel_first') as cancel:P.observe_first(self.new,nonce)
        cancel.assert_not_called()
    def test_no_secret_or_database_or_timer_authority(self):
        publisher=(ROOT/'deployment/publish-news.py').read_text()
        self.assertNotIn('runtime-env.json', publisher); self.assertNotIn('psql', publisher); self.assertNotIn('prisma:', publisher)
        self.assertNotIn("'start', 'dogeow-test-news-ingest", publisher)
        sudo=(ROOT/'deployment/sudoers-news-deploy').read_text().splitlines()
        self.assertEqual(sudo, ['news-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart dogeow-test-news-web.service'])
        business=(ROOT/'src/lib/news/ingest.ts').read_bytes()
        expected=json.loads((ROOT.parent/'source-baseline.json').read_text()) if (ROOT.parent/'source-baseline.json').exists() else None
        if expected: self.assertEqual(hashlib.sha1(b'blob '+str(len(business)).encode()+b'\0'+business).hexdigest(), expected['src/lib/news/ingest.ts'])

if __name__ == '__main__': unittest.main()
