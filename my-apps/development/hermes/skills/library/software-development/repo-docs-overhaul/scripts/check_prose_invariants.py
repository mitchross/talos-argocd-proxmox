#!/usr/bin/env python3
"""Check that a prose-only rewrite kept the facts.

Compares every changed *.md file in the working tree against a base ref and
reports changes to: fenced code blocks, link targets, inline `code` spans,
and numbers in prose (counts lost). Also counts em dashes left outside code.

Usage: check_prose_invariants.py [--base HEAD] [repo_dir]
Any line printed is a spot to read by hand; arrows turned into words
(`A -> B` becoming `A`, then `B`) show up as INLINE diffs and are usually fine.
"""
import re, subprocess, sys
from collections import Counter

args = sys.argv[1:]
base = 'HEAD'
if '--base' in args:
    i = args.index('--base'); base = args[i + 1]; del args[i:i + 2]
repo = args[0] if args else '.'

def sh(*c):
    return subprocess.run(c, cwd=repo, capture_output=True, text=True).stdout

FENCE = re.compile(r'```.*?```', re.S)
INLINE = re.compile(r'`[^`\n]+`')

def parts(t):
    fences = FENCE.findall(t)
    rest = FENCE.sub('', t)
    links = re.findall(r'\]\(([^)]+)\)', rest)
    inline = INLINE.findall(rest)
    prose = INLINE.sub('', rest)
    nums = re.findall(r'\d+(?:\.\d+)?', prose)
    return fences, links, inline, nums, prose.count('\u2014')

# -z: paths with spaces (design exports, "Web scraper for ...") must stay one path
files = [f for f in sh('git', 'diff', '-z', '--name-only', base).split('\0') if f.endswith('.md')]
left = 0
for f in files:
    old = sh('git', 'show', f'{base}:{f}')
    try:
        new = open(f'{repo}/{f}', encoding='utf-8').read()
    except FileNotFoundError:
        print(f, 'DELETED'); continue
    a, b = parts(old), parts(new)
    out = []
    if a[0] != b[0]:
        out.append('FENCES changed')
    if Counter(a[1]) != Counter(b[1]):
        out.append(f'LINKS -{sorted(set(a[1]) - set(b[1]))} +{sorted(set(b[1]) - set(a[1]))}')
    if Counter(a[2]) != Counter(b[2]):
        out.append(f'INLINE -{sorted(set(a[2]) - set(b[2]))[:5]} +{sorted(set(b[2]) - set(a[2]))[:5]}')
    lost = Counter(a[3]) - Counter(b[3])
    if lost:
        out.append(f'NUMS lost {dict(lost)}')
    if b[4]:
        out.append(f'em dashes left in prose: {b[4]}')
    left += b[4]
    if out:
        print(f, '|', '; '.join(out))
print(f'{len(files)} files checked, {left} em dashes left in prose')
