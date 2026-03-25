# Gitbeads Embedding Draft

This document describes the preferred way to embed `gitbeads` into a normal
project repository. The current repository is the development repository for the
tool itself, which is unusual. The normal case is that `gitbeads` is brought into
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
- canonical tracker state on a dedicated `gitbeads` branch
- a hidden git worktree at `.git/gitbeads/`

Concretely, the target repository would contain something like:

```text
<target-repo>/
  tools/
    gitbeads
  skills/
    gitbeads/
      SKILL.md
      references/
```

And at runtime `gitbeads` would maintain:

```text
<target-repo>/.git/gitbeads/
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

1. tool-first embedding

```bash
tools/gitbeads list
tools/gitbeads next --claim
```

2. skill-adjacent embedding

```bash
skills/gitbeads/gitbeads list
skills/gitbeads/gitbeads next --claim
```

For a normal repository, `tools/gitbeads` is the better default because it makes
the CLI feel like project infrastructure rather than skill internals. The skill
can then reference `tools/gitbeads`.

## Recommended skill relationship

The skill should be documentation and workflow guidance around the tool, not the
primary home of the executable.

Preferred pattern:

- executable at `tools/gitbeads`
- skill at `skills/gitbeads/SKILL.md`
- skill examples invoke `tools/gitbeads`

This separates:

- implementation and operations
- agent instructions
- tracker state

That separation is healthier than coupling all three to the skill directory.

## Installation options

There are three realistic ways to embed `gitbeads` into another repository.

### Option 1: vendored file copy

Copy the executable and skill files into the target repository.

Pros:

- simplest mental model
- easiest to patch locally
- no extra git mechanism needed

Cons:

- manual upgrades unless automation is added later

This is probably the best initial embedding model.

### Option 2: subtree or submodule

Track `gitbeads` as an imported dependency.

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

## Recommended long-term direction

The strongest default seems to be:

- vendor `gitbeads` into `tools/gitbeads`
- ship `skills/gitbeads/` next to it
- keep all mutable tracker state on the `gitbeads` branch via `.git/gitbeads/`

In short:

- visible tool
- visible skill
- hidden state

That gives the cleanest operator experience for both humans and agents.

