//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const assert = require('node:assert/strict');
const test = require('node:test');

const { validatePrepublish } = require('./prepublish.js');

const PACKAGE = {
  name: '@minutes/ringrtc',
  version: '2.69.7-minutes.1',
  config: { upstreamVersion: '2.69.7', tapApiVersion: 1 },
};

function validManifest() {
  return {
    schemaVersion: 1,
    packageVersion: '2.69.7-minutes.1',
    upstreamVersion: '2.69.7',
    tapApiVersion: 1,
    targets: {
      'darwin-arm64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.1-darwin-arm64.node',
        sha256: 'a'.repeat(64),
      },
      'win32-x64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.1-win32-x64.node',
        sha256: 'b'.repeat(64),
      },
    },
  };
}

void test('prepublish requires both checksum-pinned tap API addons', () => {
  const manifest = validManifest();
  delete manifest.targets['win32-x64'];

  assert.throws(
    () => validatePrepublish(PACKAGE, manifest),
    /missing prebuild target win32-x64/
  );

  manifest.targets['win32-x64'] = validManifest().targets['win32-x64'];
  assert.doesNotThrow(() => validatePrepublish(PACKAGE, manifest));
});
