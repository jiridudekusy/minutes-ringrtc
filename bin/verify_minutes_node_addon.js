#!/usr/bin/env node

//
// Copyright 2026 Minutes contributors
// SPDX-License-Identifier: AGPL-3.0-only
//

const path = require('node:path');

function verifyAddon(addonPath, expectedVersion) {
  // oxlint-disable-next-line import/no-dynamic-require typescript/no-var-requires
  const addon = require(path.resolve(addonPath));
  const functions = [
    'cm_audioTapIsSupported',
    'cm_audioTapVersion',
    'cm_startAudioTap',
    'cm_readAudioTap',
    'cm_stopAudioTap',
  ];
  for (const name of functions) {
    if (typeof addon[name] !== 'function') {
      throw new Error(`missing native export ${name}`);
    }
  }
  const actualVersion = addon.cm_audioTapVersion();
  if (actualVersion !== expectedVersion) {
    throw new Error(
      `expected audio tap API version ${expectedVersion}, got ${actualVersion}`
    );
  }
}

if (require.main === module) {
  const [addonPath, version] = process.argv.slice(2);
  const expectedVersion = Number(version);
  try {
    if (!addonPath || !Number.isInteger(expectedVersion)) {
      throw new Error('usage: verify_minutes_node_addon.js ADDON VERSION');
    }
    verifyAddon(addonPath, expectedVersion);
  } catch (error) {
    console.error(`addon error: ${error.message}`);
    process.exitCode = 1;
  }
}

module.exports = { verifyAddon };
