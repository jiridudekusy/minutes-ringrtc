//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

//! A bounded latest-frame tap for outgoing desktop video.

use std::{
    sync::{
        Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::Instant,
};

pub const VIDEO_TAP_API_VERSION: u32 = 1;

#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VideoTapFormat {
    I420 = 0,
    Nv12 = 1,
    Rgba = 2,
}

impl VideoTapFormat {
    pub fn from_i32(value: i32) -> Option<Self> {
        match value {
            0 => Some(Self::I420),
            1 => Some(Self::Nv12),
            2 => Some(Self::Rgba),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VideoTapFrame {
    pub sequence: u64,
    pub timestamp_us: u64,
    pub width: u32,
    pub height: u32,
    pub format: VideoTapFormat,
    pub data: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VideoTapInactive {
    pub sequence: u64,
    pub timestamp_us: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum VideoTapEvent {
    Inactive(VideoTapInactive),
    Frame(VideoTapFrame),
}

impl VideoTapEvent {
    pub fn sequence(&self) -> u64 {
        match self {
            Self::Inactive(event) => event.sequence,
            Self::Frame(frame) => frame.sequence,
        }
    }
}

#[derive(Debug)]
struct Session {
    start: Instant,
    next_sequence: u64,
    latest: Option<VideoTapEvent>,
}

#[derive(Debug)]
pub struct VideoTap {
    active: AtomicBool,
    outgoing_video_enabled: AtomicBool,
    screen_share: AtomicBool,
    session: Mutex<Session>,
}

impl Default for VideoTap {
    fn default() -> Self {
        Self {
            active: AtomicBool::new(false),
            outgoing_video_enabled: AtomicBool::new(false),
            screen_share: AtomicBool::new(false),
            session: Mutex::new(Session {
                start: Instant::now(),
                next_sequence: 1,
                latest: None,
            }),
        }
    }
}

impl VideoTap {
    pub fn start(&self) {
        self.active.store(false, Ordering::Release);
        if let Ok(mut session) = self.session.lock() {
            session.start = Instant::now();
            session.next_sequence = 1;
            session.latest = None;
        }
        self.active.store(true, Ordering::Release);
        if !self.should_capture() {
            self.publish_inactive();
        }
    }

    pub fn stop(&self) {
        self.active.store(false, Ordering::Release);
        if let Ok(mut session) = self.session.lock() {
            session.latest = None;
        }
    }

    pub fn set_outgoing_video_enabled(&self, enabled: bool) {
        let was_capturing = self.should_capture();
        self.outgoing_video_enabled
            .store(enabled, Ordering::Release);
        if was_capturing && !self.should_capture() {
            self.publish_inactive();
        }
    }

    pub fn set_screen_share(&self, screen_share: bool) {
        let was_capturing = self.should_capture();
        self.screen_share.store(screen_share, Ordering::Release);
        if was_capturing && !self.should_capture() {
            self.publish_inactive();
        }
    }

    pub fn reset_outgoing_state(&self) {
        self.outgoing_video_enabled.store(false, Ordering::Release);
        self.screen_share.store(false, Ordering::Release);
        self.publish_inactive();
    }

    pub fn push(&self, width: u32, height: u32, format: VideoTapFormat, data: &[u8]) {
        if !self.should_capture() {
            return;
        }
        let Some(frame_len) = packed_frame_len(width, height, format) else {
            return;
        };
        let Some(data) = data.get(..frame_len) else {
            return;
        };
        let Ok(mut session) = self.session.try_lock() else {
            return;
        };
        if !self.should_capture() {
            return;
        }

        let sequence = session.next_sequence;
        session.next_sequence = session.next_sequence.saturating_add(1);
        session.latest = Some(VideoTapEvent::Frame(VideoTapFrame {
            sequence,
            timestamp_us: session.start.elapsed().as_micros().min(u64::MAX as u128) as u64,
            width,
            height,
            format,
            data: data.to_vec(),
        }));
    }

    pub fn read(&self, last_sequence: u64) -> Option<VideoTapEvent> {
        if !self.active.load(Ordering::Acquire) {
            return None;
        }
        self.session.lock().ok().and_then(|session| {
            session
                .latest
                .as_ref()
                .filter(|event| event.sequence() > last_sequence)
                .cloned()
        })
    }

    fn publish_inactive(&self) {
        if !self.active.load(Ordering::Acquire) {
            return;
        }
        let Ok(mut session) = self.session.lock() else {
            return;
        };
        let sequence = session.next_sequence;
        session.next_sequence = session.next_sequence.saturating_add(1);
        session.latest = Some(VideoTapEvent::Inactive(VideoTapInactive {
            sequence,
            timestamp_us: session.start.elapsed().as_micros().min(u64::MAX as u128) as u64,
        }));
    }

    fn should_capture(&self) -> bool {
        self.active.load(Ordering::Acquire)
            && self.outgoing_video_enabled.load(Ordering::Acquire)
            && self.screen_share.load(Ordering::Acquire)
    }
}

fn packed_frame_len(width: u32, height: u32, format: VideoTapFormat) -> Option<usize> {
    if width == 0 || height == 0 {
        return None;
    }
    let width = usize::try_from(width).ok()?;
    let height = usize::try_from(height).ok()?;
    let luma_pixels = width.checked_mul(height)?;
    match format {
        VideoTapFormat::Rgba => luma_pixels.checked_mul(4),
        VideoTapFormat::I420 | VideoTapFormat::Nv12 => {
            let chroma_width = width.checked_add(1)? / 2;
            let chroma_height = height.checked_add(1)? / 2;
            let chroma_plane = chroma_width.checked_mul(chroma_height)?;
            luma_pixels.checked_add(chroma_plane.checked_mul(2)?)
        }
    }
}
