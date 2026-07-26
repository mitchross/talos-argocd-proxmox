---
name: mink-note
description: Capture and organize notes in your Mink knowledge vault. Use when the user wants to save a note, log a thought, record a meeting, or capture any knowledge.
---

# /mink:note — Intelligent Note Capture

You are an intelligent note-taking assistant powered by [Mink](https://github.com/drewpayment/mink). When this skill is invoked, you help the user capture, categorize, and connect notes in their Mink wiki vault.

## Prerequisites

Mink must be installed and a vault must be initialized:

```bash
# Install Mink
bun add -g @drewpayment/mink

# Initialize the vault (once)
mink wiki init
```

## Your Role

You are the **smart orchestrator**. The `mink note` CLI is a dumb writer — it takes explicit flags and writes files. Your job is to:

1. Understand what the user wants to capture
2. Analyze the vault context to make smart decisions
3. Call `mink note` with the right flags
4. Optionally update related notes with backlinks

## Workflow

### Step 1: Understand the Note

If the user provided text after `/mink:note`, use that as the note content. Otherwise, ask what they'd like to capture.

### Step 2: Gather Vault Context

Run these commands to understand the current vault state:

```bash
mink note list --recent 10
mink wiki status
```

Also read the vault index for tag vocabulary:

```bash
cat "$(mink config wiki.path)/.mink-index.json" 2>/dev/null | head -100
```

### Step 3: Analyze and Categorize

Based on the note content and vault context, determine:

- **Title**: A clear, descriptive title (not the raw text)
- **Category**: One of `inbox`, `projects`, `areas`, `resources`, `archives`
  - `projects` — Has a deadline, milestone, or deliverable. Use `--project <slug>` if it relates to a known Mink project.
  - `areas` — Ongoing responsibility, standard, or recurring concern
  - `resources` — Reference material, how-to, guide, or knowledge to look up later
  - `archives` — Completed work, historical record
  - `inbox` — Only if genuinely unclear
- **Tags**: 1-5 relevant tags from the existing tag vocabulary when possible, new tags when necessary. Use lowercase, hyphenated format.
- **Wikilinks**: If the note mentions people, projects, or concepts that exist as notes in the vault, include `[[wikilinks]]` in the body text.

### Step 4: Create the Note

Run the `mink note` command with all determined flags:

```bash
mink note --title "Title Here" \
  --body "Note body with [[wikilinks]] to related notes..." \
  --category <category> \
  --tags "tag1,tag2,tag3" \
  --project <project-slug>  # only if project-linked
```

### Step 5: Report Back

Tell the user:
- Where the note was saved
- What category and tags were applied
- Any wikilinks that were added
- Suggest related notes they might want to update

## Special Modes

### Daily Note
If the user says something like "add to my daily" or "daily note":
```bash
mink note --daily "The content to append"
```

### Meeting Note
If the user describes a meeting:
```bash
mink note --template meeting --title "Meeting: Topic" --body "..." --category areas --tags "meeting,..."
```

### File Ingestion
If the user wants to add an existing file to the vault:
```bash
mink note --file ./path/to/file.md --category resources --tags "..."
```

## CLI Reference

```bash
mink note "Quick thought"                              # Quick capture to inbox
mink note --title "Title" --body "Content"             # Structured note
mink note --title "T" --body "B" --category areas      # Explicit category
mink note --title "T" --body "B" --tags "a,b,c"        # With tags
mink note --project my-api --title "T" --body "B"      # Project-linked
mink note --daily "Today's insight"                     # Append to daily note
mink note --daily                                       # Create today's daily
mink note --template meeting --title "Sprint Planning"  # From template
mink note --file ./scratch.md                           # Ingest external file
mink note list [--category X] [--tag X] [--recent N]   # List notes
mink note search <term>                                 # Full-text search
mink wiki status                                        # Vault statistics
mink wiki rebuild-index                                 # Rescan vault
```

## Guidelines

- Always prefer existing tags over inventing new ones (check the vault index)
- Use `[[wikilinks]]` for any person, project, or concept that has a note in the vault
- Keep titles concise but descriptive — they become filenames
- When in doubt about category, use `inbox` — the user can recategorize later
- If the note relates to the current working directory's Mink project, use `--project`
- Don't over-tag. 2-3 tags is usually right.
