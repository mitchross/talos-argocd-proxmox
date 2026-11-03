#!/usr/bin/env python3
"""Stage a pinned checkpoint; publish readiness only after every artifact verifies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request


class ModelCache:
    def __init__(self, manifest):
        raw = Path(manifest).read_bytes()
        self.spec = json.loads(raw)
        self.revision = hashlib.sha256(raw).hexdigest()
        self.directory = self.spec['directory']
        for name in [self.directory] + [f['name'] for f in self.spec['files']]:
            if Path(name).name != name or name in ('', '.', '..'):
                raise ValueError(f'Expected a flat checkpoint name: {name!r}')

    @staticmethod
    def valid(path, artifact):
        if not path.is_file() or path.stat().st_size != artifact['size']:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == artifact['sha256']

    def marker(self, root):
        return Path(root) / self.directory / '.verified-manifest'

    def ready(self, root):
        marker = self.marker(root)
        try:
            if marker.read_text().strip() != self.revision:
                return False
            return all((marker.parent / f['name']).stat().st_size == f['size']
                       for f in self.spec['files'])
        except FileNotFoundError:
            return False

    def begin(self, root):
        marker = self.marker(root)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.unlink(missing_ok=True)
        return marker.parent

    def finish(self, root):
        marker = self.marker(root)
        part = marker.with_suffix('.part')
        part.write_text(self.revision + '\n')
        part.replace(marker)
        print(f'Verified checkpoint: {marker.parent}', flush=True)

    def download(self, root, source_url=None):
        directory = self.begin(root)
        base = source_url or f"https://huggingface.co/{self.spec['repo']}/resolve/{self.spec['revision']}"
        for artifact in self.spec['files']:
            destination = directory / artifact['name']
            if self.valid(destination, artifact):
                continue
            part = destination.with_name(destination.name + '.part')
            offset = part.stat().st_size if part.exists() else 0
            if offset >= artifact['size']:
                part.unlink()
                offset = 0
            request = urllib.request.Request(base + '/' + artifact['name'])
            if offset:
                request.add_header('Range', f'bytes={offset}-')
            print(f"Downloading {artifact['name']}", flush=True)
            with urllib.request.urlopen(request, timeout=120) as response:
                resume = offset and response.status == 206
                if resume and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise ValueError('Server resumed at the wrong byte offset')
                with part.open('ab' if resume else 'wb') as stream:
                    shutil.copyfileobj(response, stream, length=8 * 1024 * 1024)
            if not self.valid(part, artifact):
                part.unlink(missing_ok=True)
                raise ValueError(f"Downloaded checksum/size mismatch: {artifact['name']}")
            part.replace(destination)
        self.finish(root)

    def sync(self, source, target):
        directory = self.begin(target)
        if not self.ready(source):
            raise ValueError('Archive is not complete for this manifest')
        for artifact in self.spec['files']:
            origin = Path(source) / self.directory / artifact['name']
            if not self.valid(origin, artifact):
                raise ValueError(f"Archive checksum/size mismatch: {artifact['name']}")
            destination = directory / artifact['name']
            if self.valid(destination, artifact):
                continue
            part = destination.with_name(destination.name + '.part')
            print(f"Copying {artifact['name']}", flush=True)
            shutil.copyfile(origin, part)
            if not self.valid(part, artifact):
                part.unlink(missing_ok=True)
                raise ValueError(f"Local checksum/size mismatch: {artifact['name']}")
            part.replace(destination)
        self.finish(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['download', 'sync', 'wait'])
    parser.add_argument('--manifest', default='/opt/repo-scripts/model-manifest.json')
    parser.add_argument('--source', default='/src')
    parser.add_argument('--target', default='/models')
    parser.add_argument('--timeout', type=int, default=21600)
    args = parser.parse_args()
    model = ModelCache(args.manifest)
    if args.action == 'download':
        model.download(args.target)
    elif args.action == 'sync':
        model.sync(args.source, args.target)
    else:
        deadline = time.monotonic() + args.timeout
        while not model.ready(args.target):
            if time.monotonic() >= deadline:
                raise TimeoutError('Checkpoint staging did not complete')
            print('Waiting for verified local checkpoint', flush=True)
            time.sleep(10)
        print('Local checkpoint ready', flush=True)


if __name__ == '__main__':
    main()
