# Agent Instructions

## Your role

You are part of the software developer team of the `gittoc` project.

## The Project

This repository is developed collaboratively by humans and coding agents.

The project itself is a testbed and development repository for `gittoc`,
so agents are expected to use `gittoc` during normal work rather than
keeping planning in chat.

## Core Rules

- Prefer small, traceable changes over large mixed batches.
- For non-trivial work, create or update a `gittoc` ticket first.
- Keep a roughly one-ticket-to-one-change relationship.
- Reference the ticket id in the git commit message when the change belongs to a
  specific ticket.
- Do not silently fix unrelated issues while working on another ticket.
  Instead create a new ticket for them so they can be scheduled.
- Do not rewrite git history unless explicitly asked,
  and then only if the to-be-rewritten history is only local.

## Ticket Workflow

- Use `skills/gittoc/gittoc` or the local alias `git toc` if available.
  You may add an alias to the `.git/config` file if it's missing.
- At the start of work, inspect ticket backlog.
  Refer to `skills/gittoc/SKILL.md` on how to actually use gittoc.
- Claim a ticket before doing substantive work when the ticket is actionable.
- Add durable notes to tickets when you discover local context that would help a
  later agent or human resume the work.
- Close tickets when the corresponding work is actually complete.
- When you know that multiple agents / humans are actually working at the same time,
  and you have ability to push to a remote, always take care to push ticket changes
  (branch `gittoc`) and source changes (any branch you are currently working on).
  Use feature-branches for larger change-sets where multiple commits are to be expected.

## Review Findings And Follow-up

- If bugs, review findings, or external audit findings are reported, create a
  ticket for each distinct issue before fixing it.
- Prefer one ticket per bug.
- If several findings are tightly coupled and must be fixed together, note that
  explicitly in the ticket history before committing, and take care to link the
  corresponding tickets via `gittoc` dependencies where that relationship fits.

## Commit Discipline

- Keep commits focused.
- Commit code and documentation updates together when they are part of the same
  ticket.
- Run relevant verification before committing.
- Avoid "drive-by" refactors unless they are required for the ticket at hand.
  If you feel that a refactor step would be useful, add it in a separate
  refactor commit where possible.

Recommended commit style:

- `T-42 Prevent claiming closed tickets`
- `T-43 Reject dependency cycles`
- `T-44 Make sync tests branch-name agnostic`

## Style

- Use `black` and `isort` (available as binaries, no need to use `python` to call them)
- Regularly check output of `pyflakes3` and `pylint` and check for sensible suggestions.
  `pyflakes` usually gives better feedback than `pylint`, so take `pylint` only as
  basic suggestions.

## Testing

- For Python/code changes, run:
  - `python3 -m unittest skills.gittoc.tests.test_gittoc`
  - `python3 -m py_compile skills/gittoc/gittoc skills/gittoc/gittoc_lib/*.py skills/gittoc/tests/test_gittoc.py`
- If you cannot run a relevant test, say so explicitly.
- When you add a bug fix, prefer adding a regression test in the same change.

## Scope Discipline

- Keep the command surface small.
- Prefer adding aliases over adding new overlapping commands.
- Prefer explicit workflow improvements over speculative features.
- If you think a new feature is useful but not clearly necessary, create a
  lower-priority ticket instead of implementing it immediately.

## Documentation

- Update `README.md` when user-visible behavior changes.
- Update `skills/gittoc/SKILL.md` when the agent-facing workflow changes.
- Update this `AGENTS.md` when the development process for the `gittoc` tool itself is to be changed.
- Keep docs concise and operational; avoid turning them into long design essays.
