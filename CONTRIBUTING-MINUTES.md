# Contributing to Minutes RingRTC

This repository follows Signal RingRTC upstream. Minutes-specific pull requests
must remain easy to replay and review after an upstream release.

1. Read `docs/FORK-MAINTENANCE.md`.
2. Put new behavior in a Minutes-owned file whenever possible.
3. Keep edits to upstream files to narrow hooks and build integration.
4. Update `config/minutes_fork_patch_manifest.json` for every new upstream touch,
   then regenerate `docs/MINUTES-PATCHES.md`.
5. Add fork release notes under `[Unreleased]` in `MINUTES-CHANGELOG.md`.
6. Run the checks documented in `README-MINUTES.md`.

Do not mix broad formatting, renames, or unrelated upstream refactors with a
Minutes feature. Such changes make the next automated sync needlessly risky.
