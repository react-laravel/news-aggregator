#!/usr/bin/python3 -I
"""ADMIN ONLY, one-time controlled takeover. Never called by the SSH gateway.

Requires the reviewed whole-site Nginx maintenance include and fixed collector
wrapper to have been installed. Leaves ingress and timer paused for the first
new-code publication. No DDL, migrations, seeds or source fetches are executed.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import select
import re
import pwd
import subprocess
import sys
import time
import urllib.request
import urllib.error
import contextlib
import importlib.util
import shutil
import stat
import math

UNIT = 'dogeow-test-news-web.service'
TIMER = 'dogeow-test-news-ingest.timer'
INGEST = 'dogeow-test-news-ingest.service'
CGROUP = Path('/sys/fs/cgroup/system.slice/dogeow-test-news-web.service')
CONTROL = Path('/var/lib/dogeow-news-lock')
MAINTENANCE = CONTROL / 'bootstrap-maintenance'
FIRST_STATE = CONTROL / 'first-state.json'
LEGACY = 'source-30191069708-1'
DROPIN = Path('/etc/systemd/system/dogeow-test-news-web.service.d/90-news-bootstrap.conf')
SNAPSHOT_SQL = '''SELECT json_build_object(
 'running',(SELECT count(*) FROM "IngestJob" WHERE status='running'),
 'active',(SELECT count(*) FROM pg_stat_activity WHERE datname='news_aggregator' AND pid<>pg_backend_pid() AND state='active'),
 'transactions',(SELECT count(*) FROM pg_stat_activity WHERE datname='news_aggregator' AND pid<>pg_backend_pid() AND xact_start IS NOT NULL),
 'unknown_connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='news_aggregator' AND pid<>pg_backend_pid() AND usename<>'dogeow_news'));
'''

class TakeoverSealed(RuntimeError):
    pass

def run(args):
    if not args or args[0]!='systemctl':raise RuntimeError('Only fixed systemctl operations are supported')
    result = subprocess.run(['/usr/bin/systemctl',*args[1:]], env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Fixed bootstrap command failed; output suppressed')
    return result.stdout.strip()

def events(cgroup=CGROUP):
    return dict(line.split() for line in (cgroup / 'cgroup.events').read_text().splitlines())

def safe_to_kill(snapshot, state):
    return state.get('frozen') == '1' and all(snapshot.get(key) == 0 for key in ['running', 'active', 'transactions', 'unknown_connections'])

class PostgreSQL:
    def __init__(self):
        self.process = subprocess.Popen(['/usr/sbin/runuser', '-u', 'postgres', '--', '/usr/bin/psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-d', 'news_aggregator'], env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def query(self, sql):
        # A separate completed statement clears the per-transaction activity
        # snapshot before the proof query. Do not rely on CTE evaluation order.
        self._execute("SELECT json_build_object('cleared',pg_stat_clear_snapshot() IS NULL);")
        return self._execute(sql)
    def _execute(self, sql):
        self.process.stdin.write(sql + '\n'); self.process.stdin.flush()
        # The SQL statements return one bounded JSON object, never table data.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if select.select([self.process.stdout], [], [], 0.25)[0]:
                line = self.process.stdout.readline()
                if not line: raise RuntimeError('PostgreSQL control session ended')
                if line.strip(): return json.loads(line)
        raise RuntimeError('PostgreSQL control query timed out')
    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('ROLLBACK;\n\\q\n'); self.process.stdin.flush()
                self.process.wait(timeout=5)
            except BaseException:
                self.process.kill(); self.process.wait(timeout=5)
        self.process.stdin.close(); self.process.stdout.close()

def wait_value(callback, predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = callback()
        if predicate(value): return value
        time.sleep(0.1)
    raise RuntimeError('Safe bootstrap wait timed out')

def frozen_attempt(database, cgroup=CGROUP, before_kill=None):
    # A direct freezer write keeps systemd stop/restart jobs out of this window.
    (cgroup / 'cgroup.freeze').write_text('1\n')
    killed = False
    try:
        wait_value(lambda: events(cgroup), lambda x: x.get('frozen') == '1', 10)
        # This is a transactional lock, NOT DDL. It waits for an old INSERT's
        # commit and prevents a kernel-buffered INSERT racing the final check.
        snapshot = database.query("BEGIN; SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='10s'; LOCK TABLE \"IngestJob\" IN ACCESS EXCLUSIVE MODE;\n" + SNAPSHOT_SQL)
        if not safe_to_kill(snapshot, events(cgroup)):
            return False
        # Old Web cannot reconnect while frozen. Stop its idle sessions while
        # holding the table barrier so pending INSERT cannot commit after kill.
        database.query("WITH stopped AS (SELECT pg_terminate_backend(pid) AS ok FROM pg_stat_activity WHERE datname='news_aggregator' AND usename='dogeow_news' AND pid<>pg_backend_pid()) SELECT json_build_object('terminated',count(*)) FROM stopped;")
        wait_value(lambda: database.query("SELECT json_build_object('connections',(SELECT count(*) FROM pg_stat_activity WHERE datname='news_aggregator' AND pid<>pg_backend_pid()));"), lambda x: x['connections'] == 0, 10)
        snapshot = database.query(SNAPSHOT_SQL)
        if not safe_to_kill(snapshot, events(cgroup)):
            raise RuntimeError('Frozen safety proof changed')
        # Linux kills frozen groups without rescheduling them. systemctl stop
        # would auto-thaw, so it is deliberately deferred until populated=0.
        if before_kill is not None:before_kill()
        (cgroup / 'cgroup.kill').write_text('1\n')
        killed = True
        wait_value(lambda: events(cgroup) if cgroup.exists() else {'populated':'0'}, lambda x: x.get('populated') == '0', 10)
        database.query("COMMIT; SELECT json_build_object('committed',true);")
        run(['systemctl', 'stop', UNIT])
        return True
    except BaseException as error:
        if killed:
            raise TakeoverSealed('Old group was terminated after the safety proof; keep maintenance/timer sealed for administrator recovery') from error
        raise
    finally:
        if not killed:
            # Close releases the table barrier before resuming a real task.
            database.close()
            (cgroup / 'cgroup.freeze').write_text('0\n')

# Installed modules are root-owned and outside every deployed release.
sys.path.insert(0,'/usr/local/libexec/dogeow-news')
sys.path.insert(1,str(Path(__file__).parent))
from news_first_state import (DurableTakeover,ProtocolError,CancelBeforeCommit,atomic_json,atomic_bytes,read_json,
                             file_lock,fsync_directory,identity,COMMITTED)
_module=Path('/usr/local/libexec/dogeow-news/publish_news.py')
if not _module.is_file():_module=Path(__file__).with_name('publish-news.py')
_spec=importlib.util.spec_from_file_location('news_fixed_publisher',_module)
P=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(P)

SERVICE='dogeow-news-first-takeover.service'
DEPLOY_STATE=Path('/var/lib/dogeow-news-deploy')
LEGACY_BLOCK=CONTROL/'legacy-no-start'
ROOT_CANCEL=CONTROL/'first-cancel.json'
ORIGINAL_LAUNCHER=CONTROL/'original-news-run'
STAGED_LAUNCHER=Path('/usr/local/libexec/dogeow-news/news-runtime.py')
RUNNER=Path('/usr/local/libexec/dogeow-test-news-run')


def protected_file(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_nlink!=1:
        raise ProtocolError('Required root-owned first controller file is not protected')


def replace_fixed(target,source):
    protected_file(source)
    temporary=target.with_name('.'+target.name+'.first-new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o755)
    with os.fdopen(fd,'wb') as output:
        output.write(source.read_bytes());output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o755)
    os.replace(temporary,target);fsync_directory(target.parent)


def root_preflight():
    for directory in [CONTROL,Path('/usr/local/libexec/dogeow-news')]:
        info=directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ProtocolError('Controller directory is not root protected')
    for path in [ORIGINAL_LAUNCHER,STAGED_LAUNCHER,Path('/usr/local/libexec/dogeow-test-news-collect')]:protected_file(path)
    if CONTROL.stat().st_dev!=P.RELEASES.stat().st_dev:
        raise ProtocolError('Claim and releases must share a filesystem for atomic activation')
    config=Path('/etc/nginx/conf.d/dogeow-test-news-https.conf').read_text()
    if 'if ($news_bootstrap_gate = "closed") { return 503; }' not in config:
        raise ProtocolError('Reviewed Nginx gate is not installed')
    condition=Path('/etc/systemd/system/dogeow-test-news-ingest.service.d/30-news-ci-result.conf').read_text()
    if 'ConditionPathExists=!/var/lib/dogeow-news-lock/bootstrap-maintenance' not in condition:
        raise ProtocolError('The old timer must also obey the bootstrap start condition')


def claim(revision,nonce):
    # Start a detached, root-only server task BEFORE publishing a root state.
    # With no state it idles without the execution lock or any host mutation.
    root_preflight();run(['systemctl','enable','--now',SERVICE])
    with file_lock(CONTROL/'claim.lock'),P.publication_lock():
        if FIRST_STATE.exists():
            state=read_json(FIRST_STATE,root_owned=True)
            if not identity(state,revision,nonce):raise ProtocolError('Different first SHA/nonce is already owned by root')
            return state
        root=CONTROL/'claims'/(revision+'-'+nonce)
        if root.exists():
            # A root CLI can die after the complete canonical directory rename
            # but before state commit. Its root-protected request is sufficient
            # for same-identity reentry; no surviving upload/SSH is required.
            request=read_json(root/'request.json',root_owned=True)
            if not identity(request,revision,nonce) or request.get('legacy')!=LEGACY:
                raise ProtocolError('Orphan canonical identity differs')
            state={**request,'phase':'claimed','claim_root':str(root),'public_open':False,'claimed_at':time.time()}
            if P.current_release()!=LEGACY:raise ProtocolError('Cannot adopt an orphan over another current release')
            Host().verify_claim(state)
            if not Host().verify_runtime(root/'runtime',state):raise ProtocolError('Orphan expanded runtime is incomplete')
            atomic_json(FIRST_STATE,state)
            return state
        ready=read_json(DEPLOY_STATE/'first-publish-ready.json')
        if not identity(ready,revision,nonce) or ready.get('schema')!=2 or ready.get('legacy')!=LEGACY or not isinstance(ready.get('expires_at'),(int,float)) or not math.isfinite(ready['expires_at']) or not time.time()<ready['expires_at']<=time.time()+1801:
            raise ProtocolError('Ready identity expired or does not match the requested package')
        if P.current_release()!=LEGACY:raise ProtocolError('Original release changed before claim')
        if run(['systemctl','show',UNIT,'-p','ActiveState','--value'])!='active':raise ProtocolError('Legacy must be serving before a new first claim')
        source=P.INCOMING/(revision+'.tar.gz')
        fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=pwd.getpwnam('news-deploy').pw_uid or info.st_nlink!=1 or info.st_size!=ready['archive_bytes'] or info.st_size>P.MAX_ARCHIVE:
            os.close(fd);raise ProtocolError('Incoming first package changed')
        root.parent.mkdir(mode=0o755,exist_ok=True)
        temporary=root.with_name('.prepare-'+root.name)
        if temporary.exists():
            if not temporary.is_dir() or temporary.is_symlink():raise ProtocolError('Unsafe interrupted claim path')
            shutil.rmtree(temporary)
        temporary.mkdir(mode=0o755)
        archive=temporary/'runtime.tar.gz'
        digest=hashlib.sha256()
        if shutil.disk_usage(CONTROL).free< P.MIN_FREE+info.st_size+ready['expanded_bytes']+16*1024**2:
            os.close(fd);raise ProtocolError('Claim copy and expansion must retain 1 GiB')
        with os.fdopen(fd,'rb') as src,archive.open('xb') as dst:
            while block:=src.read(1024*1024):digest.update(block);dst.write(block)
            dst.flush();os.fsync(dst.fileno())
        archive.chmod(0o400)
        if digest.hexdigest()!=ready['archive_sha256']:raise ProtocolError('First archive checksum changed')
        expected,expanded=P.inspect_archive(archive,revision)
        if expected!=ready['files'] or expanded!=ready['expanded_bytes']:raise ProtocolError('First manifest changed')
        runtime=temporary/'runtime';runtime.mkdir(mode=0o755)
        P.extract_archive(archive,runtime,expected)
        for directory,_,files in os.walk(runtime,followlinks=False):
            for name in files:
                path=Path(directory)/name
                if path.is_symlink():continue
                with path.open('rb') as content:os.fsync(content.fileno())
            fsync_directory(directory)
        atomic_json(temporary/'request.json',ready,mode=0o400)
        fsync_directory(temporary);os.rename(temporary,root);fsync_directory(root.parent)
        state={**ready,'phase':'claimed','claim_root':str(root),'public_open':False,'claimed_at':time.time()}
        # Root now owns a complete immutable source archive and verified runtime.
        # The SSH observer can die or delete its upload without affecting this.
        atomic_json(FIRST_STATE,state)
        source.unlink();fsync_directory(P.INCOMING)
        return state


class Host:
    enforce_root=True
    def claim_root(self,state):
        expected=CONTROL/'claims'/(state['revision']+'-'+state['nonce'])
        if state.get('claim_root')!=str(expected):raise ProtocolError('Canonical claim path mismatch')
        return expected
    def verify_claim(self,state):
        root=self.claim_root(state);archive=root/'runtime.tar.gz'
        protected_file(archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=state['archive_sha256']:raise ProtocolError('Canonical archive changed')
        expected,total=P.inspect_archive(archive,state['revision'])
        if expected!=state['files'] or total!=state['expanded_bytes']:raise ProtocolError('Canonical manifest changed')
    def cancelled(self,state):
        for path,owner in [(ROOT_CANCEL,True),(DEPLOY_STATE/'first-cancel.json',False)]:
            if path.exists() and identity(read_json(path,root_owned=owner),state['revision'],state['nonce']):return True
        return time.time()>=state['expires_at']
    def maintenance(self,state,checkpoint):
        root_preflight()
        MAINTENANCE.touch(mode=0o644,exist_ok=True);LEGACY_BLOCK.touch(mode=0o644,exist_ok=True);fsync_directory(CONTROL)
        DROPIN.parent.mkdir(parents=True,exist_ok=True)
        atomic_bytes(DROPIN,b'[Unit]\nConditionPathExists=!/var/lib/dogeow-news-lock/legacy-no-start\n[Service]\nRestart=no\n',preserve_metadata=True)
        run(['systemctl','daemon-reload'])
        run(['systemctl','stop',TIMER]);checkpoint('after_timer_stop')
        if run(['systemctl','show',UNIT,'-p','Restart','--value'])!='no':raise ProtocolError('Legacy automatic restart remains enabled')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open('https://news.dogeow.com/admin/login',timeout=10):raise ProtocolError('Loaded public maintenance gate is ineffective')
        except urllib.error.HTTPError as error:
            if error.code!=503:raise ProtocolError('Unexpected public maintenance status')
        # On a pre-commit process death the database barrier is gone. Resume
        # any legitimate paused work before making a fresh complete proof.
        if state['phase'] not in COMMITTED and CGROUP.exists() and events().get('frozen')=='1':
            (CGROUP/'cgroup.freeze').write_text('0\n')
    def drain_and_stop(self,state,commit,checkpoint):
        while True:
            committed=state['phase'] in COMMITTED
            if not committed and self.cancelled(state):return False
            if P.current_release()!=LEGACY:raise ProtocolError('Current changed during legacy drain')
            populated=CGROUP.exists() and events().get('populated')=='1'
            if not populated:
                if not committed:return False
                run(['systemctl','stop',UNIT]);return True
            if run(['systemctl','show',UNIT,'-p','ControlGroup','--value'])!='/system.slice/dogeow-test-news-web.service':raise ProtocolError('Web group changed')
            if run(['systemctl','show',INGEST,'-p','ActiveState','--value']) not in ['inactive','failed']:
                time.sleep(1);continue
            uid=pwd.getpwnam('dogeow-test-news').pw_uid
            for process in Path('/proc').iterdir():
                if not process.name.isdigit():continue
                try:
                    if process.stat().st_uid==uid and '0::/system.slice/dogeow-test-news-web.service\n' not in (process/'cgroup').read_text():raise ProtocolError('Unknown News runtime process')
                except FileNotFoundError:pass
            database=PostgreSQL()
            try:
                if database.query(SNAPSHOT_SQL)['running']:
                    time.sleep(1);continue
                # Same lock used by publisher cancellation and root claim.
                with P.publication_lock():
                    if not committed and self.cancelled(state):return False
                    try:
                        if frozen_attempt(database,before_kill=commit):
                            checkpoint('after_kill');return True
                    except CancelBeforeCommit:return False
                    except TakeoverSealed:raise
                    except RuntimeError:
                        if committed:raise
            finally:database.close()
            time.sleep(1)
    @contextlib.contextmanager
    def activation_lease(self,state):
        MAINTENANCE.touch(mode=0o644,exist_ok=True);fsync_directory(CONTROL)
        with P.publication_lock():
            fd=os.open(P.INGEST_LOCK,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_nlink!=1:raise ProtocolError('Stable ingestion lock changed')
                while True:
                    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:time.sleep(.25)
                yield
            finally:os.close(fd)
    def install_launcher(self,state):
        replace_fixed(RUNNER,STAGED_LAUNCHER)
    def verify_runtime(self,path,state):
        if not path.is_dir() or path.is_symlink():return False
        actual=set()
        for parent,dirs,files in os.walk(path,followlinks=False):
            for name in dirs[:]:
                item=Path(parent)/name
                if item.is_symlink():
                    if item!=path/'.next/cache' or os.readlink(item)!=str(P.APP/'shared/cache'):return False
                    dirs.remove(name)
            for name in files:
                file=Path(parent)/name;relative=file.relative_to(path).as_posix();actual.add(relative)
                if file.is_symlink() or relative not in state['files'] or hashlib.sha256(file.read_bytes()).hexdigest()!=state['files'][relative]:return False
        return actual==set(state['files'])
    def place_release(self,state):
        final=P.RELEASES/state['revision']
        if final.exists():
            if not self.verify_runtime(final,state):raise ProtocolError('Existing first release differs from immutable claim')
            return
        root=self.claim_root(state);runtime=root/'runtime'
        if not runtime.exists():
            if shutil.disk_usage(root).free<P.MIN_FREE+state['expanded_bytes']+16*1024**2:raise ProtocolError('Recovery expansion must retain 1 GiB')
            # A process death while re-expanding cannot leave a partial runtime
            # that blocks every later resume. Only our root-enclave scratch is
            # replaced; the canonical archive is never modified.
            recovering=root/'.recover-runtime'
            if recovering.exists():
                if not recovering.is_dir() or recovering.is_symlink():raise ProtocolError('Unsafe recovery scratch')
                shutil.rmtree(recovering)
            recovering.mkdir(mode=0o755)
            P.extract_archive(root/'runtime.tar.gz',recovering,state['files'])
            if not self.verify_runtime(recovering,state):raise ProtocolError('Re-expanded claim differs')
            for directory,_,files in os.walk(recovering,followlinks=False):
                for name in files:
                    file=Path(directory)/name
                    if not file.is_symlink():
                        with file.open('rb') as content:os.fsync(content.fileno())
                fsync_directory(directory)
            os.rename(recovering,runtime);fsync_directory(root)
        if not self.verify_runtime(runtime,state):raise ProtocolError('Claimed expanded runtime differs')
        os.rename(runtime,final);fsync_directory(P.RELEASES);fsync_directory(root)
    def switch_new(self,state):
        current=P.current_release()
        if current not in [LEGACY,state['revision']]:raise ProtocolError('Unexpected current during first activation')
        if current!=state['revision']:P.switch_current(state['revision'])
        fsync_directory(P.RELEASES)
        LEGACY_BLOCK.unlink(missing_ok=True);fsync_directory(CONTROL)
    def ensure_new_healthy(self,state):
        try:P.health(P.RELEASES/state['revision'],state['revision']);return
        except BaseException:pass
        run(['systemctl','restart',UNIT]);P.wait_health(P.RELEASES/state['revision'],state['revision'])
    def restore_new_schedule(self,state,checkpoint):
        DROPIN.unlink(missing_ok=True);fsync_directory(DROPIN.parent);run(['systemctl','daemon-reload'])
        run(['systemctl','start',TIMER]);checkpoint('after_timer_restore')
        wait_value(lambda:run(['systemctl','show',INGEST,'-p','ActiveState','--value']),lambda x:x in ['inactive','failed'],30)
    def remove_legacy(self,state):
        legacy=P.RELEASES/LEGACY
        if legacy.exists():P.remove_release(LEGACY)
        user=pwd.getpwnam('news-deploy')
        # Future ordinary publisher cleanup must be able to remove this code.
        for parent,dirs,files in os.walk(P.RELEASES/state['revision'],followlinks=False):
            os.chown(parent,user.pw_uid,user.pw_gid)
            for name in dirs+files:os.chown(Path(parent)/name,user.pw_uid,user.pw_gid,follow_symlinks=False)
    def open_ingress(self,state):
        MAINTENANCE.unlink(missing_ok=True);fsync_directory(CONTROL)
    def restore_legacy(self,state,checkpoint):
        if state['phase'] in COMMITTED or P.current_release()!=LEGACY:raise ProtocolError('Never restore legacy after kill commit or new current')
        MAINTENANCE.touch(mode=0o644,exist_ok=True)
        replace_fixed(RUNNER,ORIGINAL_LAUNCHER);checkpoint('abort_launcher')
        if CGROUP.exists() and events().get('frozen')=='1':(CGROUP/'cgroup.freeze').write_text('0\n')
        checkpoint('abort_thaw')
        DROPIN.unlink(missing_ok=True);LEGACY_BLOCK.unlink(missing_ok=True);run(['systemctl','daemon-reload'])
        if run(['systemctl','show',UNIT,'-p','ActiveState','--value'])!='active':run(['systemctl','start',UNIT])
        # Legacy does not expose the new /healthz. Verify its original contract.
        if P.request('/')[0]!=307 or P.request('/api/news')[0]!=401 or P.request('/admin/login')[0]!=200:raise ProtocolError('Legacy restore health failed')
        run(['systemctl','start',TIMER]);checkpoint('abort_timer')
        MAINTENANCE.unlink(missing_ok=True);fsync_directory(CONTROL);checkpoint('abort_open')
    def cleanup_claim(self,state):
        if state['phase'] not in ['completed','aborted']:return
        root=self.claim_root(state)
        if root.exists():
            if root.is_symlink():raise ProtocolError('Invalid own claim cleanup path')
            shutil.rmtree(root);fsync_directory(root.parent)


def serve():
    # No SSH parent and no executor lock while idle. The unit restarts even
    # after SIGTERM; terminal work idles until root explicitly finalizes it.
    while True:
        while not FIRST_STATE.exists():time.sleep(.25)
        with file_lock(CONTROL/'controller.lock'):
            DurableTakeover(FIRST_STATE,Host()).run()
        time.sleep(1)

def terminal_action(action,revision,nonce):
    state=read_json(FIRST_STATE,root_owned=True)
    expected='aborted' if action=='retire-aborted' else 'completed'
    if not identity(state,revision,nonce) or state['phase']!=expected or MAINTENANCE.exists():
        raise ProtocolError('Only an opened terminal identity may be finalized')
    run(['systemctl','disable','--now',SERVICE])
    with file_lock(CONTROL/'controller.lock'),P.publication_lock():
        state=read_json(FIRST_STATE,root_owned=True)
        if not identity(state,revision,nonce) or state['phase']!=expected:raise ProtocolError('Terminal identity changed')
        Host().cleanup_claim(state)
        if action=='retire-aborted':
            if P.current_release()!=LEGACY:raise ProtocolError('Aborted legacy is no longer current')
            history=CONTROL/'history';history.mkdir(mode=0o755,exist_ok=True)
            atomic_json(history/(revision+'-'+nonce+'-aborted.json'),state)
            for path in [DEPLOY_STATE/'first-publish-ready.json',DEPLOY_STATE/'first-cancel.json',ROOT_CANCEL]:
                if path.exists() and identity(read_json(path),revision,nonce):path.unlink()
            FIRST_STATE.unlink();fsync_directory(CONTROL)
    return state

def main(args):
    if os.geteuid()!=0:raise ProtocolError('Administrator-only first controller')
    if args==['--serve']:serve();return
    actions=['claim','resume','cancel','finalize','retire-aborted']
    if len(args)!=3 or args[0] not in actions or not re.fullmatch('[0-9a-f]{40}',args[1]) or not re.fullmatch('[0-9a-f]{32}',args[2]):raise ProtocolError('Expected fixed first controller action SHA nonce')
    action,revision,nonce=args
    if action=='claim':result=claim(revision,nonce)
    elif action in ['finalize','retire-aborted']:result=terminal_action(action,revision,nonce)
    else:
        state=read_json(FIRST_STATE,root_owned=True)
        if not identity(state,revision,nonce):raise ProtocolError('Recovery identity mismatch')
        if action=='cancel':
            with P.publication_lock():atomic_json(ROOT_CANCEL,{'revision':revision,'nonce':nonce})
        if state['phase'] not in ['completed','aborted']:run(['systemctl','enable','--now',SERVICE])
        result=state
    print(json.dumps({'revision':revision,'nonce':nonce,'phase':result['phase'],'server_controller_independent':True}))

if __name__=='__main__':
    try:main(sys.argv[1:])
    except BaseException as error:
        print(str(error),file=sys.stderr);sys.exit(1)
