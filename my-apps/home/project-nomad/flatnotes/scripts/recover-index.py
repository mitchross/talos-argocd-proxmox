#!/usr/bin/env python3
"""Preserve the audited Whoosh EOF index; flatnotes rebuilds from Markdown."""
import hashlib
import json
import os
from pathlib import Path
import shutil


def recover(root, opener):
    root = Path(root)
    index = root / '.flatnotes'
    archive = root / '.flatnotes-recovery-20260909'
    if index.is_symlink():
        raise RuntimeError('Refusing a symlink index')
    if not index.exists():
        return 'No index: normal application startup will build it'
    if not index.is_dir():
        raise RuntimeError('Index is not a directory')
    try:
        opened = opener(str(index), indexname='5')
        opened.close()
        return 'Existing index opens successfully; unchanged'
    except TypeError as error:
        if str(error) != 'ord() expected a character, but string of length 0 found':
            raise
    files = list(index.iterdir())
    if not files or any(p.is_symlink() or not p.is_file() for p in files):
        raise RuntimeError('Unexpected index layout; manual inspection required')
    if shutil.disk_usage(root).free < max(64 * 1024**2, sum(p.stat().st_size for p in files) * 2):
        raise RuntimeError('Insufficient headroom for index rebuild; original unchanged')
    digests = {}
    for path in files:
        with path.open('rb') as stream:
            digests[path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.mkdir(mode=0o700)  # Exclusive: never overwrite an earlier recovery.
    with (archive / 'sha256.json').open('x') as stream:
        json.dump(digests, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(index, archive / 'index')  # Same PVC: preserves every original byte.
    for directory in (archive, root):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return 'Original index retained in .flatnotes-recovery-20260909/index; application will rebuild'


if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/app/server')
    from whoosh.index import open_dir
    print(recover('/data', open_dir))
