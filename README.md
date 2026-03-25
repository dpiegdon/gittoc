# gitbeads prototype

`gitbeads` is a minimal conceptual merge of `beads` and `ticgit`:

- `beads` semantics: dependency-aware, multi-session, agent-friendly tasks
- `ticgit` constraints: everything lives in git and can survive with simple tools

The prototype stores one compact JSON document per task in `.codex/issues/open/`
and exposes a small Python CLI at `scripts/gitbeads.py`. Agents should prefer the
CLI so the ticket store does not spill into prompt context.

Current useful commands:

- `python3 scripts/gitbeads.py summary`
- `python3 scripts/gitbeads.py ready`
- `python3 scripts/gitbeads.py next --claim --owner codex`
- `python3 scripts/gitbeads.py show GB-0001`
