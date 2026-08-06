//
// Copyright 2024 Signal Messenger, LLC
// SPDX-License-Identifier: AGPL-3.0-only
//

//! WebRTC FFI ADM interface.

use std::{
    ffi::{c_uchar, c_void},
    sync::{Arc, LockResult, Mutex, MutexGuard},
};

use libc::size_t;

use crate::{
    audio_tap::AudioTap,
    webrtc,
    webrtc::audio_device_module::{AudioDeviceModule, AudioLayer},
};

/// Shared owner passed through the stable ADM FFI pointer. Ordinary ADM
/// callbacks lock `adm`, while the 10 ms post-APM callback reads `audio_tap`
/// directly and therefore never contends with device enumeration or switching.
#[derive(Debug)]
pub struct AudioDeviceModuleHandle {
    adm: Mutex<AudioDeviceModule>,
    audio_tap: Arc<AudioTap>,
}

impl AudioDeviceModuleHandle {
    pub fn new(adm: AudioDeviceModule) -> Self {
        let audio_tap = adm.audio_tap();
        Self {
            adm: Mutex::new(adm),
            audio_tap,
        }
    }

    pub fn lock(&self) -> LockResult<MutexGuard<'_, AudioDeviceModule>> {
        self.adm.lock()
    }
}

fn audio_tap_is_active_impl(tap: &AudioTap) -> bool {
    tap.is_active()
}

fn push_processed_local_audio_impl(tap: &AudioTap, samples: &[i16]) -> bool {
    if samples.is_empty() {
        return false;
    }
    tap.push_local_input(samples);
    true
}

/// all_adm_functions is a higher-level macro that enables "tt muncher" macros
/// The list of functions MUST be kept in sync with AudioDeviceCallbacks in webrtc C++, and
/// in particular the order must match.
macro_rules! all_adm_functions {
    ($macro:ident) => {
        $macro!(
            active_audio_layer(audio_layer: webrtc::ptr::Borrowed<AudioLayer>) -> i32;

            // Main initialization and termination
            init() -> i32;
            terminate() -> i32;
            initialized() -> bool;

            // Device enumeration
            playout_devices() -> i16;
            recording_devices() -> i16;
            playout_device_name(index: u16, name: webrtc::ptr::Borrowed<c_uchar>, guid: webrtc::ptr::Borrowed<c_uchar>) -> i32;
            recording_device_name(index: u16, name: webrtc::ptr::Borrowed<c_uchar>, guid: webrtc::ptr::Borrowed<c_uchar>) -> i32;

            // Audio transport initialization
            playout_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            init_playout() -> i32;
            playout_is_initialized() -> bool;

            recording_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            init_recording() -> i32;
            recording_is_initialized() -> bool;

            // Audio transport control
            start_playout() -> i32;
            stop_playout() -> i32;

            playing() -> bool;
            start_recording() -> i32;
            stop_recording() -> i32;
            recording() -> bool;

            // Audio mixer initialization
            init_speaker() -> i32;
            speaker_is_initialized() -> bool;
            init_microphone() -> i32;
            microphone_is_initialized() -> bool;

            // Speaker volume controls
            speaker_volume_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_speaker_volume(volume: u32) -> i32;
            speaker_volume(volume: webrtc::ptr::Borrowed<u32>) -> i32;
            max_speaker_volume(max_volume: webrtc::ptr::Borrowed<u32>) -> i32;
            min_speaker_volume(min_volume: webrtc::ptr::Borrowed<u32>) -> i32;

            // Microphone volume controls
            microphone_volume_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_microphone_volume(volume: u32) -> i32;
            microphone_volume(volume: webrtc::ptr::Borrowed<u32>) -> i32;
            max_microphone_volume(max_volume: webrtc::ptr::Borrowed<u32>) -> i32;
            min_microphone_volume(min_volume: webrtc::ptr::Borrowed<u32>) -> i32;

            // Speaker mute control
            speaker_mute_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_speaker_mute(enable: bool) -> i32;
            speaker_mute(enabled: webrtc::ptr::Borrowed<bool>) -> i32;

            // Microphone mute control
            microphone_mute_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_microphone_mute(enable: bool) -> i32;
            microphone_mute(enabled: webrtc::ptr::Borrowed<bool>) -> i32;

            // Stereo support
            stereo_playout_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_stereo_playout(enable: bool) -> i32;
            stereo_playout(enabled: webrtc::ptr::Borrowed<bool>) -> i32;
            stereo_recording_is_available(available: webrtc::ptr::Borrowed<bool>) -> i32;
            set_stereo_recording(enable: bool) -> i32;
            stereo_recording(enabled: webrtc::ptr::Borrowed<bool>) -> i32;

            // Playout delay
            playout_delay(delay_ms: webrtc::ptr::Borrowed<u16>) -> i32;

            // Processed local capture, after WebRTC audio processing. These
            // callbacks intentionally bypass the ADM mutex.
            audio_tap_is_active() -> bool;
            push_processed_local_audio(samples: webrtc::ptr::Borrowed<i16>, sample_count: size_t) -> bool;
        );
    }
}

// Enum used to tag failures due to the adm pointer being null
enum InternalFailure {
    NullPtr,
    MutexPoison,
}
// Methods to convert rust-style errors into return types matching C/++ types
impl From<InternalFailure> for i32 {
    fn from(_failure: InternalFailure) -> i32 {
        -1
    }
}
impl From<InternalFailure> for i16 {
    fn from(_failure: InternalFailure) -> i16 {
        -1
    }
}
impl From<InternalFailure> for bool {
    fn from(_failure: InternalFailure) -> bool {
        false
    }
}

/// Generator macro for the full list of functions to be called by C++ rffi.
/// These dispatch to AudioDeviceModule.
/// Note that these functions are dispatched via pointers, and *not* called directly, so they don't
/// need to worry about name mangling or matching case with C++.
macro_rules! adm_wrapper {
    () => {};
    (audio_tap_is_active() -> bool ; $($t:tt)*) => {
        extern "C" fn audio_tap_is_active(
            ptr: webrtc::ptr::Borrowed<AudioDeviceModuleHandle>,
        ) -> bool {
            // Safety: C++ retains the Arc backing this pointer until the peer
            // connection factory and its audio processor are destroyed.
            unsafe { ptr.as_ref() }
                .is_some_and(|handle| audio_tap_is_active_impl(&handle.audio_tap))
        }
        adm_wrapper!($($t)*);
    };
    (push_processed_local_audio(samples: webrtc::ptr::Borrowed<i16>, sample_count: size_t) -> bool ; $($t:tt)*) => {
        extern "C" fn push_processed_local_audio(
            ptr: webrtc::ptr::Borrowed<AudioDeviceModuleHandle>,
            samples: webrtc::ptr::Borrowed<i16>,
            sample_count: size_t,
        ) -> bool {
            // Safety: The handle has the lifetime described above. WebRTC owns
            // the sample buffer for the duration of this synchronous callback.
            let Some(handle) = (unsafe { ptr.as_ref() }) else {
                return false;
            };
            if samples.is_null() || sample_count == 0 {
                return false;
            }
            let samples = unsafe { std::slice::from_raw_parts(samples.as_ptr(), sample_count) };
            push_processed_local_audio_impl(&handle.audio_tap, samples)
        }
        adm_wrapper!($($t)*);
    };
    ($f:ident($($param:ident: $arg_ty:ty),*) -> $ret:ty ; $($t:tt)*) => {
        extern "C" fn $f(ptr: webrtc::ptr::Borrowed<AudioDeviceModuleHandle>, $($param: $arg_ty),*) -> $ret {
            if let Some(handle) = unsafe { ptr.as_ref() } {
                match handle.lock() {
                    #[allow(unused_mut)]  // Some functions require mut; others don't.
                    Ok(mut adm) => adm.$f($($param),*),
                    Err(e) =>  {
                        error!("Mutex was poisoned? {}", e);
                        InternalFailure::MutexPoison.into()
                    }
                }
            } else {
                error!("{} wrapper with null pointer", stringify!($f));
                InternalFailure::NullPtr.into()
            }
        }
        adm_wrapper!($($t)*);
    }
}

// Actual generation of C-interface functions.
all_adm_functions!(adm_wrapper);

/// Generator macro for the struct type of function pointers. A pointer to this
/// struct is passed to the C++ rffi, so it's vital that the generated struct match
/// the same order as the struct in the C++.
macro_rules! adm_struct_definition {
    (struct AudioDeviceCallbacks { $($inner:tt)* } => ) => {
        #[repr(C)]
        #[allow(non_snake_case)]
         pub struct AudioDeviceCallbacks {
            $($inner)*
         }
    };
    (struct AudioDeviceCallbacks { $($inner:tt)* } => $f:ident($($param:ident: $arg_ty:ty),*) -> $ret:ty ; $($t:tt)*) => {
        adm_struct_definition!(struct AudioDeviceCallbacks {
            $($inner)*
            pub $f: extern "C" fn(
              adm_borrowed: webrtc::ptr::Borrowed<AudioDeviceModuleHandle>, $($param: $arg_ty),*) -> $ret,
        } => $($t)*);
    };
    ($f:ident($($param:ident: $arg_ty:ty),*) -> $ret:ty ; $($t:tt)*) => {
        adm_struct_definition!(struct AudioDeviceCallbacks {
          pub $f: extern "C" fn(
              adm_borrowed: webrtc::ptr::Borrowed<AudioDeviceModuleHandle>, $($param: $arg_ty),*) -> $ret,
        } => $($t)*);
    }
}

all_adm_functions!(adm_struct_definition);

/// Generator macro for the instantiation of the function pointer struct.
macro_rules! adm_struct_instantiation {
    (AudioDeviceCallbacks { $($inner:tt)* } => ) => {
        const AUDIO_DEVICE_CBS: AudioDeviceCallbacks = AudioDeviceCallbacks {
            $($inner)*
        };
    };
    (AudioDeviceCallbacks { $($inner:tt)* } => $f:ident($($_args:tt)*) -> $_ret:ty ; $($t:tt)*) => {
        adm_struct_instantiation!(
            AudioDeviceCallbacks {
                $($inner)*
                $f: crate::webrtc::ffi::audio_device_module::$f,
            } => $($t)*
        );
    };
    ($f:ident($($_args:tt)*) -> $_ret:ty ; $($t:tt)*) => {
        adm_struct_instantiation!(
            AudioDeviceCallbacks {
                $f: crate::webrtc::ffi::audio_device_module::$f,
            } => $($t)*
        );
    }
}

all_adm_functions!(adm_struct_instantiation);
pub const AUDIO_DEVICE_CBS_PTR: *const AudioDeviceCallbacks = &AUDIO_DEVICE_CBS;

/// Safety: Must be called with the same pointer passed to the C++ layer when
/// constructing the PeerConnectionFactory.
///
/// The purpose of this function is to reclaim a pointer to the ADM that is
/// "leaked" to the C++ layer (via Arc::into_raw)
///
/// The C++ layer must only call this function when it is done using the ADM,
/// as this function could drop the ADM
pub unsafe extern "C" fn decrement_adm_ref_count(adm_borrowed: webrtc::ptr::Borrowed<c_void>) {
    // Don't try to convert null to an arc
    if adm_borrowed.is_null() {
        return;
    }
    // Get types right
    let adm_borrowed = adm_borrowed.as_ptr() as *const AudioDeviceModuleHandle;
    // Only used for decrementing the reference count.
    let _adm = unsafe { Arc::from_raw(adm_borrowed) };
}

#[cfg(test)]
mod audio_tap_callback_tests {
    use super::{audio_tap_is_active_impl, push_processed_local_audio_impl};
    use crate::audio_tap::AudioTap;

    #[test]
    fn callbacks_access_the_tap_without_an_adm_mutex() {
        let tap = AudioTap::new(8);
        assert!(!audio_tap_is_active_impl(&tap));

        tap.start();
        tap.set_local_input_enabled(true);
        let samples = [11, 12, 13, 14];
        assert!(push_processed_local_audio_impl(&tap, &samples));

        assert!(audio_tap_is_active_impl(&tap));
        assert_eq!(tap.drain(usize::MAX).local_input, samples);
    }
}

unsafe extern "C" {
    pub fn Rust_recordedDataIsAvailable(
        audio_samples: *const c_void,
        n_samples: size_t,
        n_bytes_per_sample: size_t,
        n_channels: size_t,
        samples_per_sec: u32,
        total_delay_ms: u32,
        clock_drift: i32,
        current_mic_level: u32,
        key_pressed: bool,
        new_mic_level: *mut u32,
        estimated_capture_time_ns: i64,
    ) -> i32;

    pub fn Rust_needMorePlayData(
        n_samples: size_t,
        n_bytes_per_sample: size_t,
        n_channels: size_t,
        samples_per_sec: u32,
        audio_samples: *mut c_void,
        n_samples_out: *mut size_t,
        elapsed_time_ms: *mut i64,
        ntp_time_ms: *mut i64,
    ) -> i32;
}
