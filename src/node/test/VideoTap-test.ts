//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

import { expect } from 'chai';
import { RingRTC } from '../index';

describe('RingRTC video tap', () => {
  it('exposes a versioned latest-frame polling API', () => {
    expect(RingRTC.isVideoTapSupported()).to.equal(true);
    expect(RingRTC.videoTapVersion()).to.equal(1);

    RingRTC.startVideoTap();
    try {
      const event = RingRTC.readVideoTap(0);
      expect(event).not.to.equal(undefined);
      expect(event?.sequence).to.equal(1);
      expect(event?.timestampUs).to.be.at.least(0);
      expect(event?.active).to.equal(false);
      expect(RingRTC.readVideoTap(event?.sequence ?? 0)).to.equal(undefined);
    } finally {
      RingRTC.stopVideoTap();
    }
  });

  it('rejects a lastSequence that is not a JavaScript safe integer', () => {
    expect(() => RingRTC.readVideoTap(Number.MAX_SAFE_INTEGER + 1)).to.throw(
      RangeError,
      'lastSequence must be a finite non-negative integer'
    );
  });
});
