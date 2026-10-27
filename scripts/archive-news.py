#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import sys
import tarfile

root = Path('.news-runtime')
revision = sys.argv[1]
spec = importlib.util.spec_from_file_location('publisher', 'deployment/publish-news.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.revision_ok(revision)
manifest = json.loads((root / 'deploy-manifest.json').read_text())
with tarfile.open('news-runtime.tar.gz', 'w:gz', compresslevel=6) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_dir():
            continue
        if not path.is_file() or path.is_symlink():
            raise ValueError('Only regular runtime files are allowed')
        archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
archive = Path('news-runtime.tar.gz')
if archive.stat().st_size > module.MAX_ARCHIVE:
    raise ValueError('Compressed runtime exceeds upload allowance')
files, total = module.inspect_archive(archive, revision)
print(json.dumps({'revision': revision, 'compressed_bytes': archive.stat().st_size, 'expanded_bytes': total, 'files': len(files), 'private_settings_included': False}))
