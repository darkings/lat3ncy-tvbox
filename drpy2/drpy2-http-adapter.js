'use strict';

const fs = require('node:fs');

const DEFAULT_TIMEOUT_MS = 20000;
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

function requiredString(value, name) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${name} must be non-empty string`);
  }
  return value.trim();
}

function normalizeRule(value) {
  const raw = requiredString(value, 'rule');
  const url = new URL(raw);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('drpy2 rule must use HTTP(S)');
  }
  if (url.username || url.password) throw new Error('drpy2 rule URL credentials rejected');
  if (/^(example\.(com|org|net)|localhost)$/iu.test(url.hostname)) {
    throw new Error('placeholder or local drpy2 rule rejected');
  }
  url.hash = '';
  return url.toString();
}

function parseRegistry() {
  let raw = process.env.DRPY2_RULE_MAP_JSON;
  if (!raw) {
    const file = requiredString(process.env.DRPY2_RULE_MAP_FILE, 'DRPY2_RULE_MAP_FILE');
    raw = fs.readFileSync(file, 'utf8');
  }
  let registry;
  try {
    registry = JSON.parse(raw);
  } catch (error) {
    throw new Error(`invalid drpy2 rule registry JSON: ${error.message}`);
  }
  if (!registry || Array.isArray(registry) || typeof registry !== 'object') {
    throw new Error('drpy2 rule registry must be an object');
  }
  return registry.rules && typeof registry.rules === 'object' ? registry.rules : registry;
}

function resolveModule(rule) {
  const normalized = normalizeRule(rule);
  const registry = parseRegistry();
  const entry = registry[normalized] ?? registry[rule];
  if (!entry) throw new Error('drpy2 rule is not present in reviewed registry');
  const moduleName = requiredString(typeof entry === 'string' ? entry : entry.module, 'module');
  if (moduleName === '.' || moduleName === '..' || /[\\/?#%\x00-\x1f]/u.test(moduleName)) {
    throw new Error('invalid drpy2 runtime module name');
  }
  return moduleName.replace(/\.js$/iu, '');
}

function runtimeEndpoint(moduleName) {
  const base = new URL(process.env.DRPY2_DR2_BASE_URL || 'http://127.0.0.1:5758');
  if (!['http:', 'https:'].includes(base.protocol)) throw new Error('invalid drpy2 runtime protocol');
  if (process.env.DRPY2_ALLOW_REMOTE_RUNTIME !== '1' && !LOOPBACK_HOSTS.has(base.hostname)) {
    throw new Error('drpy2 runtime must be loopback');
  }
  base.pathname = `${base.pathname.replace(/\/$/u, '')}/api/${encodeURIComponent(moduleName)}`;
  base.search = '';
  base.hash = '';
  return base;
}

function rejectPlaceholder(value, field = 'url') {
  const text = requiredString(value, field);
  if (/example\.(com|org|net)|mock\.m3u8|placeholder/iu.test(text)) {
    throw new Error(`${field} contains placeholder`);
  }
  let parsed;
  try {
    parsed = new URL(text);
  } catch (_) {
    throw new Error(`${field} not an absolute URL`);
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error(`${field} must use HTTP(S)`);
  return text;
}

async function requestJson(endpoint, params) {
  const url = new URL(endpoint.toString());
  url.searchParams.set('pwd', requiredString(process.env.DRPY2_DR2_PWD, 'DRPY2_DR2_PWD'));
  url.searchParams.set('adpt', 'dr');
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  }
  const timeoutMs = Number.parseInt(process.env.DRPY2_TIMEOUT_MS || '', 10) || DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      headers: {'accept': 'application/json', 'user-agent': 'ponyo-source-manager/1.0'},
      redirect: 'error',
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') throw new Error(`drpy2 runtime timeout after ${timeoutMs}ms`);
    throw new Error(`drpy2 runtime request failed: ${error.message}`);
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new Error(`drpy2 runtime HTTP ${response.status}`);
  const body = await response.text();
  let data;
  try {
    data = JSON.parse(body);
  } catch (_) {
    throw new Error('drpy2 runtime returned invalid JSON');
  }
  if (!data || Array.isArray(data) || typeof data !== 'object') {
    throw new Error('drpy2 runtime returned non-object JSON');
  }
  if (data.error) throw new Error(`drpy2 runtime error: ${String(data.error)}`);
  return data;
}

function firstVod(data, action) {
  if (!Array.isArray(data.list) || !data.list.length || !data.list[0] || typeof data.list[0] !== 'object') {
    throw new Error(`drpy2 ${action} returned an empty list`);
  }
  return data.list[0];
}

function encodeEpisode(flag, play) {
  return Buffer.from(JSON.stringify({flag, play}), 'utf8').toString('base64url');
}

function decodeEpisode(token) {
  try {
    const value = JSON.parse(Buffer.from(requiredString(token, 'episode token'), 'base64url').toString('utf8'));
    return {flag: requiredString(value.flag, 'episode flag'), play: requiredString(value.play, 'episode play id')};
  } catch (error) {
    throw new Error(`invalid episode token: ${error.message}`);
  }
}

function parseEpisodes(vod) {
  const lines = String(vod.vod_play_from || '').split('$$$');
  const groups = String(vod.vod_play_url || '').split('$$$');
  const episodes = [];
  groups.forEach((group, groupIndex) => {
    const line = (lines[groupIndex] || `line-${groupIndex + 1}`).trim();
    group.split('#').forEach((entry, episodeIndex) => {
      const splitAt = entry.indexOf('$');
      const name = (splitAt >= 0 ? entry.slice(0, splitAt) : `episode-${episodeIndex + 1}`).trim();
      const play = (splitAt >= 0 ? entry.slice(splitAt + 1) : entry).trim();
      if (play) {
        const token = encodeEpisode(line, play);
        episodes.push({name, line, flag: token, url: token});
      }
    });
  });
  if (!episodes.length) throw new Error('drpy2 detail returned no episodes');
  return episodes;
}

async function execute(request) {
  if (!request || typeof request !== 'object') throw new Error('request must be an object');
  const endpoint = runtimeEndpoint(resolveModule(request.rule));
  const params = request.params && typeof request.params === 'object' ? request.params : {};
  switch (request.action) {
    case 'search': {
      const data = await requestJson(endpoint, {wd: requiredString(params.keyword || params.wd, 'keyword'), pg: params.pg || 1});
      if (!Array.isArray(data.list) || !data.list.length) throw new Error('drpy2 search returned an empty list');
      return data;
    }
    case 'detail': {
      const data = await requestJson(endpoint, {ac: 'detail', ids: requiredString(params.id || params.ids, 'id')});
      return firstVod(data, 'detail');
    }
    case 'episode': {
      const data = await requestJson(endpoint, {ac: 'detail', ids: requiredString(params.id || params.ids, 'id')});
      return {list: parseEpisodes(firstVod(data, 'detail'))};
    }
    case 'play': {
      const episode = decodeEpisode(params.flag || params.url);
      const data = await requestJson(endpoint, {play: episode.play, flag: episode.flag});
      data.url = rejectPlaceholder(data.url || data.play_url, 'play URL');
      return data;
    }
    default:
      throw new Error(`unsupported drpy2 action: ${String(request.action)}`);
  }
}

module.exports = {execute};
