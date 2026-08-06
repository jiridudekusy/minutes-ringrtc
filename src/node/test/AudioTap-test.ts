//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

import { expect } from 'chai';
import { RingRTC } from '../index';

describe('RingRTC audio tap', () => {
  it('exposes a versioned capability check', () => {
    expect(RingRTC.isAudioTapSupported()).to.be.a('boolean');
    expect(RingRTC.audioTapVersion()).to.equal(1);
  });

  it('exposes bounded polling controls and PCM metadata', function () {
    // Headless hosts (notably GitHub's Windows runner) may not expose an
    // initializable audio device. The capability check is deliberately false
    // in that environment even though the native API itself is present.
    if (!RingRTC.isAudioTapSupported()) {
      this.skip();
    }

    RingRTC.startAudioTap();
    try {
      const chunk = RingRTC.readAudioTap(480);
      expect(chunk.sampleRate).to.equal(48_000);
      expect(chunk.channels).to.equal(1);
      expect(chunk.localInputStartSample).to.be.at.least(0);
      expect(chunk.remotePlayoutStartSample).to.be.at.least(0);
      expect(chunk.localInputPcm.byteLength % 2).to.equal(0);
      expect(chunk.remotePlayoutPcm.byteLength % 2).to.equal(0);
      expect(chunk.droppedLocalInputSamples).to.be.at.least(0);
      expect(chunk.droppedRemotePlayoutSamples).to.be.at.least(0);
    } finally {
      RingRTC.stopAudioTap();
    }
  });
});
