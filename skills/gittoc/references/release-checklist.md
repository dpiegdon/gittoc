# gittoc Release Checklist

This is a pragmatic checklist for a first public `gittoc` release.

## Release framing

- Decide whether the public release name stays `gittoc`.
- Pick an initial version tag such as `v0.1.0` or `v0.1.0-alpha`.
- Position the release as an early, opinionated prototype rather than a finished tracker.

## Repo contents

- Confirm `README.md` is the shortest accurate introduction to the project.
- Confirm `skills/gittoc/SKILL.md` is operational and succinct.
- Confirm `LICENSE` is present and correct.
- Decide whether to add a short `AUTHORS` or `CREDITS` note.

## Attribution

- State that implementation was done by Codex.
- State that project direction, review, and maintenance are by David R. Piegdon `<dgit@piegdon.de>`.
- Make sure the public repo still has a clearly accountable human maintainer.

## Installation story

- Document the intended embedding model for another repository.
- Decide whether the recommended CLI path is `tools/gittoc`, `skills/gittoc/gittoc`, or optional `git toc`.
- Decide whether repo-local git alias setup is included in the initial release or only documented.

## Feature boundaries

- Be explicit that the tracker is git-backed, local-first, and daemon-free.
- Be explicit that automatic remote sync and conflict handling are not part of the initial release.
- Be explicit that the command/file schema may still evolve in `v0.x`.

## Verification

- Run `python3 -m unittest skills.gittoc.tests.test_gittoc`.
- Run a short manual smoke test in a fresh repo.
- Confirm the tracker can initialize cleanly in a repo that has no existing `gittoc` branch.

## Publication

- Create the public repository.
- Push the code and tags.
- Write short release notes explaining:
  - what problem `gittoc` solves
  - the design lineage from `ticgit`, `nitwit`, and `beads`
  - current limitations
