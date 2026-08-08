'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const adapter = require('../drpy2/drpy2-http-adapter.js');

async function main() {
  const requests = [];
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    requests.push(url);
    res.setHeader('content-type', 'application/json');
    if (url.searchParams.has('wd')) {
      res.end(JSON.stringify({list: [{vod_id: 'vod-1', vod_name: '熊出没'}]}));
    } else if (url.searchParams.get('ac') === 'detail') {
      res.end(JSON.stringify({list: [{
        vod_id: url.searchParams.get('ids'),
        vod_name: '熊出没',
        vod_play_from: '直连$$$备用',
        vod_play_url: '第1集$media-one#第2集$media-two$$$正片$media-main',
      }]}));
    } else if (url.searchParams.has('play')) {
      res.end(JSON.stringify({parse: 0, url: `https://media.test/${url.searchParams.get('flag')}/${url.searchParams.get('play')}.m3u8`}));
    } else {
      res.statusCode = 400;
      res.end(JSON.stringify({error: 'unexpected request'}));
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const {port} = server.address();
  const rule = 'https://cdn.test/rules/kids.js';
  process.env.DRPY2_DR2_BASE_URL = `http://127.0.0.1:${port}`;
  process.env.DRPY2_DR2_PWD = 'secret';
  process.env.DRPY2_RULE_MAP_JSON = JSON.stringify({[rule]: {module: 'kids-reviewed-a1b2'}});
  try {
    const search = await adapter.execute({rule, action: 'search', params: {keyword: '熊出没'}});
    assert.equal(search.list[0].vod_id, 'vod-1');
    const detail = await adapter.execute({rule, action: 'detail', params: {id: 'vod-1'}});
    assert.equal(detail.vod_name, '熊出没');
    const episode = await adapter.execute({rule, action: 'episode', params: {id: 'vod-1'}});
    assert.equal(episode.list.length, 3);
    const play = await adapter.execute({rule, action: 'play', params: {flag: episode.list[0].flag}});
    assert.equal(play.url, 'https://media.test/直连/media-one.m3u8');
    assert.ok(requests.every(url => url.pathname === '/api/kids-reviewed-a1b2'));
    assert.ok(requests.every(url => url.searchParams.get('pwd') === 'secret'));
    assert.ok(requests.every(url => url.searchParams.get('adpt') === 'dr'));
    await assert.rejects(
      adapter.execute({rule: 'https://cdn.test/rules/unreviewed.js', action: 'search', params: {keyword: 'x'}}),
      /reviewed registry/u,
    );
    process.env.DRPY2_DR2_BASE_URL = 'https://runtime.example.net';
    await assert.rejects(
      adapter.execute({rule, action: 'search', params: {keyword: 'x'}}),
      /must be loopback/u,
    );
    console.log('drpy2-http-adapter: all integration assertions passed');
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
