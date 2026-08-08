//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const {
  installPrebuild,
  selectPrebuild,
} = require('./fetch-minutes-prebuild.js');

const PACKAGE = {
  name: '@minutes/ringrtc',
  version: '2.69.7-minutes.3',
  config: {
    upstreamVersion: '2.69.7',
    tapApiVersion: 1,
    releaseRepository: 'jiridudekusy/minutes-ringrtc',
  },
};

function manifestFor(bytes) {
  return {
    schemaVersion: 1,
    packageVersion: PACKAGE.version,
    upstreamVersion: PACKAGE.config.upstreamVersion,
    tapApiVersion: PACKAGE.config.tapApiVersion,
    targets: {
      'darwin-arm64': {
        asset: 'minutes-ringrtc-v2.69.7-minutes.3-darwin-arm64.node',
        sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
      },
    },
  };
}

void test('selects the Linux x64 addon used by Minutes desktop', () => {
  const bytes = Buffer.from('linux-native-addon');
  const manifest = manifestFor(bytes);
  manifest.targets['linux-x64'] = {
    asset: 'minutes-ringrtc-v2.69.7-minutes.3-linux-x64.node',
    sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
  };

  const selected = selectPrebuild(manifest, PACKAGE, {
    platform: 'linux',
    arch: 'x64',
  });

  assert.equal(selected.destination, 'build/linux/libringrtc-x64.node');
  assert.equal(
    selected.asset,
    'minutes-ringrtc-v2.69.7-minutes.3-linux-x64.node'
  );
});

void test('selects only a checksum-pinned Minutes GitHub release addon', () => {
  const bytes = Buffer.from('native-addon');

  const selected = selectPrebuild(manifestFor(bytes), PACKAGE, {
    platform: 'darwin',
    arch: 'arm64',
  });

  assert.deepEqual(selected, {
    asset: 'minutes-ringrtc-v2.69.7-minutes.3-darwin-arm64.node',
    sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    url: 'https://github.com/jiridudekusy/minutes-ringrtc/releases/download/v2.69.7-minutes.3/minutes-ringrtc-v2.69.7-minutes.3-darwin-arm64.node',
    destination: 'build/darwin/libringrtc-arm64.node',
  });
});

void test('installs a verified addon atomically and rejects a checksum mismatch', async () => {
  const packageRoot = await fs.mkdtemp(
    path.join(os.tmpdir(), 'minutes-ringrtc-install-')
  );
  try {
    const expectedBytes = Buffer.from('native-addon');
    const selected = selectPrebuild(manifestFor(expectedBytes), PACKAGE, {
      platform: 'darwin',
      arch: 'arm64',
    });

    await assert.rejects(
      installPrebuild(selected, packageRoot, async (_url, destination) => {
        await fs.writeFile(destination, Buffer.from('tampered'));
      }),
      /checksum mismatch/i
    );
    await assert.rejects(
      fs.stat(path.join(packageRoot, selected.destination)),
      /ENOENT/
    );

    await installPrebuild(selected, packageRoot, async (_url, destination) => {
      await fs.writeFile(destination, expectedBytes);
    });
    assert.deepEqual(
      await fs.readFile(path.join(packageRoot, selected.destination)),
      expectedBytes
    );
  } finally {
    await fs.rm(packageRoot, { recursive: true, force: true });
  }
});
