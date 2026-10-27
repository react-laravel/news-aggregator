#!/usr/bin/python3 -I
"""Installed root-owned. Runtime UID only; lock survives exec until all work exits."""
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

BASE = Path('/var/www/news.dogeow.com')
LOCK = Path('/var/lib/dogeow-news-lock/ingest.lock')
GATE = Path('/var/lib/dogeow-news-deploy/gate/maintenance')
BOOTSTRAP_GATE = Path('/var/lib/dogeow-news-lock/bootstrap-maintenance')
NODE = '/opt/codex-node-v24.16.0/bin/node'
RUNTIME = 'dogeow-test-news'
LEGACY = '038dd4cb63a594d695638ae6a55c2965d24d94f6'


def acquire(lock=LOCK, gate=GATE):
    # Root owns the directory and this stable inode; neither UID can replace it.
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
        os.close(fd)
        raise RuntimeError('Invalid ingestion lock')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Lock-before-gate is essential: a publisher first closes admission,
        # then waits on this same inode. No check-then-start gap exists.
        if os.path.lexists(gate) or os.path.lexists(BOOTSTRAP_GATE):
            raise BlockingIOError('发布维护中，请稍后再试')
        return fd
    except BaseException:
        os.close(fd)
        raise


def environment(mode, release):
    config = json.loads((BASE / 'shared/runtime-env.json').read_text())
    env = dict(config[mode])
    env.update(PATH='/opt/codex-node-v24.16.0/bin:/usr/bin:/bin', NODE_ENV='production',
               HOSTNAME='127.0.0.1', PORT='3008', NEXT_TELEMETRY_DISABLED='1',
               NODE_OPTIONS='--max-old-space-size=256',
               NEWS_REVISION=release.name if re.fullmatch('[0-9a-f]{40}', release.name) else LEGACY)
    return env


def main(args):
    if os.geteuid() != pwd.getpwnam(RUNTIME).pw_uid:
        raise RuntimeError('Only the News runtime account may collect')
    if not (1 <= len(args) <= 2 and args[0] in ['web', 'ingest']):
        raise RuntimeError('Invalid collector command')
    if len(args) == 2 and not re.fullmatch('[A-Za-z0-9_-]{1,128}', args[1]):
        raise RuntimeError('Invalid source id')
    try:
        fd = acquire()
    except BlockingIOError:
        print(json.dumps({'error': '采集任务正在运行或发布维护中，请稍后再试'}, ensure_ascii=False))
        return 75
    root = (BASE / 'current').resolve(strict=True)
    if root.parent != BASE / 'releases':
        raise RuntimeError('Invalid News release')
    env = environment(args[0], root)
    os.chdir(root)
    os.set_inheritable(fd, True)
    os.execve(NODE, [NODE, str(root / 'ingest.cjs'), *args[1:]], env)
    return 1


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        print(json.dumps({'error': '采集程序无法安全启动'}, ensure_ascii=False))
        sys.exit(1)
