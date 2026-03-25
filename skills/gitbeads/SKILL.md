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
- Internal code is split into focused modules under `skills/gitbeads/gitbeads_lib/`.

This keeps the backlog shared across feature branches while avoiding working-tree clutter.

## Commands

Run the CLI with:

`skills/gitbeads/gitbeads <command>`

Core commands:

- `init`: create the store if missing
- `refresh`: reload tracker state after conflict errors and print current summary
- `new "Title" --body "..." --priority 2`: create a ticket
- `list`: list open tickets by default, ordered by priority
- `list --all`: list all tickets
- `list --format compact|normal|verbose|json`: choose output detail
- `list --state open --state claimed`: filter by state
- `list --ready-only`: show only ready issues
- `summary`: print compact counts by status and ready-ness
- `ready --format compact`: list open tickets whose dependencies are all closed
- `ready-one --format json`: return the single highest-priority ready issue
- `next --format verbose`: print the first ready ticket, optionally claiming it
- `resume`: recover the most relevant current ticket context
- `resume GB-1 --format json`: recover a specific ticket as structured data
- `claim GB-1 --owner alice`: claim a specific ticket
- `show GB-1 --history`: print one ticket as JSON, optionally with event history
- `show GB-1 --field id --field title --field priority`: request a minimal JSON field subset
- `update GB-1 --state blocked --priority 4`
- `dep GB-2 GB-1`: make `GB-2` depend on `GB-1`
- `note GB-1 "local context"`: append a durable note to the issue history
- `history GB-1`: show per-issue event history
- `history GB-1 --limit 5`: show only the most recent events
- `history GB-1 --notes-only --limit 3`: show only recent durable notes
- `export GB-1`: copy a visible scratch copy to `.gitbeads-export/`
- `import GB-1`: import a scratch copy back into the tracker
- `close GB-1`: mark done
- `log GB-1`: show git history for the ticket file

## Recommended workflow

At the start of multi-step work:

```bash
skills/gitbeads/gitbeads summary
skills/gitbeads/gitbeads refresh
skills/gitbeads/gitbeads resume
skills/gitbeads/gitbeads ready --format compact
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
- When that happens, run `skills/gitbeads/gitbeads refresh` and retry against the new tracker head.
- `resume` without an id prefers claimed tickets owned by the current user, then the highest-priority ready issue, then the highest-priority open issue.
- For embedding guidance in a host repository, see [references/embedding.md](references/embedding.md).
