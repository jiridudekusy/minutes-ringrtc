//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

use ringrtc::audio_tap::{AudioTap, AudioTapSource, pcm_i16_to_le_bytes};

#[test]
fn inactive_tap_ignores_samples() {
    let tap = AudioTap::new(4);

    tap.push(AudioTapSource::LocalInput, &[1, 2]);
    tap.push(AudioTapSource::RemotePlayout, &[3, 4]);

    let drained = tap.drain(usize::MAX);
    assert!(drained.local_input.is_empty());
    assert!(drained.remote_playout.is_empty());
}

#[test]
fn active_tap_keeps_sources_separate_and_drains_in_order() {
    let tap = AudioTap::new(8);
    tap.start();

    tap.push(AudioTapSource::RemotePlayout, &[10, 11]);
    tap.push(AudioTapSource::LocalInput, &[1, 2, 3]);

    let drained = tap.drain(2);
    assert_eq!(drained.local_input, vec![1, 2]);
    assert_eq!(drained.remote_playout, vec![10, 11]);

    let remainder = tap.drain(usize::MAX);
    assert_eq!(remainder.local_input, vec![3]);
    assert!(remainder.remote_playout.is_empty());
}

#[test]
fn bounded_tap_drops_oldest_samples_and_reports_loss() {
    let tap = AudioTap::new(3);
    tap.start();

    tap.push(AudioTapSource::LocalInput, &[1, 2]);
    tap.push(AudioTapSource::LocalInput, &[3, 4, 5]);

    let drained = tap.drain(usize::MAX);
    assert_eq!(drained.local_input, vec![3, 4, 5]);
    assert_eq!(drained.dropped_local_input, 2);
    assert_eq!(drained.dropped_remote_playout, 0);
}

#[test]
fn stop_preserves_final_samples_but_blocks_new_writes() {
    let tap = AudioTap::new(4);
    tap.start();
    tap.push(AudioTapSource::LocalInput, &[1, 2]);

    tap.stop();
    tap.push(AudioTapSource::LocalInput, &[3, 4]);

    assert!(!tap.is_active());
    assert_eq!(tap.drain(usize::MAX).local_input, vec![1, 2]);
}

#[test]
fn restart_clears_samples_and_loss_counters_from_previous_session() {
    let tap = AudioTap::new(2);
    tap.start();
    tap.push(AudioTapSource::RemotePlayout, &[1, 2, 3]);
    tap.stop();

    tap.start();
    tap.push(AudioTapSource::RemotePlayout, &[4]);

    let drained = tap.drain(usize::MAX);
    assert_eq!(drained.remote_playout, vec![4]);
    assert_eq!(drained.dropped_remote_playout, 0);
}

#[test]
fn disabled_outgoing_track_taps_silence_instead_of_microphone_samples() {
    let tap = AudioTap::new(4);
    tap.start();
    tap.set_local_input_enabled(false);

    tap.push_local_input(&[7, 8, 9]);
    tap.push(AudioTapSource::RemotePlayout, &[4, 5]);

    let drained = tap.drain(usize::MAX);
    assert_eq!(drained.local_input, vec![0, 0, 0]);
    assert_eq!(drained.remote_playout, vec![4, 5]);
}

#[test]
fn pcm_is_exposed_as_explicit_little_endian_bytes() {
    assert_eq!(
        pcm_i16_to_le_bytes(vec![0x1234, -2]),
        vec![0x34, 0x12, 0xfe, 0xff]
    );
}

#[test]
fn sample_offsets_are_monotonic_and_include_overflowed_samples() {
    let tap = AudioTap::new(3);
    tap.start();

    tap.push(AudioTapSource::LocalInput, &[1, 2, 3, 4]);
    let first = tap.drain(2);
    assert_eq!(first.local_input_start_sample, 1);
    assert_eq!(first.local_input, vec![2, 3]);

    tap.push(AudioTapSource::LocalInput, &[5, 6]);
    let second = tap.drain(usize::MAX);
    assert_eq!(second.local_input_start_sample, 3);
    assert_eq!(second.local_input, vec![4, 5, 6]);
}
