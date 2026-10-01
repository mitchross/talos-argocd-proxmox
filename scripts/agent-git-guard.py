#!/usr/bin/env python3
"""Deny obvious default-branch git writes; never grant tool permission.

This is a narrow shell-token check, not a shell interpreter or security sandbox.
Only read-only git queries run here. Server branch protection remains necessary.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def git_value(cwd, *args):
    result = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True,
                            text=True, timeout=3)
    return result.stdout.strip() if result.returncode == 0 else ''


def protected(cwd):
    names = {'main', 'master'}
    default = git_value(cwd, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD')
    if default:
        names.add(default.removeprefix('origin/'))
    return names


def unsafe_ref(ref, names):
    destination = ref.lstrip('+').split(':')[-1].removeprefix('refs/heads/')
    return destination in names or '*' in destination


def reason(command, cwd):
    lexer = shlex.shlex(command.replace('\n', ';'), posix=True, punctuation_chars=';&|()')
    lexer.whitespace_split = True
    tokens = list(lexer)
    segments, part = [], []
    for token in tokens + [';']:
        if token and all(c in ';&|()' for c in token):
            if part:
                segments.append(part)
                part = []
        else:
            part.append(token)
    directory = Path(cwd)
    for segment in segments:
        if segment[0] == 'cd' and len(segment) == 2:
            directory = (directory / segment[1]).resolve()
            continue
        for position, token in enumerate(segment):
            if Path(token).name != 'git':
                continue
            args = segment[position + 1:]
            target, index = directory, 0
            while index < len(args):
                flag = args[index]
                if flag in ('-C', '-c', '--git-dir', '--work-tree'):
                    if index + 1 >= len(args):
                        return 'Cannot resolve git global option; run a simple git command.'
                    if flag == '-C':
                        target = (target / args[index + 1]).resolve()
                    elif flag in ('--git-dir', '--work-tree'):
                        return 'Use git -C for repository writes so the branch can be checked.'
                    index += 2
                elif flag.startswith('-c') or flag.startswith('--no-') or flag == '--bare':
                    index += 1
                elif flag.startswith(('--git-dir=', '--work-tree=')):
                    return 'Use git -C for repository writes so the branch can be checked.'
                else:
                    break
            if index >= len(args) or args[index] not in ('commit', 'push'):
                continue
            operation, rest = args[index], args[index + 1:]
            names = protected(target)
            branch = git_value(target, 'symbolic-ref', '--short', '-q', 'HEAD')
            if not branch:
                return 'Cannot establish a writable feature branch; use a simple git -C command.'
            if branch in names:
                return f'No {operation} on default branch {branch}; use a feature branch and PR.'
            if operation == 'push':
                if any(arg in ('--all', '--mirror') for arg in rest):
                    return 'Bulk pushes can write the default branch; push a named feature branch.'
                if any(unsafe_ref(arg, names) for arg in rest):
                    return 'No push to a default branch; push a feature branch and open a PR.'
                configured = git_value(target, 'config', '--get-regexp', r'^remote\..*\.push$')
                if any(unsafe_ref(line.split(maxsplit=1)[1], names)
                       for line in configured.splitlines() if ' ' in line):
                    return 'Configured remote push refspec can write the default branch.'
                mode = git_value(target, 'config', 'push.default')
                upstream = git_value(target, 'config', f'branch.{branch}.merge')
                if mode == 'matching' or (mode in ('', 'simple', 'upstream') and unsafe_ref(upstream, names)):
                    # An explicit feature refspec overrides push.default/upstream.
                    positional = [arg for arg in rest if not arg.startswith('-')]
                    if len(positional) < 2:
                        return 'Implicit push may target the default branch; supply a feature refspec.'
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        inputs = payload.get('tool_input', {})
        message = reason(inputs.get('command', inputs.get('cmd', '')), payload.get('cwd', os.getcwd()))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        message = f'Branch check failed ({type(exc).__name__}); retry with a simple git command.'
    if message:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
              'permissionDecision': 'deny', 'permissionDecisionReason': message}}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
