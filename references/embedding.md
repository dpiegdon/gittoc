# Gittoc Embedding Draft

This document describes the preferred way to embed `gittoc` into a normal
project repository. The current repository is the development repository for the
tool itself, which is unusual. The normal case is that `gittoc` is brought into
some other git repository and used there by humans and agents.

## Design goals

- zero external runtime dependencies beyond `python3` and `git`
- no background services
- no pollution of the active feature branch
- usable both through a skill and directly at the shell
- easy to inspect manually without requiring git plumbing knowledge

## Recommended embedding model

The best default embedding is:

- a small executable at a stable path inside the target repository
- a matching skill directory that documents the workflow
- canonical tracker state on a dedicated `gittoc` branch
- a hidden git worktree at `.git/gittoc/`

Concretely, the target repository would contain something like:

```text
<target-repo>/
  tools/
    gittoc/
      gittoc          ← CLI entrypoint
      gittoc_lib/     ← internal modules
      SKILL.md        ← skill instructions
  .claude/
    skills/
      gittoc.md       ← Claude Code skill (copy of tools/gittoc/SKILL.md)
```

And at runtime `gittoc` would maintain:

```text
<target-repo>/.git/gittoc/
  issues/
    open/
    claimed/
    blocked/
    closed/
```

This keeps the operational data inside git, keeps the active branch clean, and
keeps the executable visible and easy to call.

## Why not keep the executable only inside the hidden worktree

The hidden worktree is for state, not for distribution. The executable should
live in the visible repository because:

- callers need a stable path before the tracker is initialized
- the tool itself should be reviewable and versioned with the host repository
- a skill should reference a normal visible path
- upgrading or patching the tool should not require touching the hidden state store

## Recommended invocation paths

There are two good invocation patterns:

1. explicit tool path

```bash
tools/gittoc/gittoc list
tools/gittoc/gittoc claim T-1 --owner alice
```

2. via git alias (after adding to `.git/config`)

```bash
git toc list
git toc claim T-1 --owner alice
```

For a normal repository, `tools/gittoc/gittoc` is the canonical path. The
git alias is an optional ergonomic layer — agents should not assume it exists.

## Optional repo-local git alias

Add this to `.git/config` directly (do not use `git config` — it escapes
the `!` on some git versions, breaking the shell-escape prefix):

```ini
[alias]
    toc = !tools/gittoc/gittoc
```

That allows:

```bash
git toc list
git toc claim T-1 --owner alice
```

This is attractive because it makes `gittoc` feel like a natural git extension
without requiring any global shell setup.

Pros:

- much shorter and more memorable command surface for humans
- stored in the repository-local git config, so it can be installed automatically per checkout
- keeps the explicit visible tool path as the actual implementation target
- reinforces the mental model that `gittoc` is git-adjacent project infrastructure

Cons:

- checkout-specific rather than repository-content-specific, so a fresh clone does not get it unless install/init runs
- not visible in normal tracked files, so the repo cannot rely on it as the only documented entrypoint
- agents and automation should still assume the explicit tool path exists, not the alias
- alias shape depends on where the executable is embedded, so install logic must write the correct path into `.git/config`

Recommended stance:

- support this as an optional convenience installed during `gittoc init` or an explicit install step
- keep `tools/gittoc/gittoc` as the canonical documented path
- document `git toc` as a local ergonomic layer, not as the only supported interface

## Recommended skill relationship

The skill should be documentation and workflow guidance around the tool, not the
primary home of the executable.

Preferred pattern:

- executable at `tools/gittoc/gittoc`
- skill at `tools/gittoc/SKILL.md`, copied to `.claude/skills/gittoc.md`
- skill examples invoke `tools/gittoc/gittoc`

This separates:

- implementation and operations
- agent instructions
- tracker state

That separation is healthier than coupling all three to the skill directory.

## Installation options

There are three realistic ways to embed `gittoc` into another repository.

### Option 1: vendored file copy

Copy the executable and skill files into the target repository.

Pros:

- simplest mental model
- easiest to patch locally
- no extra git mechanism needed

Cons:

- manual upgrades unless automation is added later

This is probably the best initial embedding model.

Current recommendation:

- do this first
- do not add a more magical install/bootstrap system for the first public release

### Option 2: subtree or submodule

Track `gittoc` as an imported dependency.

Pros:

- clearer upgrade story
- reuse across many repositories

Cons:

- higher git workflow complexity
- worse ergonomics for casual users

This is reasonable only if many repositories need to share one upstream.

### Option 3: external skill installer

Install the skill and tool from outside the repository.

Pros:

- central management
- easier upgrades

Cons:

- weaker repo-local transparency
- more dependence on the surrounding environment

This is viable, but less aligned with the current design philosophy.

## First release decision

For the first public prototype release:

- recommend a visible vendored tool in the host repository
- keep mutable tracker state on the hidden `gittoc` branch/worktree
- document repo-local `git toc` alias setup as optional
- do not require or ship a dedicated install script yet

This keeps the release boring, inspectable, and easy to explain.

## Recommended long-term direction

The strongest default seems to be:

- vendor `gittoc` into `tools/gittoc/`
- copy `SKILL.md` to `.claude/skills/gittoc.md` for Claude Code users
- keep all mutable tracker state on the `gittoc` branch via `.git/gittoc/`

In short:

- visible tool
- visible skill
- hidden state

That gives the cleanest operator experience for both humans and agents.
