# gittoc

`gittoc` is a git-backed issue tracker for humans and agents.

It tries to combine the best parts of older repo-local ticket systems with some
of the task-selection and persistence ideas that matter more in agent workflows:
dependencies, ready work discovery, compact machine-readable output, and durable
local context.

## Quick install

Requires Python 3.8+ and git. In your repo:

```bash
mkdir -p tools && git clone --depth=1 https://codeberg.org/dpiegdon/gittoc tools/gittoc && rm -rf tools/gittoc/.git && ./tools/gittoc/gittoc init && ./tools/gittoc/setup && ./tools/gittoc/gittoc summary
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
- the CLI is plain Python 3.8+ plus git, with no extra runtime dependencies

Current ticket states are directory-based:

- `issues/open`
- `issues/claimed`
- `issues/blocked`
- `issues/closed`
- `issues/rejected`

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
gittoc update T-42 -p 1 -l bug,ux    # add labels
gittoc update T-42 -x ux             # remove a label
gittoc update T-42 -L task,docs      # replace all labels
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
mkdir -p tools
git clone https://codeberg.org/dpiegdon/gittoc tools/gittoc
rm -rf tools/gittoc/.git
./tools/gittoc/gittoc init             # initialize tracker branch
./tools/gittoc/setup                   # create skill symlink and git alias
./tools/gittoc/gittoc summary          # should print all-zero counts
```

The tool code stays visible and reviewable on the normal branch. Only the
mutable issue store lives on the hidden `gittoc` branch/worktree.

### Local-only install (shared repos)

If you want to use gittoc on a project without committing the tool upstream,
exclude it from git tracking:

```bash
mkdir -p tools
git clone https://codeberg.org/dpiegdon/gittoc tools/gittoc
rm -rf tools/gittoc/.git
echo 'tools/gittoc/' >> .git/info/exclude
./tools/gittoc/gittoc init
./tools/gittoc/setup
```

The tool stays local to your checkout — invisible to git, never pushed. Each
collaborator who wants gittoc installs it themselves the same way.

## Project layout

- `gittoc`: CLI entrypoint
- `gittoc_lib/`: internal modules
- `SKILL.md`: skill instructions
- `references/embedding.md`: embedding and installation notes
- `tests/test_gittoc.py`: end-to-end test

## Codex Thoughts

> This project feels more real now than speculative.
>
> The strongest thing about it is that the implementation still matches the
> pitch. Git is still the database, the hidden worktree keeps tracker state out
> of feature branches, and the command set mostly lines up with concrete workflow
> needs instead of chasing abstractions. That honesty matters. A human or agent
> arriving cold can inspect the repo, run a few commands, and form a reliable
> mental model without needing a separate service or a long architecture tour.
>
> The project has also moved past the stage where the main question is "is this a
> good idea?" The question now is whether it can keep its shape while becoming
> more useful. The risk is not lack of features; it is gradual command bloat,
> overlapping affordances, and agent-friendly shortcuts that make the surface area
> feel heavier than the underlying model. If the project keeps protecting the
> simple storage model and remains disciplined about command growth, it has a real
> shot at being one of the rare coordination tools that is both powerful and
> understandable.

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
python3 -m unittest tests.test_gittoc        # from the gittoc dev repo
python3 -m unittest tools.gittoc.tests.test_gittoc  # from a host repo where gittoc is vendored
```
