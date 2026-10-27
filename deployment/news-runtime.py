#!/usr/bin/python3 -I
"""Replacement for the existing fixed runtime launcher, installed by admin."""
import os
from pathlib import Path
import sys
sys.path.insert(0, '/usr/local/libexec/dogeow-news')
from news_collect import environment, BASE, NODE

mode = sys.argv[1:]
if mode == ['ingest']:
    os.execv('/usr/local/libexec/dogeow-test-news-collect', ['/usr/local/libexec/dogeow-test-news-collect', 'ingest'])
if mode != ['web']:
    raise SystemExit(2)
root = (BASE / 'current').resolve(strict=True)
if root.parent != BASE / 'releases':
    raise SystemExit(2)
os.chdir(root)
os.execve(NODE, [NODE, str(root / 'server.js')], environment('web', root))
