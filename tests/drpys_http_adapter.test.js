'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const adapter = require('../drpy2/drpys-http-adapter.js');

async function main() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    res.setHeader('content-type', 'application/json');
    if (url.searchParams.has('wd')) {
      res.end(JSON.stringify({list: [{vod_id: 'vod-1', vod_name: '真实搜索结果'}]}));
    } else if (url.searchParams.get('ac') === 'detail') {
      res.end(JSON.stringify({list: [{
        vod_id: url.searchParams.get('ids'),
        vod_name: '真实详情',
        vod_play_from: '线路A$$$线路B',
        vod_play_url: '第1集$media-one#第2集$media-two$$$正片$media-main',
      }]}));
    } else if (url.searchParams.has('play')) {
      res.end(JSON.stringify({
        parse: 0,
        url: `http://media.test/${url.searchParams.get('flag')}/${url.searchParams.get('play')}.m3u8`,
        header: {Referer: 'http://media.test/'},
      }));
    } else {
      res.statusCode = 400;
      res.end(JSON.stringify({error: 'unexpected request'}));
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const {port} = server.address();
  const rule = `http://127.0.0.1:${port}/api/real-module`;
  try {
    const search = await adapter.execute({rule, action: 'search', params: {keyword: '测试'}});
    assert.equal(search.list[0].vod_id, 'vod-1');
    const detail = await adapter.execute({rule, action: 'detail', params: {id: 'vod-1'}});
    assert.equal(detail.vod_name, '真实详情');
    const episode = await adapter.execute({rule, action: 'episode', params: {id: 'vod-1'}});
    assert.equal(episode.list.length, 3);
    const play = await adapter.execute({rule, action: 'play', params: {flag: episode.list[0].flag}});
    assert.equal(play.url, 'http://media.test/线路A/media-one.m3u8');
    assert.equal(play.header.Referer, 'http://media.test/');
    await assert.rejects(
      () => adapter.execute({rule: 'http://example.com/api/mock', action: 'search', params: {keyword: 'x'}}),
      /placeholder|untrusted/
    );
    console.log('drpys-http-adapter: all integration assertions passed');
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
