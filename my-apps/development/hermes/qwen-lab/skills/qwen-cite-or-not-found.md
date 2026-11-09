---
name: qwen-cite-or-not-found
description: Use when answering any factual question. Cite a source or say NOT FOUND.
version: 1.0.0
metadata:
  hermes:
    tags: [Research, Grounding, Qwen-Lab]
    category: qwen-lab
---

# Cite it or say NOT FOUND

A wrong answer that sounds sure is worse than NOT FOUND.

## Steps

1. Decide where the answer lives: a file, a command, the web, or memory.
2. Get it from there:
   - File: `read_file` or `search_files`. Cite `path:line`.
   - Command: run it. Cite the command and the output line.
   - Web: `web_search`, then open the page with the browser tool and read it. Cite the URL and quote
     the sentence.
   - Memory: cite it as "memory", and check it against a file or command if it matters.
3. Write the answer. Put the source right after each claim, like `(docs.vllm.ai/...: "quote")`.
4. If no source says it, write `NOT FOUND` and list what you checked.

## Rules

- Never fill a gap from what you remember about versions, flags, paths, prices or dates.
- One good primary source (official docs, source code, release notes) beats three blog posts.
- If two sources disagree, show both and say which is newer.
