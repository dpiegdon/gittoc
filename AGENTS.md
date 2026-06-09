# Agent Instructions

This repository is the development repo for `gittoc`, a git-backed issue
tracker. Agents are expected to use `gittoc` for all planning and tracking
rather than keeping state in chat.

## Core Rules

- Prefer small, traceable changes over large mixed batches.
- Create or update a ticket before doing non-trivial work.
- One ticket per distinct issue; commit your changes per ticket where possible.
- Include the ticket ID in commit messages, e.g. `Add label filtering (T-39)`.
- Do not silently fix unrelated issues — open a new ticket instead.
- Do not rewrite git history unless explicitly asked, and only if the history
  is local.

## Ticket Workflow

- Use `gittoc` or `git toc` if the alias is available.
  See `SKILL.md` for command reference.
- Inspect the backlog at the start of work: `gittoc resume` or `gittoc list`.
- Claim a ticket before starting substantive work.
- Add notes to tickets when you discover context that would help a later
  session resume the work.
- Close tickets when the work is complete.
- When multiple agents or humans are working concurrently, push both the
  `gittoc` branch and the working branch after each commit.
- If you are tasked with solving multiple tickets, try to finish one ticket before taking another.
- Note/body text on the command line is evaluated by your shell (backticks,
  `$(...)`, `!`). Single-quote it, or pass it via `-F FILE` / `-F -` (with a
  quoted heredoc `<<'EOF'`) on `note`, `new`, and `update` to avoid mangling.

## Commit Discipline

- Keep commits focused; commit code and docs together when they belong to the
  same ticket.
- Run relevant tests before committing.
- Avoid drive-by refactors; open a ticket if a refactor would be useful.

## Style

- Format with `isort` first, then `black` before committing (black wins on
  import formatting conflicts).
- Check `python3 -m pyflakes` output before committing.
- Keep `mypy` clean; the dev pipeline type-checks `scripts/gittoc` and
  `scripts/gittoc_lib/` (tests are excluded).

## Testing

The fastest path is the local dev pipeline. It builds an isolated venv, installs
the pinned dev tools, and runs lint (isort, black, pyflakes), a type check
(mypy), the Python-floor check (vermin), `py_compile`, and the full test suite
in one go:

```bash
scripts/dev/check            # all checks; extra args pass through to the tests
scripts/dev/check -k pull    # e.g. only test ids containing "pull"
```

`scripts/dev/` is dev-only — the install `setup` script removes it (and its
venv) so vendored installs never carry it. To run pieces by hand instead:

```bash
python3 -m pytest scripts/tests/test_gittoc.py
python3 -m py_compile scripts/gittoc scripts/gittoc_lib/*.py scripts/tests/test_gittoc.py
```

On multi-core machines the suite runs roughly twice as fast through the
stdlib parallel runner (same tests, real CLI binary, no extra dependencies):

```bash
python3 scripts/tests/run_parallel.py          # one worker per core
python3 scripts/tests/run_parallel.py -j 4     # explicit worker count
python3 scripts/tests/run_parallel.py -k pull  # only ids containing "pull"
```

- Add regression tests when fixing bugs.
- If you cannot run a test, say so explicitly.

## Scope Discipline

- Keep the command surface small.
- Prefer aliases over new overlapping commands.
- Prefer explicit workflow improvements over speculative features.
- When unsure whether a feature is necessary, open a lower-priority ticket
  instead of implementing it.

### Non-goals

Resist turning `gittoc` into Jira. Notes-as-audit-trail is the core feature;
stay repo-local and zero-infra; states plus labels are enough, so avoid
workflow ceremony. Multi-writer use (concurrent agents and humans) is
load-bearing: treat optimistic locking, the `actor` field, and `ref` stamping
as first-class invariants when changing event handling.

## Documentation

- Update `README.md` when user-visible behavior changes.
- Update `SKILL.md` when the agent-facing workflow changes.
- Keep docs concise and operational.
