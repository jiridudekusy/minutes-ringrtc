# Minutes RingRTC changelog

This file records only changes maintained by the Minutes fork. Signal's
upstream release history remains in `CHANGELOG.md`.

## [Unreleased]

- (add release notes)

## [2.70.2-minutes.3] - 2026-08-20

- Rebuild WebRTC with production settings after running the post-APM audio tap
  test so published native addons match upstream release configuration.

## [2.70.2-minutes.2] - 2026-08-12

- Make release version tests independent of the live changelog contents and
  explicitly dispatch native addon builds after creating a release tag.

## [2.70.2-minutes.1] - 2026-08-12

- Synchronize the Signal RingRTC baseline from 2.69.7 to 2.70.2.

- Add automated stable-upstream detection, sync pull requests, release versioning,
  and a machine-verified fork patch manifest.
- Add Linux x64 to the checksum-pinned native addon release matrix.
- Keep optional recording-tap failures from blocking mute, leave, disconnect,
  or hangup actions.
- Remove the global audio-device mutex from the post-APM capture hot path and
  preserve buffered PCM across transient tap contention.
- Harden fork workflows by pinning privileged actions and avoiding direct shell
  interpolation of manual inputs.

## [2.69.7-minutes.3] - 2026-07-31

- Capture outgoing local audio after WebRTC audio processing so recordings match
  the signal sent to the remote participant.
- Keep the WebRTC processor modification in a separate, idempotent patch queue.
- Fix the processor's WebRTC GN dependencies.

## [2.69.7-minutes.2] - 2026-07-22

- Add a bounded outgoing screen-share video tap with explicit inactive events.
- Add Node and Rust tests for outgoing video tap lifecycle and frame formats.

## [2.69.7-minutes.1] - 2026-07-22

- Add versioned local-input and remote-playout PCM taps for recording.
- Preserve sample-offset gaps under contention instead of compressing time.
- Publish the `@minutes/ringrtc` compatibility package with checksum-pinned
  macOS ARM64 and Windows x64 native addons.
