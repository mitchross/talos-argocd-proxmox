#!/usr/bin/env python3
"""Size an unslop / plain-English pass before editing.

Usage: scan_prose_tells.py <repo_dir>
Prints JSON rows {f, w, em, voc, emo, inl} for tracked *.md prose files:
words, em dashes, AI-vocabulary hits, emojis and `**Label:**` bullets, all
counted outside fenced code. Skips agent instruction files, changelogs,
vendored dirs, archives, skill libraries and dated records (YYYY-MM-DD in path).
Bin-pack the rows by `w` (about 10k words per child).
"""
import json, re, subprocess, sys

repo = sys.argv[1] if len(sys.argv) > 1 else '.'
SKIP = re.compile(r'(^|/)(CLAUDE|AGENTS|SKILL|CHANGELOG|LICENSE|SOUL)\.md$|(^|/)\.(claude|agents|github|codex|cursor)/'
                  r'|node_modules/|vendor/|/_archive/|(^|/)\d{4}-\d{2}-\d{2}|/results\.md$|/skills/', re.I)
VOCAB = re.compile(r'\b(additionally|crucial|delve|enhance|fostering|garner|interplay|intricate|pivotal|showcase|'
                   r'tapestry|testament|underscore|vibrant|leverage|utilize|seamless(ly)?|robust|serves as|in order to)\b', re.I)
EMOJI = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50]')

out = subprocess.run(['git', '-C', repo, 'ls-files', '-z', '*.md'], capture_output=True, text=True).stdout
rows = []
for f in filter(None, out.split('\0')):  # -z keeps paths with spaces whole
    if SKIP.search(f):
        continue
    t = re.sub(r'```.*?```', '', open(f'{repo}/{f}', encoding='utf-8', errors='ignore').read(), flags=re.S)
    rows.append(dict(f=f, w=len(t.split()), em=t.count('\u2014'), voc=len(VOCAB.findall(t)),
                     emo=len(EMOJI.findall(t)), inl=len(re.findall(r'^\s*[-*] \*\*[^*]+:\*\*', t, re.M))))
print(json.dumps(rows))
