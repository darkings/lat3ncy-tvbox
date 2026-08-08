#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

function readRequest() {
  return new Promise((resolve, reject) => {
    let input = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => { input += chunk; });
    process.stdin.on('end', () => {
      try { resolve(JSON.parse(input)); }
      catch (error) { reject(new Error(`invalid JSON request: ${error.message}`)); }
    });
    process.stdin.on('error', reject);
  });
}

async function main() {
  const adapterSetting = process.env.DRPY2_ADAPTER;
  if (!adapterSetting) {
    throw new Error('DRPY2_ADAPTER is not configured; refusing to use a mock playback engine');
  }
  const adapterPath = path.isAbsolute(adapterSetting)
    ? adapterSetting : path.resolve(process.cwd(), adapterSetting);
  if (!fs.existsSync(adapterPath)) {
    throw new Error(`DRPY2_ADAPTER does not exist: ${adapterPath}`);
  }
  if (path.resolve(adapterPath) === path.resolve(__filename)) {
    throw new Error('DRPY2_ADAPTER must not point to the bridge itself');
  }
  const adapter = require(adapterPath);
  const execute = typeof adapter === 'function' ? adapter : adapter.execute;
  if (typeof execute !== 'function') {
    throw new Error('DRPY2_ADAPTER must export a function or execute(request)');
  }
  const request = await readRequest();
  const response = await execute(request);
  if (!response || typeof response !== 'object') {
    throw new Error('DRPY2_ADAPTER returned a non-object response');
  }
  process.stdout.write(`${JSON.stringify(response)}\n`);
}

main().catch(error => {
  process.stderr.write(`drpy2 runner error: ${error.message}\n`);
  process.exit(2);
});
