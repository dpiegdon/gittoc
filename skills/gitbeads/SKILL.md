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
- Tickets live there as `issues/<state>/GB-XXXX.json`.
- The directory is the canonical state: `open`, `claimed`, `blocked`, `closed`.
- One ticket per file
- Compact structured fields: `title`, `body`, `deps`, `labels`, `owner`, `priority`
- Git is the audit trail; `gitbeads log` shows ticket history

This keeps the backlog shared across feature branches while avoiding working-tree clutter.

## Commands

Run the CLI with:

`skills/gitbeads/gitbeads <command>`

Core commands:

- `init`: create the store if missing
- `new "Title" --body "..." --priority 2`: create a ticket
- `list`: list all tickets, ordered by priority
- `list --state open --state claimed`: filter by state
- `list --ready-only`: show only ready issues
- `summary`: print compact counts by status and ready-ness
- `ready`: list open tickets whose dependencies are all closed
- `next`: print the first ready ticket, optionally claiming it
- `claim GB-0001 --owner alice`: claim a specific ticket
- `show GB-0001`: print one ticket as JSON
- `update GB-0001 --state blocked --priority 4`
- `dep GB-0002 GB-0001`: make `GB-0002` depend on `GB-0001`
- `close GB-0001`: mark done
- `log GB-0001`: show git history for the ticket file

## Recommended workflow

At the start of multi-step work:

```bash
skills/gitbeads/gitbeads summary
skills/gitbeads/gitbeads ready
skills/gitbeads/gitbeads next --show-body
```

When beginning a task:

```bash
skills/gitbeads/gitbeads next --claim --owner alice
```

When new follow-up work appears:

```bash
skills/gitbeads/gitbeads new "Add feature"
skills/gitbeads/gitbeads dep GB-0003 GB-0001
```

When finishing:

```bash
skills/gitbeads/gitbeads close GB-0001
```

## Design intent

This tool is intentionally boring:

- no database
- no background service
- no hidden remote state beyond git itself
- no manual branch switching by the caller

If the script is missing or broken, callers can still inspect the hidden worktree and the `gitbeads` branch directly as a fallback.

## References

- Short design note: [references/design-improvements.md](references/design-improvements.md)
