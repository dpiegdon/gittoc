# Gitbeads Design Improvements

The current design is solid enough for real use, but the next improvements should
focus on collaboration safety and operator ergonomics rather than adding much more
surface area.

Priority areas:

- Add optimistic locking or a lightweight conflict check so concurrent agents do
  not silently overwrite each other's tracker changes.
- Improve list and show views with optional compact and verbose modes so humans
  can choose between fast scanning and richer context.
- Add first-class notes or event history per issue if short-lived work context
  proves too sparse for multi-agent coordination.
- Consider a small export/import path between the hidden tracker worktree and the
  visible working tree for manual editing or review workflows.
- Add more automated tests around migration and rename-heavy history so tracker
  evolution stays safe as the storage layout changes.

