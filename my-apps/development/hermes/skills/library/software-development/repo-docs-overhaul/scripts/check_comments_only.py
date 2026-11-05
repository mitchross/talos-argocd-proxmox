#!/usr/bin/env python3
"""Prove a diff changes only comments.

  check_comments_only.py <repo> [--base REF]

For each changed .rs/.ts/.tsx/.js/.jsx/.mjs/.cjs file, strip comments with a small
lexer (strings, raw strings, char literals, template literals aware), collapse
whitespace, and compare base vs working tree. Fenced ``` blocks inside comments
(Rust doctests, JSDoc examples) count as code, so editing them fails the check.
Exit 1 if any file's code changed. Non-code files are listed, not checked.
"""
import re, subprocess, sys

EXT = ('.rs', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')
CHAR_LIT = re.compile(r"'(\\(x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^\\'\n])'")


def strip(src, rust):
    out, comments, i, n = [], [], 0, len(src)
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == '//':
            j = src.find('\n', i)
            j = n if j < 0 else j
            comments.append(src[i:j]); i = j
        elif two == '/*':
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith('/*', j) and rust: depth += 1; j += 2
                elif src.startswith('*/', j): depth -= 1; j += 2
                else: j += 1
            comments.append(src[i:j]); out.append(' '); i = j
        elif rust and c == 'r' and re.match(r'r#*"', src[i:]) and (i == 0 or not (src[i-1].isalnum() or src[i-1] == '_')):
            m = re.match(r'r(#*)"', src[i:]); end = '"' + m.group(1)
            j = src.find(end, i + len(m.group(0)))
            j = n if j < 0 else j + len(end)
            out.append(src[i:j]); i = j
        elif c == '"' or (not rust and c in "'`"):
            q, j = c, i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == '\\' else 1
            out.append(src[i:j + 1]); i = j + 1
        elif rust and c == "'":
            m = CHAR_LIT.match(src, i)
            if m: out.append(m.group(0)); i = m.end()
            else: out.append(c); i += 1
        else:
            out.append(c); i += 1
    fences = []
    for cm in comments:
        body = '\n'.join(re.sub(r'^\s*(///?!?|/\*\*?|\*/?|\*)', '', l) for l in cm.split('\n'))
        fences += re.findall(r'```.*?```', body, flags=re.S)
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()
    return norm(''.join(out)), [norm(f) for f in fences]


def git(repo, *a):
    return subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True)


def main():
    repo = sys.argv[1]
    base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else 'HEAD'
    files = [f for f in git(repo, 'diff', '-z', '--name-only', base).stdout.split('\0') if f]
    bad, checked, other = 0, 0, []
    for f in files:
        if not f.endswith(EXT):
            other.append(f); continue
        old = git(repo, 'show', f'{base}:{f}').stdout
        try:
            new = open(f'{repo}/{f}', encoding='utf-8').read()
        except FileNotFoundError:
            print('DELETED', f); bad += 1; continue
        rust = f.endswith('.rs')
        checked += 1
        if strip(old, rust) != strip(new, rust):
            a, b = strip(old, rust)[0], strip(new, rust)[0]
            k = next((x for x in range(min(len(a), len(b))) if a[x] != b[x]), min(len(a), len(b)))
            print(f'CODE CHANGED {f}: ...{a[max(0,k-60):k+60]!r} -> ...{b[max(0,k-60):k+60]!r}')
            bad += 1
    print(f'checked {checked} code files; code changed in {bad}; non-code files changed: {other}')
    sys.exit(1 if bad else 0)


main()
