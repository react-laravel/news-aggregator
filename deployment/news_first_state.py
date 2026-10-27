"""Root-owned durable first-takeover state machine. No project code is imported."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

CONTROL = Path('/var/lib/dogeow-news-lock')
STATE = CONTROL / 'first-state.json'
COMMITTED = {'kill_committed','old_dead','launcher_ready','release_ready','switch_intent','starting','healthy','open_intent','completed'}
PRECOMMIT = {'claimed','maintenance','draining','aborting'}

class ProtocolError(RuntimeError):
    pass
class CancelBeforeCommit(ProtocolError):
    pass

def fsync_directory(directory):
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def atomic_bytes(path,data,mode=0o644,preserve_metadata=False):
    path=Path(path)
    owner=None
    if preserve_metadata:
        try:info=path.lstat()
        except FileNotFoundError:pass
        else:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                raise ProtocolError('Atomic target must be a regular file')
            owner=(info.st_uid,info.st_gid);mode=stat.S_IMODE(info.st_mode)
    # Each writer cleans only its own same-directory scratch. No operation
    # opens/truncates the durable target before the fully synced replacement.
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(data);output.flush()
            current=os.fstat(output.fileno())
            if owner is not None and (current.st_uid,current.st_gid)!=owner:
                os.fchown(output.fileno(),*owner)
            os.fchmod(output.fileno(),mode);os.fsync(output.fileno())
        os.replace(temporary,path);fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)

def atomic_json(path,value,mode=0o644):
    atomic_bytes(path,(json.dumps(value,sort_keys=True)+'\n').encode('utf-8'),mode)

def identity(value,revision,nonce):
    return isinstance(value,dict) and value.get('revision')==revision and value.get('nonce')==nonce

def read_json(path,root_owned=False):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'r') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (root_owned and (info.st_uid!=0 or info.st_mode&0o022)):
            raise ProtocolError('Untrusted protocol record')
        data=source.read(4*1024**2+1)
        if len(data)>4*1024**2:raise ProtocolError('Protocol record exceeds limit')
        return json.loads(data)

@contextlib.contextmanager
def file_lock(path,nonblocking=False):
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ProtocolError('Invalid controller lock')
        fcntl.flock(fd,fcntl.LOCK_EX|(fcntl.LOCK_NB if nonblocking else 0));yield
    finally:os.close(fd)

class DurableTakeover:
    """Host is the fixed privileged adapter; tests use an in-memory fake host."""
    def __init__(self,path,host,checkpoint=None):
        self.path=Path(path);self.host=host;self.checkpoint=checkpoint or (lambda phase:None)
        self.state=read_json(self.path,root_owned=host.enforce_root)
    def save(self,phase,**fields):
        self.state.update(fields,phase=phase,updated_at=time.time())
        atomic_json(self.path,self.state);self.checkpoint(phase)
    def commit_kill(self):
        # Called while publish.lock, database barrier and frozen group proof
        # are all held. Cancel writers use publish.lock too.
        self.host.verify_claim(self.state)
        if self.state['phase'] not in COMMITTED and self.host.cancelled(self.state):
            raise CancelBeforeCommit('First request cancelled before irreversible commit')
        self.save('kill_committed')
    def run(self):
        phase=self.state['phase']
        if phase=='completed':
            # A historical reentry never rewinds a later normal deployment.
            self.host.cleanup_claim(self.state);return self.state
        if phase=='aborted':
            self.host.cleanup_claim(self.state);return self.state
        self.host.verify_claim(self.state)
        if phase in PRECOMMIT or phase=='kill_committed':
            if phase=='aborting' or (phase not in COMMITTED and self.host.cancelled(self.state)):
                self.save('aborting');self.host.restore_legacy(self.state,self.checkpoint)
                self.save('aborted',public_open=True);self.host.cleanup_claim(self.state);return self.state
            self.save('maintenance' if phase!='kill_committed' else 'kill_committed')
            self.host.maintenance(self.state,self.checkpoint)
            if self.state['phase']!='kill_committed':self.save('draining')
            outcome=self.host.drain_and_stop(self.state,self.commit_kill,self.checkpoint)
            if not outcome:
                if self.state['phase'] in COMMITTED:
                    raise ProtocolError('Committed takeover cannot restore legacy')
                self.save('aborting');self.host.restore_legacy(self.state,self.checkpoint)
                self.save('aborted',public_open=True);self.host.cleanup_claim(self.state);return self.state
            self.save('old_dead')
        # Every resumed post-commit activation is performed under the real
        # ingest lease. A crash after opening ingress cannot cause a restart
        # that kills a newly admitted collection.
        with self.host.activation_lease(self.state):
            self.host.install_launcher(self.state);self.save('launcher_ready')
            self.host.place_release(self.state);self.save('release_ready')
            self.save('switch_intent');self.host.switch_new(self.state);self.checkpoint('after_switch')
            self.save('starting');self.host.ensure_new_healthy(self.state);self.checkpoint('after_restart')
            self.save('healthy');self.host.restore_new_schedule(self.state,self.checkpoint)
            self.host.remove_legacy(self.state)
            self.save('open_intent');self.host.open_ingress(self.state);self.checkpoint('after_open')
            self.save('completed',public_open=True)
        self.host.cleanup_claim(self.state)
        return self.state
