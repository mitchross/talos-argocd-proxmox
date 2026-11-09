---
name: qwen-verify-by-running
description: Use before saying any change is done. Prove it with a real run.
version: 1.0.0
metadata:
  hermes:
    tags: [Testing, Verification, Qwen-Lab]
    category: qwen-lab
---

# Nothing is done until it ran

## Steps

1. Before you edit, find how the project checks itself: look for `Makefile`, `package.json`
   scripts, `Cargo.toml`, `pyproject.toml`, `tests/`. Run the tests once so you know the start state.
2. Make one small change.
3. Run the check that proves it: the test for that code, or the command that shows the new behaviour.
4. Read the output. Passing means exit code 0 and the test you care about listed as passed.
5. If it failed, read the first error, fix that one thing, and run again. After 3 failed tries,
   stop and report what you tried.
6. Report with the real output, trimmed to the lines that matter:

```
Ran: <command>
Result: <pass/fail line, test count>
```

## Rules

- Never write "should work", "probably passes" or "I believe it's fixed". Run it or say you didn't.
- Never edit a test just to make it pass, unless the card says the test is wrong.
- A new feature gets a new test.
