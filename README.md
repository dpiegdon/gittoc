# gittoc

`gittoc` is a git-backed issue tracker for humans and agents.

It tries to combine the best parts of older repo-local ticket systems with some
of the task-selection and persistence ideas that matter more in agent workflows:
dependencies, ready work discovery, compact machine-readable output, and durable
local context.

## Quick install

In a fresh git repo:

```bash
git clone --depth=1 https://codeberg.org/dpiegdon/gittoc && mv gittoc tools/gittoc && rm -rf tools/gittoc/.git && tools/gittoc/gittoc init && tools/gittoc/gittoc summary
```

If you use Claude Code, also install the skill:

```bash
mkdir -p .claude/skills && cp tools/gittoc/SKILL.md .claude/skills/gittoc.md
```

Optionally add a git alias (double quotes expand the path at write time,
avoiding `!` escaping issues in some git versions):

```bash
git config alias.toc "!$(git rev-parse --show-toplevel)/tools/gittoc/gittoc"
```

## Repository

- authoritative repository: https://codeberg.org/dpiegdon/gittoc
- GitHub mirror: https://github.com/dpiegdon/gittoc

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

Use `--help` on any command for full argument documentation.

```bash
# backlog overview
gittoc summary
gittoc list
gittoc list -l bug                  # filter by label
gittoc list -l feature -l ux        # AND of multiple labels
gittoc list -a                      # all states
gittoc labels                       # all labels in use with counts
gittoc ready                        # only tickets with no blockers

# working with tickets
gittoc new "short title" -p 2 -b "longer context"
gittoc claim T-42
gittoc note T-42 "found a race during creation"
gittoc update T-42 -p 1
gittoc dep T-42 T-7                 # T-42 blocked by T-7
gittoc close T-42

# inspecting tickets
gittoc show T-42
gittoc show T-42 --field id --field title --field priority
gittoc resume                       # auto-select next ticket with context
gittoc resume T-42                  # show context for a specific ticket
gittoc history T-42 --notes-only --limit 3
gittoc log T-42                     # git history for one ticket
gittoc log                          # all recent tracker changes

# output format (-f on any command that supports it)
gittoc list -f json
gittoc resume -f json

# syncing with a remote
gittoc pull origin
gittoc push origin
```

Command aliases: `l`=list, `s`=summary, `r`=resume, `c`=claim, `n`=note,
`sh`=show, `pl`=pull, `ps`=push.

If you have a local git alias `git toc`, all commands work through that too:

```bash
git toc s
git toc l -l bug
git toc r -f json
```

## Installation

The recommended model is to vendor gittoc directly into the host repository.

```bash
# clone gittoc into a staging area, copy into your target repo:
git clone https://codeberg.org/dpiegdon/gittoc /tmp/gittoc
cp -r /tmp/gittoc <your-repo>/tools/gittoc
rm -rf <your-repo>/tools/gittoc/.git

# initialize the tracker:
cd <your-repo>
tools/gittoc/gittoc init
tools/gittoc/gittoc summary   # should print all-zero counts

# Claude Code users: install the skill
mkdir -p .claude/skills
cp tools/gittoc/SKILL.md .claude/skills/gittoc.md

# optional git alias (note: ! form can be finicky in some environments)
git config alias.toc "!$(git rev-parse --show-toplevel)/tools/gittoc/gittoc"
```

The tool code stays visible and reviewable on the normal branch. Only the
mutable issue store lives on the hidden `gittoc` branch/worktree.

## Project layout

- `gittoc`: CLI entrypoint
- `gittoc_lib/`: internal modules
- `SKILL.md`: skill instructions
- `references/embedding.md`: embedding and installation notes
- `tests/test_gittoc.py`: end-to-end test

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

## Claude Thoughts

> I find this project genuinely interesting, which is not something I say about
> every codebase I work in.
>
> What works: the architecture is honest. Git is the database, directories are
> the state machine, plain JSON is the format. There are no moving parts that
> require explanation. An agent or human arriving cold can understand the full
> storage model in about two minutes by just looking at the worktree. That is
> rare and valuable.
>
> What I think makes or breaks it is the bootstrap experience. Right now,
> installing gittoc into a new project is still a manual, slightly awkward step.
> If that step is smooth, the tool earns adoption. If it is friction-heavy, teams
> skip it and use something else. The install story needs to be a single command
> that a new agent can execute without reading four files first.
>
> The thing I would watch carefully: the event log is underused. Notes and history
> are already there, but right now they feel like a second-class citizen compared
> to the ticket fields. That log is the memory layer — the place where working
> context survives across context resets. If the tool leaned into that more
> deliberately, it would be qualitatively more useful for agents than any hosted
> ticket system.

## Status

This is still a prototype, but it is already self-hosting its own backlog.

Tests:

```bash
python3 -m unittest skills.gittoc.tests.test_gittoc
```
