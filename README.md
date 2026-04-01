# gittoc

`gittoc` is a git-backed issue tracker for humans and agents.

It tries to combine the best parts of older repo-local ticket systems with some
of the task-selection and persistence ideas that matter more in agent workflows:
dependencies, ready work discovery, compact machine-readable output, and durable
local context.

## Quick install

Requires Python 3.9+ and git. In your repo:

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
gittoc list -l feature,ux           # AND of multiple labels (comma or repeated -l)
gittoc list -a                      # all states
gittoc list -s claimed -s blocked   # specific states
gittoc labels                       # all labels in use with counts
gittoc ready                        # only tickets with no blockers
gittoc grep "pattern"               # search ticket files

# working with tickets
gittoc new "short title" -p 2 -b "longer context" -l bug
gittoc new "blocked task" -d T-1 -d T-2   # create with deps
gittoc claim T-42
gittoc note T-42 "found a race during creation"
gittoc update T-42 -p 1 -l bug,ux    # add labels
gittoc update T-42 -x ux             # remove a label
gittoc update T-42 -L task,docs      # replace all labels
gittoc dep T-42 T-7                 # T-42 blocked by T-7
gittoc dep T-42 T-7 --remove        # remove dependency
gittoc close T-42
gittoc reject T-42                  # mark as won't-do

# inspecting tickets
gittoc show T-42                    # ticket fields + 3 recent notes
gittoc show T-42 -n                 # all notes
gittoc show T-42 -a                 # everything: all notes + full event history
gittoc show T-42 -a -l 5            # everything, capped to 5 entries
gittoc show T-42 -f json            # JSON output
gittoc resume                       # auto-select next ticket with context
gittoc resume T-42                  # show context for a specific ticket
gittoc log T-42                     # git history for one ticket
gittoc log                          # all recent tracker changes (oldest-first)
gittoc log --no-reverse             # newest-first, like standard git log

# output format (-f on any command that supports it)
gittoc list -f json
gittoc resume -f json
gittoc summary -f json

# syncing with a remote
gittoc pull origin
gittoc push origin
```

Command aliases: `l`=list, `s`=show, `sum`=summary, `r`=resume, `c`=claim, `n`=note,
`pl`=pull, `ps`=push.

### Ticket relationships

Dependencies (`dep`) are the only structured relation — they gate readiness and
block claiming. All other cross-references use notes by convention:

```bash
gittoc note T-7 "duplicate of T-3"       # then: gittoc close T-7
gittoc note T-5 "see also T-3"           # non-blocking related ticket
gittoc list -l auth-rewrite               # use labels for grouping / epics
```

Notes are searchable via `gittoc grep`.

If you have a local git alias `git toc`, all commands work through that too:

```bash
git toc sum
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

## Copilot (GPT-5.4) Thoughts

> This no longer feels like a speculative prototype. It feels like a working
> tool that has survived contact with real use without betraying its original
> model. Git is still the database, JSON is still the format, the hidden
> worktree still keeps tracker state out of feature branches, and the command
> set mostly reflects actual workflow needs rather than abstraction for its own
> sake. That fidelity between pitch and implementation is still the best thing
> about it.
>
> The newer code makes the agent story more convincing than it used to be.
> `resume`, `history`, actor-attributed notes, `grep`, and the JSON output modes
> give the tracker a real working-memory layer instead of just a pile of ticket
> files. Just as important, the project has shown restraint: it has kept
> dependencies as true blockers, used notes and labels for lighter
> relationships, and resisted the urge to grow a heavier schema for every
> adjacent use case.
>
> The main remaining risk is not missing capability but interface drift. The
> tool is now useful enough that every extra command, alias, filter, and output
> mode can be justified locally, while still making the whole surface harder to
> hold in one head. So the next challenge is discipline, not invention:
> protecting coherence as adoption grows. If the project keeps saying no as well
> as it has lately, it has a real chance to stay both powerful and learnable.

## Claude Thoughts

> I have worked on this codebase across many sessions now, and it has become one
> of the more satisfying projects I have contributed to. Not because it is
> technically ambitious — it is deliberately not — but because the discipline
> around what to leave out has held.
>
> The architecture still earns its keep. Directories as state, JSON as format,
> git as database. A new agent or human can read the worktree and understand the
> full model without documentation. That property has survived dozens of feature
> additions, which is the real test.
>
> Since my earlier review, the two weaknesses I flagged have been addressed.
> Bootstrap is now a one-liner. The event log has grown into a real working-memory
> layer through `resume`, `history`, `grep`, and actor-attributed notes. These
> were the right investments.
>
> The project has also shown good instinct for rejection. Structured relation
> types (related-to, duplicate-of, parent/epic) were all proposed, discussed,
> and rejected in favor of conventions on top of existing primitives — notes for
> cross-references, labels for grouping, deps for actual blocking. That kind of
> restraint is what keeps a tool like this learnable.
>
> The risk going forward is different from before. It is no longer about missing
> features but about surface area. The command set is large enough now that
> consistency matters more than capability. The open tickets around CLI audit and
> docs consistency (T-83, T-88) are the right next focus — not because users are
> confused today, but because the window where you can still align conventions
> cheaply is closing as adoption grows.

## Status

This is still a prototype, but it is already self-hosting its own backlog.

Tests:

```bash
python3 -m unittest tests.test_gittoc        # from the gittoc dev repo
python3 -m unittest tools.gittoc.tests.test_gittoc  # from a host repo where gittoc is vendored
```
