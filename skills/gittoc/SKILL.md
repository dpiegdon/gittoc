---
name: gittoc
description: Use when work spans multiple turns or sessions and needs a repo-local issue tracker with dependencies, ready-task discovery, and git history, without external services or nonstandard dependencies.
---

# Gittoc

`gittoc` is a repo-local task tracker for humans and agents. It combines
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

- The canonical tracker lives on the `gittoc` branch.
- The CLI keeps a hidden git worktree at `.git/gittoc/`.
- Tickets live there as `issues/<state>/T-<n>.json`.
- The directory is the canonical state: `open`, `claimed`, `blocked`, `closed`.
- One ticket per file
- Compact structured fields: `title`, `body`, `deps`, `labels`, `owner`, `priority`
- Optional per-ticket event history lives in sibling `T-<n>.events.jsonl` files.
- Git is the audit trail; `gittoc log` shows ticket history
- Internal code is split into focused modules under `skills/gittoc/gittoc_lib/`.

This keeps the backlog shared across feature branches while avoiding working-tree clutter.

## Commands

Run the CLI with:

`skills/gittoc/gittoc <command>`

Core commands:

- `init`: create the store if missing
- `refresh`: reload tracker state after conflict errors and print current summary
- `remote --format json`: inspect inferred and configured tracker remote wiring
- `remote --set origin`: configure the tracker branch to use a specific remote
- `pull origin`: fetch and merge the tracker branch from a remote
- `push origin`: push the tracker branch to a remote
- `new "Title" --body "..." --priority 2`: create a ticket
- `list`: list open tickets by default, ordered by priority
- `l`: short alias for `list`
- `list --all`: list all tickets
- `list --format compact|normal|verbose|json`: choose output detail
- `list --state open --state claimed`: filter by state
- `list --ready-only`: show only ready issues
- `summary`: print compact counts by status and ready-ness
- `s`: short alias for `summary`
- `ready --format compact`: convenience alias for `list --ready-only`
- `resume`: recover the most relevant current ticket context
- `r`: short alias for `resume`
- `resume T-1 --format json`: recover a specific ticket as structured data
- `claim T-1 --owner alice`: claim a specific ticket
- `c T-1 --owner alice`: short alias for `claim`
- `show T-1`: print one ticket as JSON with the latest recent notes
- `sh T-1`: short alias for `show`
- `show T-1 --history`: print one ticket as JSON with full event history
- `show T-1 --field id --field title --field priority`: request a minimal JSON field subset
- `update T-1 --state blocked --priority 4`
- `dep T-2 T-1`: make `T-2` depend on `T-1`
- `note T-1 "local context"`: append a durable note to the issue history
- `n T-1 "local context"`: short alias for `note`
- `history T-1`: show per-issue event history
- `history T-1 --limit 5`: show only the most recent events
- `history T-1 --notes-only --limit 3`: show only recent durable notes
- `close T-1`: mark done
- `log T-1`: show git history for the ticket file

## Recommended workflow

At the start of multi-step work:

```bash
skills/gittoc/gittoc summary
skills/gittoc/gittoc refresh
skills/gittoc/gittoc resume
skills/gittoc/gittoc list --ready-only --format compact
```

When beginning a task:

```bash
skills/gittoc/gittoc claim T-1 --owner alice
```

When new follow-up work appears:

```bash
skills/gittoc/gittoc new "Add feature"
skills/gittoc/gittoc dep T-3 T-1
```

When finishing:

```bash
skills/gittoc/gittoc close T-1
```

## Design intent

This tool is intentionally boring:

- no database
- no background service
- no hidden remote state beyond git itself
- no manual branch switching by the caller

If the script is missing or broken, callers can still inspect the hidden worktree and the `gittoc` branch directly as a fallback.

## Notes

- Mutating commands use optimistic concurrency checks and will refuse to commit if the tracker changed mid-command.
- When that happens, run `skills/gittoc/gittoc refresh` and retry against the new tracker head.
- `init` will auto-configure `gittoc.remote` from the repo's inferred main remote when one is available.
- `pull <remote>` fetches and attempts a normal merge of `remote/gittoc`; merge conflicts are left for explicit resolution in `.git/gittoc`.
- `resume` without an id prefers claimed tickets owned by the current user, then the highest-priority ready issue, then the highest-priority open issue.
- `resume` includes recent notes by default so it can replace most one-ticket “what now?” lookups.
- In some sandboxed agent environments, writes under `.git/gittoc/` may require explicit approval even though this is not normally a problem in a local shell.
- If tracker mutations fail with a read-only or permission error under `.git/gittoc/`, the environment may be blocking `.git` writes rather than the tool itself.
- For embedding guidance in a host repository, see [references/embedding.md](references/embedding.md).
