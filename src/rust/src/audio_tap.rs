//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

//! A bounded, non-blocking tap for the desktop audio device module.
//!
//! Audio callback threads never wait for the consumer. If the buffer lock is
//! busy or its capacity is exceeded, samples are dropped and reported to the
//! consumer so it can insert silence and preserve its media timeline.

use std::{
    collections::VecDeque,
    sync::{
        Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
};

pub const AUDIO_TAP_SAMPLE_RATE: u32 = 48_000;
pub const AUDIO_TAP_CHANNELS: u8 = 1;
pub const AUDIO_TAP_API_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AudioTapSource {
    LocalInput,
    RemotePlayout,
}

#[derive(Debug, Default, Eq, PartialEq)]
pub struct AudioTapChunk {
    pub local_input: Vec<i16>,
    pub remote_playout: Vec<i16>,
    pub local_input_start_sample: u64,
    pub remote_playout_start_sample: u64,
    pub dropped_local_input: u64,
    pub dropped_remote_playout: u64,
}

#[derive(Debug, Default)]
struct Buffers {
    local_input: VecDeque<i16>,
    remote_playout: VecDeque<i16>,
    local_input_start_sample: u64,
    remote_playout_start_sample: u64,
}

#[derive(Debug)]
pub struct AudioTap {
    capacity_samples_per_source: usize,
    active: AtomicBool,
    local_input_enabled: AtomicBool,
    buffers: Mutex<Buffers>,
    dropped_local_input: AtomicU64,
    dropped_remote_playout: AtomicU64,
}

impl AudioTap {
    pub fn new(capacity_samples_per_source: usize) -> Self {
        assert!(capacity_samples_per_source > 0);
        Self {
            capacity_samples_per_source,
            active: AtomicBool::new(false),
            local_input_enabled: AtomicBool::new(false),
            buffers: Mutex::new(Buffers::default()),
            dropped_local_input: AtomicU64::new(0),
            dropped_remote_playout: AtomicU64::new(0),
        }
    }

    pub fn start(&self) {
        self.active.store(false, Ordering::Release);
        if let Ok(mut buffers) = self.buffers.lock() {
            buffers.local_input.clear();
            buffers.remote_playout.clear();
            buffers.local_input_start_sample = 0;
            buffers.remote_playout_start_sample = 0;
        }
        self.dropped_local_input.store(0, Ordering::Relaxed);
        self.dropped_remote_playout.store(0, Ordering::Relaxed);
        self.active.store(true, Ordering::Release);
    }

    pub fn stop(&self) {
        self.active.store(false, Ordering::Release);
        // Synchronize with any callback that passed the active check just before stop.
        drop(self.buffers.lock());
    }

    pub fn is_active(&self) -> bool {
        self.active.load(Ordering::Acquire)
    }

    pub fn push(&self, source: AudioTapSource, samples: &[i16]) {
        if samples.is_empty() || !self.is_active() {
            return;
        }

        let dropped = match self.buffers.try_lock() {
            Ok(mut buffers) => {
                let dropped = match source {
                    AudioTapSource::LocalInput => append_bounded(
                        &mut buffers.local_input,
                        samples,
                        self.capacity_samples_per_source,
                    ),
                    AudioTapSource::RemotePlayout => append_bounded(
                        &mut buffers.remote_playout,
                        samples,
                        self.capacity_samples_per_source,
                    ),
                };
                match source {
                    AudioTapSource::LocalInput => {
                        buffers.local_input_start_sample += dropped;
                    }
                    AudioTapSource::RemotePlayout => {
                        buffers.remote_playout_start_sample += dropped;
                    }
                }
                dropped
            }
            Err(_) => samples.len() as u64,
        };

        if dropped > 0 {
            self.dropped_counter(source)
                .fetch_add(dropped, Ordering::Relaxed);
        }
    }

    pub fn set_local_input_enabled(&self, enabled: bool) {
        self.local_input_enabled.store(enabled, Ordering::Release);
    }

    pub fn push_local_input(&self, samples: &[i16]) {
        if self.local_input_enabled.load(Ordering::Acquire) {
            self.push(AudioTapSource::LocalInput, samples);
        } else {
            self.push_silence(AudioTapSource::LocalInput, samples.len());
        }
    }

    pub fn drain(&self, max_samples_per_source: usize) -> AudioTapChunk {
        let (local_input, remote_playout, local_input_start_sample, remote_playout_start_sample) =
            self.buffers.lock().map_or_else(
                |_| (Vec::new(), Vec::new(), 0, 0),
                |mut buffers| {
                    let local_input_start_sample = buffers.local_input_start_sample;
                    let remote_playout_start_sample = buffers.remote_playout_start_sample;
                    let local_input = drain_front(&mut buffers.local_input, max_samples_per_source);
                    let remote_playout =
                        drain_front(&mut buffers.remote_playout, max_samples_per_source);
                    buffers.local_input_start_sample += local_input.len() as u64;
                    buffers.remote_playout_start_sample += remote_playout.len() as u64;
                    (
                        local_input,
                        remote_playout,
                        local_input_start_sample,
                        remote_playout_start_sample,
                    )
                },
            );

        AudioTapChunk {
            local_input,
            remote_playout,
            local_input_start_sample,
            remote_playout_start_sample,
            dropped_local_input: self.dropped_local_input.swap(0, Ordering::Relaxed),
            dropped_remote_playout: self.dropped_remote_playout.swap(0, Ordering::Relaxed),
        }
    }

    fn dropped_counter(&self, source: AudioTapSource) -> &AtomicU64 {
        match source {
            AudioTapSource::LocalInput => &self.dropped_local_input,
            AudioTapSource::RemotePlayout => &self.dropped_remote_playout,
        }
    }

    fn push_silence(&self, source: AudioTapSource, sample_count: usize) {
        if sample_count == 0 || !self.is_active() {
            return;
        }

        let dropped = match self.buffers.try_lock() {
            Ok(mut buffers) => {
                let dropped = match source {
                    AudioTapSource::LocalInput => append_silence_bounded(
                        &mut buffers.local_input,
                        sample_count,
                        self.capacity_samples_per_source,
                    ),
                    AudioTapSource::RemotePlayout => append_silence_bounded(
                        &mut buffers.remote_playout,
                        sample_count,
                        self.capacity_samples_per_source,
                    ),
                };
                match source {
                    AudioTapSource::LocalInput => {
                        buffers.local_input_start_sample += dropped;
                    }
                    AudioTapSource::RemotePlayout => {
                        buffers.remote_playout_start_sample += dropped;
                    }
                }
                dropped
            }
            Err(_) => sample_count as u64,
        };
        if dropped > 0 {
            self.dropped_counter(source)
                .fetch_add(dropped, Ordering::Relaxed);
        }
    }
}

fn append_bounded(buffer: &mut VecDeque<i16>, samples: &[i16], capacity: usize) -> u64 {
    let dropped = buffer
        .len()
        .saturating_add(samples.len())
        .saturating_sub(capacity);
    let dropped_from_buffer = dropped.min(buffer.len());
    buffer.drain(..dropped_from_buffer);

    let first_sample = dropped.saturating_sub(dropped_from_buffer);
    buffer.extend(&samples[first_sample..]);
    dropped as u64
}

fn append_silence_bounded(buffer: &mut VecDeque<i16>, sample_count: usize, capacity: usize) -> u64 {
    let dropped = buffer
        .len()
        .saturating_add(sample_count)
        .saturating_sub(capacity);
    let dropped_from_buffer = dropped.min(buffer.len());
    buffer.drain(..dropped_from_buffer);

    let retained_samples = sample_count.saturating_sub(dropped - dropped_from_buffer);
    buffer.extend(std::iter::repeat_n(0, retained_samples));
    dropped as u64
}

fn drain_front(buffer: &mut VecDeque<i16>, max_samples: usize) -> Vec<i16> {
    let count = buffer.len().min(max_samples);
    buffer.drain(..count).collect()
}

pub fn pcm_i16_to_le_bytes(samples: Vec<i16>) -> Vec<u8> {
    samples
        .into_iter()
        .flat_map(i16::to_le_bytes)
        .collect::<Vec<_>>()
}
