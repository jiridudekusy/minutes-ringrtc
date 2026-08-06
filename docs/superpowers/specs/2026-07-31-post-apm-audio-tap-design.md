# Post-APM outgoing audio tap

## Goal

The RingRTC audio tap must expose the local audio that WebRTC is about to send,
not the raw samples read from the selected microphone. This makes Minutes
recordings use the same echo cancellation, noise suppression, high-pass filter,
and gain control as the live Signal call.

Remote audio remains the decoded RingRTC playout signal. The public Node API
continues to provide one 48 kHz mono local stream and one 48 kHz mono remote
stream, so Signal Desktop/Minutes needs no behavioral API migration.

## Current behavior and defect

The custom desktop audio device module currently calls
`audio_tap.push_local_input(chunk)` immediately before
`RecordedDataIsAvailable`. WebRTC applies its Audio Processing Module only after
that call. Consequently, loudspeaker output captured acoustically by the
microphone is present in the Minutes local stream even when WebRTC later removes
it from the stream sent to the peer. Minutes then mixes that raw local signal
with remote playout and can record the remote speaker twice with a delay.

## Architecture

Use WebRTC's `AudioFrameProcessor`, the supported extension point for captured
audio after the Audio Processing Module and before encoder fan-out.

The RingRTC-managed WebRTC integration will install a transparent processor
when constructing the desktop peer connection factory. For each processed
`AudioFrame`, it will:

1. copy the frame into the existing RingRTC `AudioTap` through a small callback
   added to the desktop audio-device callback table;
2. normalize only the tap copy to the existing 48 kHz mono contract when the
   processed frame has a different rate or channel count;
3. forward the original frame, unchanged and exactly once, through the
   processor sink callback.

The raw microphone call to `push_local_input` will be removed. Remote playout
continues to be tapped immediately after `NeedMorePlayData`, before hardware
playout. Existing active/mute gating remains in `AudioTap`, so a muted local
sender contributes timeline-preserving silence.

The small WebRTC-side change will be owned by this fork as a versioned patch
against the pinned `signalapp/webrtc` revision and applied by workspace setup.
Release builds must use WebRTC artifacts produced with that patch; they must not
combine the new Rust callback ABI with Signal's unmodified prebuilt artifact.

## Data flow

```text
microphone -> desktop ADM -> WebRTC APM -> AudioFrameProcessor -> encoder/network
                                      |-> RingRTC local audio tap

decoded remote audio -> NeedMorePlayData -> speakers
                                    |-> RingRTC remote audio tap

RingRTC local + remote taps -> Minutes mono recording mix
```

## Failure and lifecycle behavior

- When the tap is inactive, the processor remains a pass-through and performs
  no copy or resampling work.
- Failure to copy into the bounded tap never blocks or alters the call. Existing
  dropped-sample accounting represents the gap as silence.
- Processor installation and teardown follow the peer connection factory
  lifetime. The callback target remains alive through the existing retained ADM
  reference.
- Starting or stopping a recording changes only tap state; it does not recreate
  the processor or peer connection factory.
- Direct and group calls share the same processed-capture point and therefore
  have identical semantics.

## Compatibility

- Keep audio tap API version 1 and its JavaScript shape unchanged.
- Keep `localInputStartSample`, `remotePlayoutStartSample`, drop counters, mute
  behavior, and the 48 kHz mono PCM representation unchanged.
- Bump only the `@minutes/ringrtc` package suffix for the new native build, then
  update Minutes to the checksum-pinned release.

## Verification

Development follows red-green-refactor:

1. Add a failing Rust callback/tap test proving raw ADM capture is not appended
   and processed frames are appended while active.
2. Add a failing WebRTC processor test proving the original frame is forwarded
   once and the tap receives the post-APM frame.
3. Preserve existing audio tap, Node API, ADM, and packaging tests.
4. Build and load the macOS arm64 Node addon and verify audio tap API version 1.
5. In a two-endpoint call using internal speakers and microphone, play remote
   speech loudly, record it, and verify the recording contains one remote copy
   rather than the delayed raw-microphone copy. Repeat after an audio-device or
   camera reinitialization to ensure the tap remains live.

## Non-goals

- No new echo canceller or noise suppressor is implemented in Minutes.
- No change is made to Signal's AEC/NS/AGC configuration.
- Local and remote stems are not exposed as separate recording files.
- The unrelated long-recording silence defect is not implicitly considered
  fixed; the reinitialization test only detects whether this architecture also
  resolves it.
