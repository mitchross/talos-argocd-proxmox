#!/usr/bin/env python3
"""Prepare reviewed Radar practice promotions and weights in Git; never deploy."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/mitchross/radar-ng-tile-server'
STAGES = ROOT / 'my-apps/practice'
TAG = re.compile(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?')


def read(path):
    return yaml.safe_load(path.read_text())


def write(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False, width=110))


def stage_path(stage):
    return STAGES / ('radar-practice-' + stage)


def get_release(stage):
    if stage == 'prod':
        d = read(stage_path('prod') / 'stable-image.yaml')
        image = d['spec']['template']['spec']['containers'][0]['image']
        tag, digest = image.removeprefix(IMAGE + ':').split('@', 1)
        return tag, digest
    path = stage_path('prod') / 'candidate/kustomization.yaml' if stage == 'candidate' else stage_path(stage) / 'kustomization.yaml'
    image = next(i for i in read(path)['images'] if i['name'] == IMAGE)
    return image['newTag'], image['digest']


def verify_release(tag, digest=None):
    if not TAG.fullmatch(tag):
        raise ValueError('Use a published vMAJOR.MINOR.PATCH release tag.')
    result = subprocess.check_output(['docker', 'buildx', 'imagetools', 'inspect', IMAGE + ':' + tag,
                                      '--format', '{{json .Manifest.Digest}}'], text=True)
    actual = json.loads(result)
    if not isinstance(actual, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', actual):
        raise ValueError('Registry returned an invalid image digest.')
    if digest and digest != actual:
        raise ValueError('The source tag was republished; do not promote changed contents.')
    return actual


def set_release(stage, tag, digest):
    label = {'pairs': {'app.kubernetes.io/version': tag}, 'includeSelectors': False, 'includeTemplates': True}
    if stage == 'prod':
        path = stage_path('prod') / 'stable-image.yaml'
        d = read(path)
        d['spec']['template']['spec']['containers'][0]['image'] = f'{IMAGE}:{tag}@{digest}'
        d['metadata'].setdefault('labels', {})['app.kubernetes.io/version'] = tag
        d['spec']['template'].setdefault('metadata', {}).setdefault('labels', {})['app.kubernetes.io/version'] = tag
    else:
        path = stage_path('prod') / 'candidate/kustomization.yaml' if stage == 'candidate' else stage_path(stage) / 'kustomization.yaml'
        d = read(path)
        for image in d['images']:
            if image['name'] == IMAGE:
                image.update(newTag=tag, digest=digest)
        d['labels'] = [x for x in d.get('labels', []) if 'app.kubernetes.io/version' not in x['pairs']] + [label]
    write(path, d)


def set_weight(percent):
    if not 0 <= percent <= 100:
        raise ValueError('Candidate percentage must be between 0 and 100.')
    path = stage_path('prod') / 'httproute.yaml'
    d = read(path)
    for ref in d['spec']['rules'][0]['backendRefs']:
        ref['weight'] = percent if ref['name'] == 'radar-api-canary' else 100 - percent
    write(path, d)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    stage = commands.add_parser('stage', help='Verify a published image and propose it in int.')
    stage.add_argument('tag')
    promote = commands.add_parser('promote', help='Copy the tested immutable source release into the next stage.')
    promote.add_argument('target', choices=['cert', 'candidate', 'prod'])
    weight = commands.add_parser('weight', help='Prepare a stable-route split; no API calls.')
    weight.add_argument('percent', type=int)
    commands.add_parser('status', help='Print desired stage pins and weights.')
    args = parser.parse_args()
    try:
        if args.command == 'status':
            for stage in ['int', 'cert', 'candidate', 'prod']:
                tag, digest = get_release(stage)
                print(f'{stage:9} {tag}@{digest}')
            print(read(stage_path('prod') / 'httproute.yaml')['spec']['rules'][0]['backendRefs'])
            return 0
        if args.command == 'stage':
            set_release('int', args.tag, verify_release(args.tag))
        elif args.command == 'weight':
            set_weight(args.percent)
        else:
            source = {'cert': 'int', 'candidate': 'cert', 'prod': 'candidate'}[args.target]
            # A new candidate must have no stable traffic while its image changes.
            route = read(stage_path('prod') / 'httproute.yaml')
            refs = {r['name']: r['weight'] for r in route['spec']['rules'][0]['backendRefs']}
            if args.target == 'candidate' and refs['radar-api-canary'] != 0:
                raise ValueError('First merge weight 0 and verify it live; candidate updates must start with preview-only traffic.')
            if args.target == 'prod' and refs['radar-api-canary'] != 100:
                raise ValueError('First merge weight 100 and verify it live before replacing the retained stable version.')
            tag, digest = get_release(source)
            verify_release(tag, digest)
            set_release(args.target, tag, digest)
        print('Updated local manifests only. Inspect git diff, render, commit to a branch and open a PR.')
        print('Promotion requires separate merged stages and live checks; this script cannot prove a stage passed.')
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
