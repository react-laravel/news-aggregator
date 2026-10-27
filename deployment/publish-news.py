#!/usr/bin/python3 -I
"""Fixed News-only publisher. Never reads private config or executes project tools."""
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import signal
import contextlib

APP = Path('/var/www/news.dogeow.com')
RELEASES = APP / 'releases'
STATE = Path('/var/lib/dogeow-news-deploy')
INCOMING = STATE / 'incoming'
GATE = STATE / 'gate/maintenance'
INGEST_LOCK = Path('/var/lib/dogeow-news-lock/ingest.lock')
FIRST_STATE = Path('/var/lib/dogeow-news-lock/first-state.json')
BOOTSTRAP_GATE = Path('/var/lib/dogeow-news-lock/bootstrap-maintenance')
LEGACY = 'source-30191069708-1'
SHA = re.compile('[0-9a-f]{40}\\Z')
MAX_ARCHIVE = 96 * 1024**2
MAX_UNPACKED = 200 * 1024**2
MIN_FREE = 1024**3
MAX_FILES = 15000
REQUIRED = {'server.js', 'ingest.cjs', 'package.json', '.next/BUILD_ID', '.next/routes-manifest.json', 'node_modules/next/package.json', 'node_modules/.prisma/client/package.json'}
PRIVATE = {'.git', '.ssh', '.codex', '.npmrc', '.gitconfig', 'auth.json', 'id_rsa', 'id_ed25519'}

class DeployError(RuntimeError):
    pass

def require(value, message):
    if not value:
        raise DeployError(message)

def revision_ok(value):
    require(isinstance(value, str) and SHA.fullmatch(value), 'Invalid revision')
    return value

def safe_path(name):
    path = PurePosixPath(name)
    require(name and path.as_posix() == name and not path.is_absolute() and '\\' not in name, 'Invalid archive path')
    require(all(p not in ['', '.', '..'] and not p.startswith('.env') and p not in PRIVATE for p in path.parts), 'Private or unsafe archive entry')
    require(path.parts[0] in {'.next', 'node_modules', 'public', 'prisma'} or name in {'server.js', 'ingest.cjs', 'package.json'}, 'Unexpected runtime entry')
    require(path.parts[:2] != ('.next', 'cache'), 'Cache cannot be uploaded')
    return path

def inspect_archive(path, revision):
    files = {}; manifest = None; total = 0
    with tarfile.open(path, 'r:gz') as source:
        for item in source:
            require(len(files) < MAX_FILES and item.isfile() and 0 <= item.size <= 64 * 1024**2, 'Unsupported archive entry')
            require(item.name not in files, 'Duplicate archive entry')
            total += item.size
            require(total <= MAX_UNPACKED, 'Expanded runtime exceeds limit')
            files[item.name] = item.size
            if item.name == 'deploy-manifest.json':
                require(item.size <= 4 * 1024**2, 'Manifest too large')
                manifest = json.loads(source.extractfile(item).read())
            else:
                safe_path(item.name)
    require(isinstance(manifest, dict) and manifest.get('schema') == 1 and manifest.get('revision') == revision, 'Manifest revision mismatch')
    expected = manifest.get('files')
    require(isinstance(expected, dict) and set(expected) == set(files) - {'deploy-manifest.json'} and REQUIRED <= set(expected), 'Manifest file list mismatch')
    require(all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) for v in expected.values()), 'Invalid file checksum')
    return expected, total

def extract_archive(archive, stage, expected):
    with tarfile.open(archive, 'r:gz') as source:
        for item in source:
            if item.name == 'deploy-manifest.json':
                continue
            require(item.isfile() and item.name in expected, 'Runtime changed after inspection')
            target = stage.joinpath(*safe_path(item.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            digest = hashlib.sha256(); count = 0
            with source.extractfile(item) as src, os.fdopen(fd, 'wb') as dst:
                while block := src.read(1024 * 1024):
                    count += len(block)
                    require(count <= item.size, 'Runtime size changed')
                    digest.update(block); dst.write(block)
                os.fchmod(dst.fileno(), 0o644)
            require(count == item.size and digest.hexdigest() == expected[item.name], 'Checksum failed')
    os.symlink(APP / 'shared/cache', stage / '.next/cache')
    for directory, _, _ in os.walk(stage, followlinks=False):
        os.chmod(directory, 0o755)

def current_release():
    require((APP / 'current').is_symlink() and os.readlink(APP / 'current') == 'releases/current', 'Protected outer link missing')
    path = RELEASES / 'current'
    require(path.is_symlink(), 'Current release link missing')
    name = os.readlink(path)
    require(name == LEGACY or SHA.fullmatch(name), 'Unknown current release')
    require((RELEASES / name).is_dir() and not (RELEASES / name).is_symlink(), 'Current release is not a directory')
    return name

def switch_current(name):
    require(name == LEGACY or SHA.fullmatch(name), 'Invalid activation target')
    temporary = RELEASES / ('.current-' + str(os.getpid()))
    os.symlink(name, temporary)
    try:
        os.replace(temporary, RELEASES / 'current')
    finally:
        temporary.unlink(missing_ok=True)

def command(args, timeout=60):
    result = subprocess.run(args, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0, 'Fixed service operation failed; output suppressed')
    return result.stdout

def restart_web():
    command(['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'restart', 'dogeow-test-news-web.service'], timeout=120)
    command(['/usr/bin/systemctl', 'is-active', '--quiet', 'dogeow-test-news-web.service'])

class HTTPS(http.client.HTTPSConnection):
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', 443), timeout=10)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)

def request(path):
    connection = HTTPS('news.dogeow.com', context=ssl.create_default_context(), timeout=10)
    try:
        connection.request('GET', path, headers={'Host': 'news.dogeow.com', 'Accept': 'application/json'})
        response = connection.getresponse(); body = response.read(4 * 1024**2 + 1)
        require(len(body) <= 4 * 1024**2, 'Health response too large')
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), body
    finally:
        connection.close()

def health(release, revision):
    status, headers, body = request('/healthz')
    require(status == 200 and json.loads(body) == {'ok': True, 'revision': revision} and headers.get('cache-control') == 'no-store', 'Revision/database readiness failed')
    require(request('/')[0] == 307 and request('/api/news')[0] == 401, 'Original anonymous access contract changed')
    status, _, body = request('/admin/login')
    require(status == 200, 'Login page failed')
    urls = set(re.findall(r'(?:src|href)=[\"\'](/_next/static/[^\"\'>?]+)', body.decode()))
    require(urls, 'Missing static asset references')
    for url in urls:
        relative = url.removeprefix('/_next/static/')
        require('..' not in PurePosixPath(relative).parts, 'Unsafe asset reference')
        path = release / '.next/static' / relative
        code, _, data = request(url)
        require(path.is_file() and code == 200 and hashlib.sha256(data).digest() == hashlib.sha256(path.read_bytes()).digest(), 'Runtime asset differs')

def wait_health(release, revision):
    last = None
    for _ in range(12):
        try:
            health(release, revision); return
        except (DeployError, ValueError, OSError, http.client.HTTPException) as error:
            last = error; time.sleep(1)
    raise DeployError('News readiness failed') from last

def remove_release(name):
    require(name == LEGACY or SHA.fullmatch(name), 'Unknown cleanup target')
    path = RELEASES / name
    require(path.is_dir() and not path.is_symlink() and shutil.rmtree.avoids_symlink_attacks, 'Unsafe release cleanup')
    shutil.rmtree(path)

@contextlib.contextmanager
def publication_lock():
    fd=os.open(STATE/'publish.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield

def read_first_state():
    try:
        fd=os.open(FIRST_STATE,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    except FileNotFoundError:return None
    with os.fdopen(fd,'r') as source:
        info=os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,'Root first state is not protected')
        return json.load(source)

def first_identity(record,revision,nonce):
    return isinstance(record,dict) and record.get('revision')==revision and record.get('nonce')==nonce

def atomic_record(path,payload):
    temporary=path.with_name(path.name+'.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o644)
    with os.fdopen(fd,'w') as output:
        json.dump(payload,output);output.flush();os.fsync(output.fileno())
    os.replace(temporary,path)

def stage_first(revision):
    archive=INCOMING/(revision+'.tar.gz')
    info=archive.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and info.st_size<=MAX_ARCHIVE,'Invalid first archive')
    files,expanded=inspect_archive(archive,revision)
    ready=STATE/'first-publish-ready.json'
    require(not ready.exists(),'An earlier ready record must be claimed or cancelled before staging another request')
    nonce=uuid.uuid4().hex
    payload={'schema':2,'revision':revision,'legacy':LEGACY,'nonce':nonce,'archive_bytes':info.st_size,
             'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'expanded_bytes':expanded,
             'expires_at':time.time()+1800,'files':files}
    atomic_record(ready,payload)
    return nonce

def cancel_first(revision,nonce):
    # Shared with root claim and final kill-commit check. Once claimed, the
    # immutable root package is outside every publisher cleanup path.
    with publication_lock():
        root=read_first_state()
        ready=STATE/'first-publish-ready.json'
        payload=json.loads(ready.read_text()) if ready.exists() else None
        if first_identity(root,revision,nonce):
            atomic_record(STATE/'first-cancel.json',{'revision':revision,'nonce':nonce})
            return
        if first_identity(payload,revision,nonce):
            (INCOMING/(revision+'.tar.gz')).unlink(missing_ok=True)
            ready.unlink()

def observe_first(revision,nonce):
    completed=False;deadline=time.monotonic()+1800
    try:
        while time.monotonic()<deadline:
            result=read_first_state()
            if first_identity(result,revision,nonce):
                if result.get('phase')=='completed' and result.get('public_open') is True:
                    require(not os.path.lexists(BOOTSTRAP_GATE),'Root controller has not reopened ingress')
                    completed=True
                    print(json.dumps({'published':revision,'nonce':nonce,'healthy':True,'root_durable_controller_completed':True}));return
                require(result.get('phase')!='aborted','First request was safely cancelled; legacy remains serving')
            time.sleep(0.25)
        raise DeployError('Observation timed out; any claimed first takeover continues in the independent server controller')
    finally:
        if not completed:cancel_first(revision,nonce)

def admission_gate():
    fd = os.open(GATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    os.write(fd, (str(os.getpid()) + '\n').encode()); os.close(fd)
    fd = os.open(INGEST_LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022 and info.st_nlink == 1, 'Invalid stable ingestion lock')
    deadline = time.monotonic() + 1200
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                require(time.monotonic() < deadline, 'Existing ingestion has not finished; old Web retained')
                time.sleep(0.25)
    except BaseException:
        os.close(fd)
        GATE.unlink(missing_ok=True)
        raise

def publish(revision):
    old = current_release()
    require(old != LEGACY,'First publication is staged and controlled independently by root')
    require(old != revision, 'Revision already active')
    require(not os.path.lexists(RELEASES / revision), 'Release already exists')
    require({p.name for p in RELEASES.iterdir()} == {old, 'current'}, 'Unknown release directory; review before deletion')
    archive = INCOMING / (revision + '.tar.gz')
    info = archive.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1 and info.st_size <= MAX_ARCHIVE, 'Invalid uploaded archive')
    expected, expanded = inspect_archive(archive, revision)
    require(shutil.disk_usage(RELEASES).free >= expanded + MIN_FREE, 'Extraction must retain at least 1 GiB free')
    stage = Path(tempfile.mkdtemp(prefix='.prepare-' + revision + '-', dir=RELEASES))
    final = RELEASES / revision
    activated = False; accepted = False; lease = None; reopen_admission = True
    try:
        extract_archive(archive, stage, expected)
        # Free upload space before the maintenance period; keep old runtime intact.
        archive.unlink()
        os.rename(stage, final)
        lease = admission_gate()
        switch_current(revision); activated = True
        restart_web()
        wait_health(final, revision)
        accepted = True
        remove_release(old)
        print(json.dumps({'published': revision, 'healthy': True, 'retained_releases': 1, 'only_web_restarted': True, 'timer_untouched': True, 'database_migrated': False}))
    except BaseException:
        if activated and not accepted:
            switch_current(old)
            try:
                restart_web()
                wait_health(RELEASES / old, old)
            except BaseException:
                reopen_admission = False
                raise DeployError('Rollback readiness failed; ingestion gate remains closed for administrator recovery')
        raise
    finally:
        # Keep the task lease until rollback or accepted cleanup has completed.
        if lease is not None:
            os.close(lease)
            if reopen_admission:
                GATE.unlink(missing_ok=True)
        if stage.exists():
            shutil.rmtree(stage)
        if not accepted and final.exists() and current_release() != revision:
            remove_release(revision)
        archive.unlink(missing_ok=True)

def receive(revision, source):
    for previous in INCOMING.iterdir():
        require(re.fullmatch('[0-9a-f]{40}\\.tar\\.gz', previous.name) and previous.is_file() and not previous.is_symlink(), 'Unknown incoming entry')
        previous.unlink()
    require(shutil.disk_usage(INCOMING).free >= MAX_ARCHIVE + MIN_FREE, 'Upload must retain at least 1 GiB free')
    target = INCOMING / (revision + '.tar.gz')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as dst:
            total = 0
            while block := source.read(1024 * 1024):
                total += len(block)
                require(total <= MAX_ARCHIVE, 'Upload exceeds limit')
                dst.write(block)
            require(total, 'Empty upload')
        print(json.dumps({'received': revision, 'compressed_bytes': total}))
    except BaseException:
        target.unlink(missing_ok=True)
        raise

def main(args):
    require(os.geteuid() == pwd.getpwnam('news-deploy').pw_uid and os.geteuid() != 0, 'Only the restricted News deployment account may publish')
    require(len(args) == 2 and args[0] in {'receive', 'publish', 'validate'}, 'Invalid command')
    command_name, revision = args; revision_ok(revision)
    for root in [APP, APP / 'shared', INGEST_LOCK.parent]:
        info = root.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, 'Protected directory is writable')
    for path in [STATE, INCOMING, RELEASES, STATE / 'gate']:
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'Deploy directory permissions invalid')
    first_nonce=None
    with publication_lock():
        root=read_first_state()
        require(not root or root.get('phase') in {'completed','aborted'},'A root-owned first takeover is active; use its original observer/administrator recovery')
        if command_name=='receive':
            receive(revision,sys.stdin.buffer)
        elif command_name=='publish':
            if current_release()==LEGACY:first_nonce=stage_first(revision)
            else:publish(revision)
        else:
            require(current_release()==revision,'Validation revision is not active')
            wait_health(RELEASES/revision,revision)
            print(json.dumps({'healthy':True,'revision':revision,'collection_triggered':False}))
    if first_nonce is not None:
        # No publish lock is held while the root actor claims or runs.
        observe_first(revision,first_nonce)

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except BaseException as error:
        print(str(error) if isinstance(error, DeployError) else 'News command failed; inspect protected logs', file=sys.stderr)
        sys.exit(1)
