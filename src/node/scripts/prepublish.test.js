//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const assert = require('node:assert/strict');
const test = require('node:test');

const { validatePrepublish } = require('./prepublish.js');

const PACKAGE = {
  name: '@minutes/ringrtc',
  version: '2.69.7-minutes.3',
  config: { upstreamVersion: '2.69.7', tapApiVersion: 1 },
};

function validManifest() {
  return {
    schemaVersion: 1,
    packageVersion: '2.69.7-minutes.3',
    upstreamVersion: '2.69.7',
    tapApiVersion: 1,
    targets: {
      'darwin-arm64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.3-darwin-arm64.node',
        sha256: 'a'.repeat(64),
      },
      'linux-x64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.3-linux-x64.node',
        sha256: 'c'.repeat(64),
      },
      'win32-x64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.3-win32-x64.node',
        sha256: 'b'.repeat(64),
      },
    },
  };
}

void test('prepublish requires every checksum-pinned tap API addon', () => {
  const manifest = validManifest();
  delete manifest.targets['linux-x64'];

  assert.throws(
    () => validatePrepublish(PACKAGE, manifest),
    /missing prebuild target linux-x64/
  );

  manifest.targets['linux-x64'] = validManifest().targets['linux-x64'];
  assert.doesNotThrow(() => validatePrepublish(PACKAGE, manifest));
});
