# Gittoc Brainstorm

## What feels good

- The core shape is strong: repo-local, branch-backed, no daemon, no database.
- The hidden worktree model is a good compromise between cleanliness and inspectability.
- The tracker is now expressive enough to support real ongoing work instead of just toy tickets.
- Priority, state directories, notes/history, and explicit git history fit together naturally.
- The project still feels small enough that one person can understand the whole system.

## What feels annoying or weak

_Updated 2026-03-31. Items marked (resolved) are kept for context._

- (resolved) ~~The single-file CLI is still carrying too many responsibilities~~ — split into cli.py, tracker.py, models.py, render.py, common.py (T-10).
- Migration behavior is easy to get subtly wrong because storage evolution and runtime behavior live in the same path.
- There is still a lot of incidental file choreography around issue moves, event files, exports, and worktree state.
- (resolved) ~~The tracker can be correct while still feeling operationally fragile under concurrent edits~~ — optimistic locking (T-15) and conflict recovery (T-24).
- Manual validation is not hard, but it still feels more tedious than it should. See T-78 (tracker integrity check) and T-82 (validate on load).
- (resolved) ~~The embedding story is better on paper than in actual repository layout~~ — documented in embedding.md, setup script added (T-66).
- The project still mixes "tool under development" and "tool being used" in the same repo, which creates odd edge cases.
