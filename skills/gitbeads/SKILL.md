---
name: gitbeads
description: Use when work spans multiple turns or sessions and needs a repo-local issue tracker with dependencies, ready-task discovery, and git history, without external services or nonstandard dependencies.
---

# Gitbeads

`gitbeads` is a repo-local task tracker for humans and agents. It combines
`beads`-style dependency-aware work management with `ticgit`'s "tickets travel
with git" model.

## When to use it

Use this skill when:

- work has multiple steps, blockers, or dependencies
- progress must survive session loss or compaction
- the repository needs a durable local backlog instead of chat-only planning
- you want task state in git without a database or background daemon

Do not use it for one-off work that can be completed in a single short turn.

## Operating rules

- Prefer the CLI over reading the hidden tracker checkout directly.
- Keep tickets concise. Store only durable task state, not long design notes.
- Use dependencies to model blocking relationships instead of embedding plans in chat.
- Commit tracker changes with the code they describe when practical.
- Prefer setting priority explicitly when triaging non-trivial work.

## Storage model

- The canonical tracker lives on the `gitbeads` branch.
- The CLI keeps a hidden git worktree at `.git/gitbeads/`.
- Tickets live there as `issues/<state>/GB-<n>.json`.
- The directory is the canonical state: `open`, `claimed`, `blocked`, `closed`.
- One ticket per file
- Compact structured fields: `title`, `body`, `deps`, `labels`, `owner`, `priority`
- Optional per-ticket event history lives in sibling `GB-<n>.events.jsonl` files.
- Git is the audit trail; `gitbeads log` shows ticket history

This keeps the backlog shared across feature branches while avoiding working-tree clutter.

## Commands

Run the CLI with:

`skills/gitbeads/gitbeads <command>`

Core commands:

- `init`: create the store if missing
- `new "Title" --body "..." --priority 2`: create a ticket
- `list`: list all tickets, ordered by priority
- `list --format compact|normal|verbose|json`: choose output detail
- `list --state open --state claimed`: filter by state
- `list --ready-only`: show only ready issues
- `summary`: print compact counts by status and ready-ness
- `ready --format compact`: list open tickets whose dependencies are all closed
- `next --format verbose`: print the first ready ticket, optionally claiming it
- `claim GB-1 --owner alice`: claim a specific ticket
- `show GB-1 --history`: print one ticket as JSON, optionally with event history
- `update GB-1 --state blocked --priority 4`
- `dep GB-2 GB-1`: make `GB-2` depend on `GB-1`
- `note GB-1 "local context"`: append a durable note to the issue history
- `history GB-1`: show per-issue event history
- `export GB-1`: copy a visible scratch copy to `.gitbeads-export/`
- `import GB-1`: import a scratch copy back into the tracker
- `close GB-1`: mark done
- `log GB-1`: show git history for the ticket file

## Recommended workflow

At the start of multi-step work:

```bash
skills/gitbeads/gitbeads summary
skills/gitbeads/gitbeads ready --format compact
skills/gitbeads/gitbeads next --show-body
```

When beginning a task:

```bash
skills/gitbeads/gitbeads next --claim --owner alice
```

When new follow-up work appears:

```bash
skills/gitbeads/gitbeads new "Add feature"
skills/gitbeads/gitbeads dep GB-3 GB-1
```

When finishing:

```bash
skills/gitbeads/gitbeads close GB-1
```

## Design intent

This tool is intentionally boring:

- no database
- no background service
- no hidden remote state beyond git itself
- no manual branch switching by the caller

If the script is missing or broken, callers can still inspect the hidden worktree and the `gitbeads` branch directly as a fallback.

## Notes

- Mutating commands use optimistic concurrency checks and will refuse to commit if the tracker changed mid-command.
- For embedding guidance in a host repository, see [references/embedding.md](references/embedding.md).
