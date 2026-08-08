'use strict';

const drpys = require('./drpys-http-adapter.js');
const drpy2 = require('./drpy2-http-adapter.js');

function isDrpysEndpoint(rule) {
  try {
    const url = new URL(String(rule));
    return /\/api\/[^/]+$/u.test(url.pathname);
  } catch (_) {
    return false;
  }
}

function execute(request) {
  return isDrpysEndpoint(request && request.rule) ? drpys.execute(request) : drpy2.execute(request);
}

module.exports = {execute};
