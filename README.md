# gitbeads prototype

`gitbeads` is a minimal conceptual merge of `beads` and `ticgit`:

- `beads` semantics: dependency-aware, multi-session, human-and-agent tasks
- `ticgit` constraints: everything lives in git and can survive with simple tools

The prototype stores one compact JSON document per task on a dedicated `gitbeads`
branch and exposes an executable CLI at `skills/gitbeads/gitbeads`. The CLI keeps
a hidden git worktree under `.git/gitbeads/` so it can use normal file IO and
regular git porcelain commands while staying out of feature branches.

Current storage model:

- canonical issue state is the directory: `issues/open`, `issues/claimed`, `issues/blocked`, `issues/closed`
- issue files store durable fields such as `title`, `body`, `deps`, `labels`, `owner`, and `priority`
- issue ids are increasing `GB-1`, `GB-2`, `GB-3`, while older padded ids remain valid
- optional per-issue event history lives in sibling `*.events.jsonl` files
- `list` now defaults to open issues; use `--all` or explicit `--state` filters for broader views
- default ordering is by priority, then state, then issue id
- the tracker branch is the source of truth; the main working tree stays clean

Current useful commands:

- `skills/gitbeads/gitbeads summary`
- `skills/gitbeads/gitbeads refresh`
- `skills/gitbeads/gitbeads ready --format compact`
- `skills/gitbeads/gitbeads ready-one --format json`
- `skills/gitbeads/gitbeads resume`
- `skills/gitbeads/gitbeads resume GB-25 --format json`
- `skills/gitbeads/gitbeads list --all --format compact`
- `skills/gitbeads/gitbeads next --claim --owner codex`
- `skills/gitbeads/gitbeads list --format verbose`
- `skills/gitbeads/gitbeads show GB-27 --field id --field title --field priority`
- `skills/gitbeads/gitbeads claim GB-11 --owner alice`
- `skills/gitbeads/gitbeads note GB-11 "extra local context"`
- `skills/gitbeads/gitbeads history GB-11 --notes-only --limit 3`
- `skills/gitbeads/gitbeads export GB-11`
- `skills/gitbeads/gitbeads import GB-11`
- `skills/gitbeads/gitbeads show GB-1`

This means:

- feature branches do not carry tracker file churn
- one backlog can be shared across branches
- issue history still lives in git
- humans can inspect the hidden worktree if they really need to, but normally should not
- agents can ask for one ready issue or a minimal field subset without parsing broad listings
- humans and agents can recover recent ticket context without dumping full history

Tests:

- `python3 -m unittest skills.gitbeads.tests.test_gitbeads`
