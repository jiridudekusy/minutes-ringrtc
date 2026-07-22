//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const PACKAGE_JSON = require('../package.json');
const PREBUILDS = require('../prebuilds.json');

const REQUIRED_TARGETS = ['darwin-arm64', 'win32-x64'];

function validatePrepublish(packageJson, manifest) {
  if (packageJson.name !== '@minutes/ringrtc') {
    throw new Error('package name must be @minutes/ringrtc');
  }
  if (
    manifest.schemaVersion !== 1 ||
    manifest.packageVersion !== packageJson.version ||
    manifest.upstreamVersion !== packageJson.config?.upstreamVersion ||
    manifest.tapApiVersion !== packageJson.config?.tapApiVersion
  ) {
    throw new Error('prebuild manifest does not match package metadata');
  }
  for (const targetId of REQUIRED_TARGETS) {
    const target = manifest.targets?.[targetId];
    if (!target) {
      throw new Error(`missing prebuild target ${targetId}`);
    }
    if (!/^[a-f0-9]{64}$/.test(target.sha256)) {
      throw new Error(`missing checksum for prebuild target ${targetId}`);
    }
    const expectedAsset = `minutes-ringrtc-v${packageJson.version}-${targetId}.node`;
    if (target.asset !== expectedAsset) {
      throw new Error(`unexpected release asset for ${targetId}`);
    }
  }
}

if (require.main === module) {
  validatePrepublish(PACKAGE_JSON, PREBUILDS);
}

module.exports = { validatePrepublish };
