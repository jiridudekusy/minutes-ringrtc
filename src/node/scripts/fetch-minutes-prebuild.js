//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const crypto = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');
const { pipeline } = require('node:stream/promises');
const { HttpsProxyAgent } = require('https-proxy-agent');
const PACKAGE_JSON = require('../package.json');
const PREBUILDS = require('../prebuilds.json');

const SUPPORTED_TARGETS = new Map([
  ['darwin-arm64', 'build/darwin/libringrtc-arm64.node'],
  ['win32-x64', 'build/win32/libringrtc-x64.node'],
]);

function selectPrebuild(manifest, packageJson, runtime = process) {
  if (
    packageJson.name !== '@minutes/ringrtc' ||
    manifest.schemaVersion !== 1 ||
    manifest.packageVersion !== packageJson.version ||
    manifest.upstreamVersion !== packageJson.config?.upstreamVersion ||
    manifest.tapApiVersion !== packageJson.config?.tapApiVersion
  ) {
    throw new Error('Minutes RingRTC prebuild manifest is incompatible');
  }

  const targetId = `${runtime.platform}-${runtime.arch}`;
  const destination = SUPPORTED_TARGETS.get(targetId);
  const target = manifest.targets?.[targetId];
  if (!destination || !target) {
    throw new Error(`Unsupported Minutes RingRTC target: ${targetId}`);
  }
  if (!/^[a-f0-9]{64}$/.test(target.sha256)) {
    throw new Error(`Missing checksum for Minutes RingRTC target: ${targetId}`);
  }
  const expectedAsset =
    `minutes-ringrtc-v${packageJson.version}-${runtime.platform}-` +
    `${runtime.arch}.node`;
  if (target.asset !== expectedAsset) {
    throw new Error(
      `Unexpected Minutes RingRTC release asset: ${target.asset}`
    );
  }

  const repository = packageJson.config.releaseRepository;
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    throw new Error('Invalid Minutes RingRTC release repository');
  }
  return {
    asset: target.asset,
    sha256: target.sha256,
    url:
      `https://github.com/${repository}/releases/download/` +
      `v${packageJson.version}/${target.asset}`,
    destination,
  };
}

async function sha256(file) {
  const hash = crypto.createHash('sha256');
  await pipeline(fs.createReadStream(file), hash);
  return hash.digest('hex');
}

function downloadTo(url, destination, redirectsRemaining = 5) {
  return new Promise((resolve, reject) => {
    const options = {};
    if (process.env.HTTPS_PROXY != null) {
      options.agent = new HttpsProxyAgent(process.env.HTTPS_PROXY);
    }
    https
      .get(url, options, response => {
        const location = response.headers.location;
        if (
          response.statusCode != null &&
          response.statusCode >= 300 &&
          response.statusCode < 400 &&
          location
        ) {
          response.resume();
          if (redirectsRemaining === 0) {
            reject(new Error('Too many Minutes RingRTC download redirects'));
            return;
          }
          resolve(
            downloadTo(
              new URL(location, url).toString(),
              destination,
              redirectsRemaining - 1
            )
          );
          return;
        }
        if (response.statusCode !== 200) {
          response.resume();
          reject(
            new Error(
              `Minutes RingRTC download failed with HTTP ${response.statusCode}`
            )
          );
          return;
        }
        resolve(pipeline(response, fs.createWriteStream(destination)));
      })
      .on('error', reject);
  });
}

async function installPrebuild(selected, packageRoot, download = downloadTo) {
  const destination = path.join(packageRoot, selected.destination);
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.${process.pid}.tmp`;
  try {
    await download(selected.url, temporary);
    const actualChecksum = await sha256(temporary);
    if (actualChecksum !== selected.sha256) {
      throw new Error(
        `Minutes RingRTC checksum mismatch: expected ${selected.sha256}, ` +
          `got ${actualChecksum}`
      );
    }
    await fsp.rename(temporary, destination);
  } finally {
    await fsp.rm(temporary, { force: true });
  }
}

async function main() {
  const packageRoot = path.resolve(__dirname, '..');
  const selected = selectPrebuild(PREBUILDS, PACKAGE_JSON, {
    platform: os.platform(),
    arch: os.arch(),
  });
  console.log(`downloading ${selected.url}`);
  await installPrebuild(selected, packageRoot);
}

module.exports = { downloadTo, installPrebuild, selectPrebuild, sha256 };

if (require.main === module) {
  main().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
