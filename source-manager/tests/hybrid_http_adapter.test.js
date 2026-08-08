'use strict';

const assert = require('node:assert/strict');
const drpys = require('../drpy2/drpys-http-adapter.js');
const drpy2 = require('../drpy2/drpy2-http-adapter.js');

drpys.execute = async request => ({runtime: 'drpys', rule: request.rule});
drpy2.execute = async request => ({runtime: 'drpy2', rule: request.rule});
const adapter = require('../drpy2/hybrid-http-adapter.js');

async function main() {
  assert.equal((await adapter.execute({rule: 'http://127.0.0.1:5757/api/demo'})).runtime, 'drpys');
  assert.equal((await adapter.execute({rule: 'https://cdn.test/rules/demo.js'})).runtime, 'drpy2');
  console.log('hybrid-http-adapter: routing assertions passed');
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
