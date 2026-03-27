# Agent Instructions

This repository is the development repo for `gittoc`, a git-backed issue
tracker. Agents are expected to use `gittoc` for all planning and tracking
rather than keeping state in chat.

## Core Rules

- Prefer small, traceable changes over large mixed batches.
- Create or update a ticket before doing non-trivial work.
- One ticket per distinct issue; one commit per ticket where possible.
- Include the ticket ID in commit messages, e.g. `Add label filtering (T-39)`.
- Do not silently fix unrelated issues — open a new ticket instead.
- Do not rewrite git history unless explicitly asked, and only if the history
  is local.

## Ticket Workflow

- Use `skills/gittoc/gittoc` or `git toc` if the alias is available.
  See `skills/gittoc/SKILL.md` for command reference.
- Inspect the backlog at the start of work: `gittoc resume` or `gittoc list`.
- Claim a ticket before starting substantive work.
- Add notes to tickets when you discover context that would help a later
  session resume the work.
- Close tickets when the work is complete.
- When multiple agents or humans are working concurrently, push both the
  `gittoc` branch and the working branch after each commit.

## Commit Discipline

- Keep commits focused; commit code and docs together when they belong to the
  same ticket.
- Run relevant tests before committing.
- Avoid drive-by refactors; open a ticket if a refactor would be useful.

## Style

- Format with `black` and `isort` before committing.
- Check `pyflakes3` and `pylint` output; `pyflakes3` is usually more signal.

## Testing

```bash
python3 -m unittest skills.gittoc.tests.test_gittoc
python3 -m py_compile skills/gittoc/gittoc skills/gittoc/gittoc_lib/*.py skills/gittoc/tests/test_gittoc.py
```

- Add regression tests when fixing bugs.
- If you cannot run a test, say so explicitly.

## Scope Discipline

- Keep the command surface small.
- Prefer aliases over new overlapping commands.
- Prefer explicit workflow improvements over speculative features.
- When unsure whether a feature is necessary, open a lower-priority ticket
  instead of implementing it.

## Documentation

- Update `README.md` when user-visible behavior changes.
- Update `skills/gittoc/SKILL.md` when the agent-facing workflow changes.
- Keep docs concise and operational.
