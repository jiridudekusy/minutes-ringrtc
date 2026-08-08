//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

use std::{thread, time::Duration};

use ringrtc::video_tap::{VIDEO_TAP_API_VERSION, VideoTap, VideoTapEvent, VideoTapFormat};

const RGBA: VideoTapFormat = VideoTapFormat::Rgba;

#[test]
fn exposes_versioned_api_and_stays_empty_while_inactive() {
    assert_eq!(VIDEO_TAP_API_VERSION, 1);
    let tap = VideoTap::default();

    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.push(2, 1, RGBA, &[1, 2, 3, 4, 5, 6, 7, 8]);

    assert_eq!(tap.read(0), None);
}

#[test]
fn retains_only_the_latest_frame_and_uses_sequence_for_incremental_reads() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();

    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    tap.push(1, 1, RGBA, &[5, 6, 7, 8]);

    let VideoTapEvent::Frame(latest) = tap.read(0).expect("latest frame") else {
        panic!("expected active frame");
    };
    assert_eq!(latest.sequence, 2);
    assert_eq!(latest.width, 1);
    assert_eq!(latest.height, 1);
    assert_eq!(latest.format, RGBA);
    assert_eq!(latest.data, [5, 6, 7, 8]);
    assert_eq!(tap.read(latest.sequence), None);
}

#[test]
fn screen_share_only_requires_enabled_outgoing_screen_share() {
    let tap = VideoTap::default();
    tap.start();

    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    let VideoTapEvent::Inactive(started_inactive) = tap.read(0).expect("initial inactive event")
    else {
        panic!("expected inactive event");
    };
    assert_eq!(started_inactive.sequence, 1);

    tap.set_outgoing_video_enabled(true);
    tap.push(1, 1, RGBA, &[5, 6, 7, 8]);
    assert_eq!(tap.read(started_inactive.sequence), None);

    tap.set_screen_share(true);
    tap.push(1, 1, RGBA, &[9, 10, 11, 12]);
    let VideoTapEvent::Frame(shared) = tap
        .read(started_inactive.sequence)
        .expect("screen-share frame")
    else {
        panic!("expected active frame");
    };
    assert_eq!(shared.sequence, 2);

    tap.set_outgoing_video_enabled(false);
    tap.push(1, 1, RGBA, &[13, 14, 15, 16]);
    let VideoTapEvent::Inactive(disabled) = tap.read(shared.sequence).expect("disabled event")
    else {
        panic!("expected inactive event");
    };
    assert_eq!(disabled.sequence, 3);
    assert_eq!(tap.read(disabled.sequence), None);
}

#[test]
fn enabled_camera_video_is_never_captured() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(false);
    tap.start();
    let VideoTapEvent::Inactive(inactive) = tap.read(0).expect("initial inactive event") else {
        panic!("expected inactive event");
    };

    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);

    assert_eq!(tap.read(inactive.sequence), None);
}

#[test]
fn stop_clears_the_slot_and_restart_resets_sequence_and_timestamp_origin() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();
    thread::sleep(Duration::from_millis(2));
    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    let VideoTapEvent::Frame(first) = tap.read(0).expect("first session frame") else {
        panic!("expected active frame");
    };
    assert!(first.timestamp_us >= 1_000);

    tap.stop();
    assert_eq!(tap.read(0), None);

    tap.start();
    tap.push(1, 1, RGBA, &[5, 6, 7, 8]);
    let VideoTapEvent::Frame(restarted) = tap.read(0).expect("restarted session frame") else {
        panic!("expected active frame");
    };
    assert_eq!(restarted.sequence, 1);
    assert!(restarted.timestamp_us < first.timestamp_us);
}

#[test]
fn ending_screen_share_publishes_inactive_only_in_screen_share_only_mode() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();
    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    let VideoTapEvent::Frame(frame) = tap.read(0).expect("screen-share frame") else {
        panic!("expected active frame");
    };

    tap.set_screen_share(false);

    let VideoTapEvent::Inactive(inactive) = tap.read(frame.sequence).expect("inactive event")
    else {
        panic!("expected inactive event");
    };
    assert_eq!(inactive.sequence, frame.sequence + 1);
}

#[test]
fn copies_only_the_tightly_packed_frame_prefix() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();

    tap.push(2, 1, RGBA, &[1, 2, 3, 4, 5, 6, 7, 8, 99, 100]);
    let VideoTapEvent::Frame(rgba) = tap.read(0).expect("rgba frame") else {
        panic!("expected active frame");
    };
    assert_eq!(rgba.data, [1, 2, 3, 4, 5, 6, 7, 8]);

    tap.push(3, 3, VideoTapFormat::I420, &[7; 64]);
    let VideoTapEvent::Frame(i420) = tap.read(rgba.sequence).expect("i420 frame") else {
        panic!("expected active frame");
    };
    assert_eq!(i420.data.len(), 17);

    tap.push(3, 3, VideoTapFormat::Nv12, &[8; 64]);
    let VideoTapEvent::Frame(nv12) = tap.read(i420.sequence).expect("nv12 frame") else {
        panic!("expected active frame");
    };
    assert_eq!(nv12.data.len(), 17);
}

#[test]
fn ignores_short_or_overflowing_frames_without_advancing_sequence() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();
    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    let VideoTapEvent::Frame(first) = tap.read(0).expect("valid frame") else {
        panic!("expected active frame");
    };

    tap.push(2, 2, RGBA, &[0; 15]);
    tap.push(u32::MAX, u32::MAX, RGBA, &[]);

    assert_eq!(tap.read(first.sequence), None);
}

#[test]
fn resetting_outgoing_state_replaces_the_latest_frame_with_inactive() {
    let tap = VideoTap::default();
    tap.set_outgoing_video_enabled(true);
    tap.set_screen_share(true);
    tap.start();
    tap.push(1, 1, RGBA, &[1, 2, 3, 4]);
    let VideoTapEvent::Frame(frame) = tap.read(0).expect("screen-share frame") else {
        panic!("expected active frame");
    };

    tap.reset_outgoing_state();

    let VideoTapEvent::Inactive(inactive) = tap.read(frame.sequence).expect("inactive event")
    else {
        panic!("expected inactive event");
    };
    tap.push(1, 1, RGBA, &[5, 6, 7, 8]);
    assert_eq!(tap.read(inactive.sequence), None);
}

#[test]
fn resetting_an_already_inactive_tap_refreshes_the_inactive_event() {
    let tap = VideoTap::default();
    tap.start();
    let VideoTapEvent::Inactive(initial) = tap.read(0).expect("initial inactive event") else {
        panic!("expected inactive event");
    };

    tap.reset_outgoing_state();

    let VideoTapEvent::Inactive(reset) = tap.read(initial.sequence).expect("reset inactive event")
    else {
        panic!("expected inactive event");
    };
    assert_eq!(reset.sequence, initial.sequence + 1);
}
