# gitbeads prototype

`gitbeads` is a minimal conceptual merge of `beads` and `ticgit`:

- `beads` semantics: dependency-aware, multi-session, human-and-agent tasks
- `ticgit` constraints: everything lives in git and can survive with simple tools

The prototype stores one compact JSON document per task on a dedicated `gitbeads`
branch and exposes an executable CLI at `skills/gitbeads/gitbeads`. The CLI keeps
a hidden git worktree under `.git/gitbeads/` so it can use normal file IO and
regular git porcelain commands while staying out of feature branches.

Current useful commands:

- `skills/gitbeads/gitbeads summary`
- `skills/gitbeads/gitbeads ready`
- `skills/gitbeads/gitbeads next --claim --owner codex`
- `skills/gitbeads/gitbeads show GB-0001`

This means:

- feature branches do not carry tracker file churn
- one backlog can be shared across branches
- issue history still lives in git
- humans can inspect the hidden worktree if they really need to, but normally should not
