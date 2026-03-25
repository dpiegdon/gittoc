# Gitbeads Brainstorm

## What feels good

- The core shape is strong: repo-local, branch-backed, no daemon, no database.
- The hidden worktree model is a good compromise between cleanliness and inspectability.
- The tracker is now expressive enough to support real ongoing work instead of just toy tickets.
- Priority, state directories, notes/history, and explicit git history fit together naturally.
- The project still feels small enough that one person can understand the whole system.

## What feels annoying or weak

- The single-file CLI is still carrying too many responsibilities despite recent cleanup.
- Migration behavior is easy to get subtly wrong because storage evolution and runtime behavior live in the same path.
- There is still a lot of incidental file choreography around issue moves, event files, exports, and worktree state.
- The tracker can be correct while still feeling operationally fragile under concurrent edits.
- Manual validation is not hard, but it still feels more tedious than it should.
- The embedding story is better on paper than in actual repository layout right now.
- The project still mixes “tool under development” and “tool being used” in the same repo, which creates odd edge cases.

