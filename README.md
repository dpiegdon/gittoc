# gitbeads prototype

`gitbeads` is a minimal conceptual merge of `beads` and `ticgit`:

- `beads` semantics: dependency-aware, multi-session, human-and-agent tasks
- `ticgit` constraints: everything lives in git and can survive with simple tools

The prototype stores one compact JSON document per task in `.gitbeads/issues/open/`
and exposes an executable CLI at `skills/gitbeads/gitbeads`. Humans and agents
should prefer the CLI so the ticket store does not spill into prompt context.

Current useful commands:

- `skills/gitbeads/gitbeads summary`
- `skills/gitbeads/gitbeads ready`
- `skills/gitbeads/gitbeads next --claim --owner codex`
- `skills/gitbeads/gitbeads show GB-0001`
