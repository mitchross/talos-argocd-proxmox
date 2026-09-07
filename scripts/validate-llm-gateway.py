#!/usr/bin/env python3
"""Reject direct local LLM endpoints in application configuration.

Includes tracked .env files even when generic ignore rules hide them from rg.
Backend service/route definitions and LiteLLM's own upstream are intentional.
This is a configuration check, not proof of deployed application traffic.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BACKEND = re.compile(r'https?://(?:vllm-service(?:\.vllm(?:\.svc(?:\.cluster\.local)?)?)?|'
                     r'llama-cpp-service(?:\.llama-cpp(?:\.svc(?:\.cluster\.local)?)?)?|'
                     r'(?:vllm|llama)\.vanillax\.me)(?=[:/\s\"\x27]|$)')
SUFFIXES = {'.yaml', '.yml', '.json', '.env'}
ALLOWED = {'my-apps/ai/litellm/config.yaml'}
BACKEND_DIRS = ('my-apps/ai/vllm/', 'my-apps/ai/llama-cpp/')


def violations(paths):
    failures = []
    for relative in paths:
        if relative in ALLOWED or relative.startswith(BACKEND_DIRS):
            continue
        path = ROOT / relative
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if BACKEND.search(line):
                failures.append(f'{relative}:{number}: direct LLM URL bypasses LiteLLM')
    return failures


def main():
    paths = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '--',
         'my-apps', 'monitoring', 'infrastructure'], cwd=ROOT, text=True).splitlines()
    failures = violations(sorted(set(paths)))
    for failure in failures:
        print(failure)
    if failures:
        raise SystemExit(1)
    print('No direct vLLM/legacy URLs found in application configuration.')


if __name__ == '__main__':
    main()
