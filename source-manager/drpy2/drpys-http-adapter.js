'use strict';

const DEFAULT_TIMEOUT_MS = 20000;

function requiredString(value, name) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function validateRule(rule) {
  const raw = requiredString(rule, 'rule');
  const url = new URL(raw);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('rule must be an HTTP(S) T4 endpoint');
  }
  if (!/\/api\/[^/]+$/u.test(url.pathname)) {
    throw new Error('rule must point to a drpy-node /api/:module endpoint');
  }
  if (/^(example\.(com|org|net)|localhost)$/iu.test(url.hostname)) {
    throw new Error('placeholder or untrusted rule host rejected');
  }
  return url;
}

function rejectPlaceholder(value, field = 'url') {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${field} is empty`);
  }
  const text = value.trim();
  if (/example\.(com|org|net)|mock\.m3u8|placeholder/iu.test(text)) {
    throw new Error(`${field} contains a placeholder`);
  }
  let parsed;
  try {
    parsed = new URL(text);
  } catch (_) {
    throw new Error(`${field} is not an absolute URL`);
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`${field} must use HTTP(S)`);
  }
  return text;
}

async function requestJson(rule, params) {
  const url = new URL(rule.toString());
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  const timeoutMs = Number.parseInt(process.env.DRPY2_TIMEOUT_MS || '', 10) || DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      headers: {accept: 'application/json', 'user-agent': 'ponyo-source-manager/1.0'},
      redirect: 'error',
      signal: controller.signal,
    });
  } catch (error) {
    if (error && error.name === 'AbortError') throw new Error(`T4 request timed out after ${timeoutMs}ms`);
    throw new Error(`T4 request failed: ${error.message}`);
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new Error(`T4 HTTP ${response.status}`);
  const body = await response.text();
  let data;
  try {
    data = JSON.parse(body);
  } catch (_) {
    throw new Error('T4 returned malformed JSON');
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('T4 returned a non-object response');
  if (data.error) throw new Error(`T4 error: ${String(data.error)}`);
  return data;
}

function firstVod(data) {
  const list = Array.isArray(data.list) ? data.list : [];
  if (!list.length || !list[0] || typeof list[0] !== 'object') throw new Error('T4 returned an empty video list');
  return list[0];
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
  const from = String(vod.vod_play_from || '').split('$$$');
  const groups = String(vod.vod_play_url || '').split('$$$');
  const episodes = [];
  groups.forEach((group, groupIndex) => {
    const line = (from[groupIndex] || `line-${groupIndex + 1}`).trim();
    group.split('#').forEach((entry, episodeIndex) => {
      const splitAt = entry.indexOf('$');
      const name = (splitAt >= 0 ? entry.slice(0, splitAt) : `episode-${episodeIndex + 1}`).trim();
      const play = (splitAt >= 0 ? entry.slice(splitAt + 1) : entry).trim();
      if (play) episodes.push({name, line, flag: encodeEpisode(line, play), url: encodeEpisode(line, play)});
    });
  });
  if (!episodes.length) throw new Error('T4 detail returned no episodes');
  return episodes;
}

async function execute(request) {
  if (!request || typeof request !== 'object') throw new Error('request must be an object');
  const rule = validateRule(request.rule);
  const params = request.params && typeof request.params === 'object' ? request.params : {};
  switch (request.action) {
    case 'search': {
      const data = await requestJson(rule, {wd: requiredString(params.keyword || params.wd, 'keyword')});
      if (!Array.isArray(data.list) || !data.list.length) throw new Error('T4 search returned an empty list');
      return data;
    }
    case 'detail': {
      const data = await requestJson(rule, {ac: 'detail', ids: requiredString(params.id || params.ids, 'id')});
      return firstVod(data);
    }
    case 'episode': {
      const data = await requestJson(rule, {ac: 'detail', ids: requiredString(params.id || params.ids, 'id')});
      return {list: parseEpisodes(firstVod(data))};
    }
    case 'play': {
      const episode = decodeEpisode(params.flag || params.url);
      const data = await requestJson(rule, {play: episode.play, flag: episode.flag});
      data.url = rejectPlaceholder(data.url || data.play_url, 'play URL');
      return data;
    }
    default:
      throw new Error(`unsupported action: ${String(request.action)}`);
  }
}

module.exports = {execute, parseEpisodes};
