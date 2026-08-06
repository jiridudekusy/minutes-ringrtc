# Maintaining the Minutes RingRTC fork

## Layers

1. **Signal RingRTC baseline** — the stable tag recorded in
   `config/minutes_desktop_artifacts.json` and
   `config/minutes_fork_patch_manifest.json`.
2. **Thin upstream hooks** — the exact inherited files listed under
   `upstreamPatches` in the patch manifest.
3. **Minutes-owned implementation** — recording tap modules, tests, artifact
   tooling, WebRTC patches, documentation, and workflows kept beside upstream.

Do not move recording policy into RingRTC call code. RingRTC only exposes bounded
media taps; Minutes Desktop decides when and how to record.

## Automatic upstream sync

Every Monday, `.github/workflows/minutes_merge_upstream.yml` queries stable
`signalapp/ringrtc` tags. If a newer tag exists and no matching sync PR is open,
the workflow:

1. creates `sync/ringrtc-<run-id>` from `main`;
2. merges the stable upstream tag without adding a persistent remote;
3. changes the package baseline to `<upstream>-minutes.0` (an unreleased staging
   revision);
4. regenerates and validates the patch manifest;
5. runs focused maintenance and distribution tests;
6. opens a pull request with the native review checklist.

Conflicts limited to the fork package name/version in `src/node/package.json`
and its lockfile are resolved mechanically: the merged dependency graph is kept,
then Minutes metadata is regenerated. Every other conflict intentionally stops
the workflow. Resolve it on a new sync branch and preserve upstream behavior. A
native media-boundary redesign is not a routine conflict and must receive a
focused review.

For a local sync:

```sh
git checkout -b sync/ringrtc-2.70.2 main
python3 bin/minutes_upstream.py merge v2.70.2
python3 bin/minutes_version.py prepare-upstream v2.70.2
python3 bin/minutes_patch_manifest.py render
python3 bin/minutes_patch_manifest.py check --include-working-tree
```

## Patch manifest rules

- New Minutes files belong under a narrow `forkOwnedPaths` pattern.
- Editing or deleting an inherited file requires an exact `upstreamPatches`
  entry and a concise reason.
- Never hide a broad wildcard over upstream source directories.
- If upstream absorbs a hook, remove the stale entry and prefer its API.
- `docs/MINUTES-PATCHES.md` is generated; edit the JSON manifest instead.

## Fork releases

Write user- or integrator-visible changes under `[Unreleased]` in
`MINUTES-CHANGELOG.md`, then run **Actions → Release Minutes RingRTC**. The
workflow increments only the `minutes.N` revision, promotes the changelog,
commits the metadata, creates `v<package-version>`, and pushes it. The native
artifact workflow builds checksum-pinned addons and publishes the GitHub release.

After an upstream sync, the staging version ends in `minutes.0`; the first
release becomes `minutes.1`. Further releases on the same upstream baseline
increment the revision.

## Native review checklist

- local input is tapped after mute gating and WebRTC audio processing;
- remote audio is tapped before operating-system playout;
- outgoing video contains only RingRTC screen-share frames, never camera frames;
- tap buffers remain bounded and do not block the real-time media thread;
- inactive, overflow, and sample-gap transitions remain explicit;
- tap API version and Node/Rust contracts agree;
- all release targets build and the package downloads only checksum-pinned assets.
