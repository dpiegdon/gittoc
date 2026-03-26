# gittoc

`gittoc` is a git-backed issue tracker for humans and agents.

It tries to combine the best parts of older repo-local ticket systems with some
of the task-selection and persistence ideas that matter more in agent workflows:
dependencies, ready work discovery, compact machine-readable output, and durable
local context.

## What it is

- tickets live in git, not in an external SaaS
- canonical tracker state lives on a dedicated `gittoc` branch
- a hidden worktree at `.git/gittoc/` keeps issue files out of normal feature branches
- one compact JSON file stores the durable state of each ticket
- optional `*.events.jsonl` files store notes and ticket history
- the CLI is plain Python plus git, with no extra runtime dependencies

Current ticket states are directory-based:

- `issues/open`
- `issues/claimed`
- `issues/blocked`
- `issues/closed`

## Previous Work

`gittoc` is not pretending to be invented from nothing. It is downstream of a
few older and newer ideas:

- [`ticgit`](https://github.com/jeffWelling/ticgit): repo-local issue tracking for humans, kept in git instead of a hosted tracker
- [`nitwit`](https://github.com/lukedupin/nitwit): CLI-first, offline, git-native ticket workflow with strong “tickets belong with the code” instincts
- [`beads`](https://github.com/steveyegge/beads): agent-oriented task graph ideas such as ready work, dependencies, claims, and durable multi-session context
- [`pearls`](https://github.com/mrorigo/pearls): a lightweight Git-native distributed issue tracker for agentic workflows, with a nearby problem statement from a different implementation direction

The design goal here is roughly:

“Beads semantics, ticgit storage, minimal moving parts.”

## Why this exists

The main problem with many older repo-local trackers is that they either clutter
the working tree or rely on large text files that become awkward for agents.
The main problem with more ambitious agent trackers is that they often add too
much infrastructure: new binaries, databases, daemons, or state that drifts away
from the repo people are already working in.

`gittoc` tries to sit in the middle:

- git is still the source of truth
- the active code branch stays clean
- humans can inspect files directly if they want
- agents can query small structured results instead of parsing huge markdown blobs

## Current commands

Examples:

```bash
skills/gittoc/gittoc summary
skills/gittoc/gittoc list
skills/gittoc/gittoc ready
skills/gittoc/gittoc resume
skills/gittoc/gittoc resume --format json
skills/gittoc/gittoc show T-27
skills/gittoc/gittoc show T-27 --field id --field title --field priority
skills/gittoc/gittoc note T-27 "found a race during ticket creation"
skills/gittoc/gittoc history T-27 --notes-only --limit 3
skills/gittoc/gittoc remote --format json
```

If you have a local git alias such as `git toc`, the same workflow can also look
like:

```bash
git toc list
git toc resume
git toc resume --format json
```

## Project layout

- [`skills/gittoc/gittoc`](/home/codex/squealds/skills/gittoc/gittoc): CLI entrypoint
- [`skills/gittoc/gittoc_lib`](/home/codex/squealds/skills/gittoc/gittoc_lib): internal modules
- [`skills/gittoc/SKILL.md`](/home/codex/squealds/skills/gittoc/SKILL.md): skill instructions
- [`skills/gittoc/references/embedding.md`](/home/codex/squealds/skills/gittoc/references/embedding.md): embedding and installation notes
- [`skills/gittoc/tests/test_gittoc.py`](/home/codex/squealds/skills/gittoc/tests/test_gittoc.py): end-to-end test

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
python3 -m unittest skills.gittoc.tests.test_gittoc
```
