# Minutes RingRTC

Minutes RingRTC is a maintained fork of
[`signalapp/ringrtc`](https://github.com/signalapp/ringrtc). It preserves the
complete upstream calling API and adds bounded, versioned recording taps used by
Minutes Desktop.

## Maintenance model

- `config/minutes_desktop_artifacts.json` is the source of truth for the
  upstream version, fork package version, tap API, and release targets.
- `config/minutes_fork_patch_manifest.json` classifies every path that differs
  from the upstream tag as either fork-owned or a documented upstream patch.
- `docs/MINUTES-PATCHES.md` is generated from that manifest.
- `MINUTES-CHANGELOG.md` contains fork release notes; upstream keeps owning
  `CHANGELOG.md`.
- `.github/workflows/minutes_merge_upstream.yml` checks weekly for the newest
  stable RingRTC tag and opens a sync pull request.
- `.github/workflows/minutes_release.yml` prepares and tags a new Minutes fork
  revision. The existing native-artifact workflow builds and publishes the tag.

The native recording implementation lives in fork-owned modules wherever
possible. Files inherited from RingRTC contain only the FFI, registration, and
build hooks needed to reach those modules. Changes to the separately checked-out
Signal WebRTC source live in `patches/webrtc/` and are applied idempotently.

See [`docs/FORK-MAINTENANCE.md`](docs/FORK-MAINTENANCE.md) before changing an
upstream-owned file.

## Distribution and installation

Minutes publishes one checksum-pinned native addon for each supported target:
macOS ARM64, Linux x64, and Windows x64. Install a released package tarball (or
the matching npm release) at an exact `X.Y.Z-minutes.N` version. Direct installs
from a Git tag or repository checkout are intentionally unsupported.

The committed `src/node/prebuilds.json` is only a release template, so its
checksums are blank. The native-artifact workflow fills those checksums after it
builds the addons and embeds the completed manifest in the published package.
An install from source therefore fails closed instead of downloading an
unverified binary.

## Local checks

```sh
python3 -m unittest discover -s bin/tests -p 'test_*.py' -v
python3 bin/minutes_version.py validate
python3 bin/minutes_patch_manifest.py check --include-working-tree

cd src/node
npm ci --ignore-scripts
npm run build
npm run test:distribution
```

Full native builds continue to use the target matrix in
`config/minutes_desktop_artifacts.json`.
