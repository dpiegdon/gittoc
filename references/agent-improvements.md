# Agent-Centric Improvement Draft

This document originally listed five priority ideas for agent-focused
improvements. All five have been implemented or superseded by concrete tickets:

- **concurrency protection** — optimistic locking landed in T-15, conflict
  recovery in T-24 (both closed)
- **per-ticket notes** — note/history commands landed in T-17 (closed)
- **machine-oriented output** — `--field`, JSON formats, `resume` landed in
  T-27 (closed)
- **separation of concerns** — SOLID refactor landed in T-10 (closed)
- **embedding layout** — documented in `references/embedding.md`

Remaining agent-facing work is tracked in the open backlog (e.g. T-79 timeline
querying, T-82 validation on load). This file is kept for historical context
only.

