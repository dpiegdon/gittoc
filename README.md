# gitbeads

`gitbeads` is a git-backed issue tracker for humans and agents.

It tries to combine the best parts of older repo-local ticket systems with some
of the task-selection and persistence ideas that matter more in agent workflows:
dependencies, ready work discovery, compact machine-readable output, and durable
local context.

## What it is

- tickets live in git, not in an external SaaS
- canonical tracker state lives on a dedicated `gitbeads` branch
- a hidden worktree at `.git/gitbeads/` keeps issue files out of normal feature branches
- one compact JSON file stores the durable state of each ticket
- optional `*.events.jsonl` files store notes and ticket history
- the CLI is plain Python plus git, with no extra runtime dependencies

Current ticket states are directory-based:

- `issues/open`
- `issues/claimed`
- `issues/blocked`
- `issues/closed`

## Previous Work

`gitbeads` is not pretending to be invented from nothing. It is downstream of a
few older and newer ideas:

- [`ticgit`](https://github.com/jeffWelling/ticgit): repo-local issue tracking for humans, kept in git instead of a hosted tracker
- [`nitwit`](https://github.com/lukedupin/nitwit): CLI-first, offline, git-native ticket workflow with strong “tickets belong with the code” instincts
- [`beads`](https://github.com/steveyegge/beads): agent-oriented task graph ideas such as ready work, dependencies, claims, and durable multi-session context

The design goal here is roughly:

“Beads semantics, ticgit storage, minimal moving parts.”

## Why this exists

The main problem with many older repo-local trackers is that they either clutter
the working tree or rely on large text files that become awkward for agents.
The main problem with more ambitious agent trackers is that they often add too
much infrastructure: new binaries, databases, daemons, or state that drifts away
from the repo people are already working in.

`gitbeads` tries to sit in the middle:

- git is still the source of truth
- the active code branch stays clean
- humans can inspect files directly if they want
- agents can query small structured results instead of parsing huge markdown blobs

## Current commands

Examples:

```bash
skills/gitbeads/gitbeads summary
skills/gitbeads/gitbeads list
skills/gitbeads/gitbeads ready
skills/gitbeads/gitbeads ready-one --format json
skills/gitbeads/gitbeads resume
skills/gitbeads/gitbeads show GB-27 --field id --field title --field priority
skills/gitbeads/gitbeads note GB-27 "found a race during ticket creation"
skills/gitbeads/gitbeads history GB-27 --notes-only --limit 3
skills/gitbeads/gitbeads remote --format json
```

If you have a local git alias such as `git gb`, the same workflow can also look
like:

```bash
git gb list
git gb resume
git gb ready-one --format json
```

## Project layout

- [`skills/gitbeads/gitbeads`](/home/codex/squealds/skills/gitbeads/gitbeads): CLI entrypoint
- [`skills/gitbeads/gitbeads_lib`](/home/codex/squealds/skills/gitbeads/gitbeads_lib): internal modules
- [`skills/gitbeads/SKILL.md`](/home/codex/squealds/skills/gitbeads/SKILL.md): skill instructions
- [`skills/gitbeads/references/embedding.md`](/home/codex/squealds/skills/gitbeads/references/embedding.md): embedding and installation notes
- [`skills/gitbeads/tests/test_gitbeads.py`](/home/codex/squealds/skills/gitbeads/tests/test_gitbeads.py): end-to-end test

## Codex Thoughts

> This project has a real idea in it.
>
> The good part is that it is trying to solve an actual coordination problem for
> both humans and agents without immediately collapsing into infrastructure
> theater. Keeping tickets in git, keeping the active branch clean, and keeping
> the tool hackable with normal files and normal git commands all feel right.
>
> The risk is that tools like this can become command-heavy and slightly too
> clever. Every new convenience command is defensible in isolation, but the total
> surface area can quietly grow until the tool becomes harder to learn than the
> problem it was meant to solve. So I think the project is promising, but only if
> it stays strict about scope and keeps earning each added feature.

## Status

This is still a prototype, but it is already self-hosting its own backlog.

Tests:

```bash
python3 -m unittest skills.gitbeads.tests.test_gitbeads
```
