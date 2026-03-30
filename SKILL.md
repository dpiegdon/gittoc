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

## Commands

Invoke as `gittoc <command>` or `tools/gittoc/gittoc <command>` or
`git toc <command>` if the alias is configured. Use `--help` on any command
for full argument documentation.

**Backlog**
- `summary` / `s` — ticket counts by state
- `list` / `l` — open tickets by priority; `-a` for all states
- `list -s claimed -s blocked` — filter by state
- `list -l bug` / `list -l feature -l ux` — filter by label (AND)
- `list --ready-only` — only tickets with no unmet dependencies
- `ready` — shorthand for `list --ready-only`
- `labels` / `labels -a` — all labels in use with counts
- `grep PATTERN [-i] [-n]` — search open ticket files; `-a` for all states, `-s closed` for specific
- `list --sort=id` — chronological order instead of priority

**Working with tickets**
- `new "Title" -p 2 -b "context" -l feature` — create a ticket
- `claim T-1` / `c T-1` — claim a ticket (defaults owner to `$GITTOC_OWNER` / `$USER`)
- `update T-1 --state blocked -p 4` — update fields
- `update T-1 -l bug,ux` — add labels
- `update T-1 -x ux` — remove labels
- `update T-1 -L task,docs` — replace all labels
- `dep T-2 T-1` — make T-2 depend on T-1 (T-1 must complete first)
- `dep T-2 T-1 T-3 T-4` — add multiple blockers T-1, T-3, T-4 for T-2
- `note T-1 "context"` / `n T-1 "context"` — append a durable note
- `close T-1` — mark done

**Inspecting tickets**
- `show T-1` / `sh T-1` — one ticket as JSON with recent notes
- `show T-1 --field id --field title` — minimal field subset
- `show T-1 --history` — include full event history
- `resume` / `r` — context for the most relevant current ticket
- `resume T-1` — context for a specific ticket
- `history T-1 --notes-only --limit 3` — recent notes only
- `log T-1` — git history for one ticket file
- `log` — all recent tracker changes

**Output format** — most commands accept `-f compact|normal|verbose|json`

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
gittoc dep T-3 T-1   # T-3 depends on T-1 (T-1 must complete first)
```

Finishing:

```bash
gittoc close T-1
```

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
