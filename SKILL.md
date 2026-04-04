---
name: gittoc
description: Use when work spans multiple turns or sessions and needs a repo-local issue tracker with dependencies, ready-task discovery, and git history, without external services or nonstandard dependencies.
---

# Gittoc

`gittoc` is a repo-local task tracker for humans and agents. Tickets travel
with git, with no database or background daemon.

## When to use it

Use this skill when:

- work has multiple steps, blockers, or dependencies
- progress must survive session loss or compaction
- the repository needs a durable local backlog instead of chat-only planning

Do not use it for one-off work that can be completed in a single short turn.

## Operating rules

- Prefer the CLI over reading the hidden tracker checkout directly.
- Keep tickets concise — store only durable task state, not long design notes.
- Use dependencies to model blocking relationships.
- Commit tracker changes with the code they describe when practical.

## Storage model

- Canonical tracker state lives on the `gittoc` branch.
- A hidden git worktree at `.git/gittoc/` serves as the working checkout.
- Tickets live as `issues/<state>/T-<n>.json`; directory is canonical state.
- States: `open`, `claimed`, `blocked`, `closed`, `rejected`.
- Fields: `title`, `body`, `deps`, `labels`, `owner`, `priority`.
- Optional per-ticket event history in sibling `T-<n>.events.jsonl` files.

## Suggested labels

Labels are free-form, but these conventions help with filtering and grooming:

- `ready` — groomed, spec is clear, no open design questions, safe to implement
- `feature` — new capability
- `bug` — something broken
- `ux` — user-facing experience improvement
- `docs` — documentation only
- `chore` — maintenance, cleanup, refactoring
- `perf` — performance improvement
- `ops` — operational/infrastructure concern
- `concept` — needs design discussion before implementation
- `human` — requires human action, not agent-implementable

## Commands

Invoke as `gittoc <command>` or `tools/gittoc/gittoc <command>` or
`git toc <command>` if the alias is configured. Use `--help` on any command
for full argument documentation.

**Backlog**
- `summary` / `sum` — ticket counts by state
- `list` / `l` — open tickets by priority; `-a` for all states
- `list -s claimed -s blocked` — filter by state
- `list -l bug` / `list -l feature,ux` — filter by label (AND; comma or repeated -l)
- `unblocked` — only tickets with no unmet dependencies
- `labels` / `labels -a` — all labels in use with counts
- `grep PATTERN [-i] [-n]` — search open ticket files; `-a` for all states, `-s closed` for specific
- `list --sort=id` — chronological order instead of priority

**Working with tickets**
- `new "Title" -p 2 -b "context" -l feature` — create a ticket
- `claim T-1` / `c T-1` — claim a ticket (defaults owner to `$GITTOC_OWNER` / `$USER`)
- `claimed` — list all currently claimed issues
- `update T-1 --state blocked -p 4` — update fields
- `update T-1 -l bug,ux` — add labels
- `update T-1 -x ux` — remove labels
- `update T-1 -L task,docs` — replace all labels
- `dep T-2 T-1` — make T-2 depend on T-1 (T-1 must complete first)
- `dep T-2 T-1 T-3 T-4` — add multiple blockers T-1, T-3, T-4 for T-2
- `dep T-2 T-1 --remove` / `dep T-2 T-1 -r` — remove a dependency
- `note T-1 "context"` / `n T-1 "context"` — append a durable note
- `close T-1` — mark done; `--actor NAME` to attribute
- `reject T-1` — mark as won't-do; `--actor NAME` to attribute

**Inspecting tickets**
- `show T-1` / `s T-1` — ticket fields + 3 recent notes
- `show T-1 -n` — all notes
- `show T-1 -a` — everything: all notes + full event history
- `show T-1 -l 5` — cap entries shown
- `show T-1 -f json` — JSON output for scripting
- `resume` / `r` — context for the most relevant current ticket
- `resume T-1` — context for a specific ticket
- `log T-1` — git history for one ticket file (oldest-first)
- `log` — all recent tracker changes (oldest-first)
- `log --no-reverse` — newest-first, like standard git log

**Output format** — listing commands accept `-f compact|normal|verbose|json`;
other commands accept `-f text|json` where applicable

**Remote sync**
- `remote` — inspect tracker remote wiring
- `remote --set origin` — configure tracker remote
- `pull` / `pull origin` — fetch and merge tracker branch (uses configured remote by default)
- `push` / `push origin` — push tracker branch (uses configured remote by default)

## Recommended workflow

At the start of multi-step work:

```bash
gittoc summary
gittoc resume
```

Beginning a task:

```bash
gittoc claim T-1
```

When new follow-up work appears:

```bash
gittoc new "Add feature" -p 3
gittoc new "Blocked task" -d T-1 -d T-2  # create with dependencies
gittoc dep T-3 T-1   # T-3 depends on T-1 (T-1 must complete first)
```

Finishing:

```bash
gittoc close T-1
```

## Ticket relationships

Dependencies (`dep`) are the only structured relation. They gate readiness and
block claiming — use them for real ordering constraints.

All other cross-references use notes by convention:

```bash
# marking a duplicate
gittoc note T-7 "duplicate of T-3"
gittoc note T-3 "T-7 closed as duplicate"
gittoc close T-7

# related tickets (non-blocking)
gittoc note T-5 "see also T-3"

# grouping / epics
gittoc update T-5 -l auth-rewrite
gittoc list -l auth-rewrite
```

This keeps the schema minimal. Notes are searchable via `gittoc grep`.

## Notes

- Mutating commands use optimistic concurrency; they refuse to commit if the
  tracker changed mid-command. Review the new state and re-run the command if still applicable.
- `resume` without an ID prefers claimed tickets owned by the current user,
  then highest-priority ready issue, then highest-priority open issue.
- `pull` fetches and attempts a normal merge; conflicts are left for manual
  resolution in `.git/gittoc/`.
- `init` auto-configures `gittoc.remote` from the repo's inferred main remote.
- In sandboxed environments, writes under `.git/gittoc/` may require explicit
  approval. If mutations fail with a permission error, the sandbox may be
  blocking `.git` writes rather than the tool itself.
- For embedding guidance, see [references/embedding.md](references/embedding.md).
