//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

import { expect } from 'chai';
import { RingRTC } from '../index';

describe('RingRTC audio tap', () => {
  it('exposes bounded polling controls and PCM metadata', () => {
    expect(RingRTC.isAudioTapSupported()).to.equal(true);

    RingRTC.startAudioTap();
    try {
      const chunk = RingRTC.readAudioTap(480);
      expect(chunk.sampleRate).to.equal(48_000);
      expect(chunk.channels).to.equal(1);
      expect(chunk.localInputPcm.byteLength % 2).to.equal(0);
      expect(chunk.remotePlayoutPcm.byteLength % 2).to.equal(0);
      expect(chunk.droppedLocalInputSamples).to.be.at.least(0);
      expect(chunk.droppedRemotePlayoutSamples).to.be.at.least(0);
    } finally {
      RingRTC.stopAudioTap();
    }
  });
});
