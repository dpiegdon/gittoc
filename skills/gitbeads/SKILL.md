---
name: gitbeads
description: Use when work spans multiple turns or sessions and needs a repo-local issue tracker with dependencies, ready-task discovery, and git history, without external services or nonstandard dependencies.
---

# Gitbeads

`gitbeads` is a repo-local task tracker for Codex. It combines `beads`-style
agent workflows with `ticgit`'s "tickets travel with git" model.

## When to use it

Use this skill when:

- work has multiple steps, blockers, or dependencies
- progress must survive session loss or compaction
- the repository needs a durable local backlog instead of chat-only planning
- you want task state in git without a database or background daemon

Do not use it for one-off work that can be completed in a single short turn.

## Operating rules

- Prefer the CLI over reading `.codex/issues/` directly.
- Keep tickets concise. Store only durable task state, not long design notes.
- Use dependencies to model blocking relationships instead of embedding plans in chat.
- Commit tracker changes with the code they describe when practical.

## Storage model

- Tickets live at `.codex/issues/open/GB-XXXX.json`
- One ticket per file
- Compact structured fields: `title`, `body`, `status`, `deps`, `labels`, `owner`
- Git is the audit trail; `gitbeads log` shows ticket history

This keeps the store local to the repo while avoiding large markdown backlogs in prompt context.

## Commands

Run the CLI with:

```bash
python3 scripts/gitbeads.py <command>
```

Core commands:

- `init`: create the store if missing
- `new "Title" --body "..."`: create a ticket
- `list`: list all tickets
- `summary`: print compact counts by status and ready-ness
- `ready`: list open tickets whose dependencies are all closed
- `next`: print the first ready ticket, optionally claiming it
- `show GB-0001`: print one ticket as JSON
- `update GB-0001 --status claimed --owner codex`
- `dep GB-0002 GB-0001`: make `GB-0002` depend on `GB-0001`
- `close GB-0001`: mark done
- `log GB-0001`: show git history for the ticket file

## Recommended Codex workflow

At the start of multi-step work:

```bash
python3 scripts/gitbeads.py summary
python3 scripts/gitbeads.py ready
python3 scripts/gitbeads.py next
```

When beginning a task:

```bash
python3 scripts/gitbeads.py next --claim --owner codex
```

When new follow-up work appears:

```bash
python3 scripts/gitbeads.py new "Add feature"
python3 scripts/gitbeads.py dep GB-0003 GB-0001
```

When finishing:

```bash
python3 scripts/gitbeads.py close GB-0001
```

## Design intent

This tool is intentionally boring:

- no database
- no background service
- no hidden remote state
- no mandatory branch switching

If the script is missing or broken, Codex can still inspect and edit the JSON files directly as a fallback.
