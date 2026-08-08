#!/usr/bin/env node
'use strict';

const adapter = require('../drpy2/drpys-http-adapter.js');

const configUrl = process.env.DRPY2_CONFIG_URL ||
  'http://127.0.0.1:5757/config/1?pwd=ponyo-local-drpy';
const keywords = (process.env.DRPY2_VERIFY_KEYWORDS || '斗罗大陆,庆余年,凡人修仙传').split(',');

async function main() {
  const response = await fetch(configUrl, {redirect: 'error'});
  if (!response.ok) throw new Error(`config HTTP ${response.status}`);
  const config = await response.json();
  const sites = (config.sites || [])
    .filter(site => site.type === 4 && String(site.api || '').startsWith('http://127.0.0.1:5757/api/'))
    .sort((a, b) => {
      const useful = value => /影视|动漫|短剧|荐片|采集|网盘/u.test(String(value.name || '')) ? 0 : 1;
      return useful(a) - useful(b);
    });
  const errors = [];
  for (const site of sites) {
    for (const keyword of keywords) {
      try {
        const search = await adapter.execute({rule: site.api, action: 'search', params: {keyword}});
        const item = search.list[0];
        const id = item.vod_id || item.id;
        if (!id) throw new Error('search item has no id');
        const detail = await adapter.execute({rule: site.api, action: 'detail', params: {id}});
        const episode = await adapter.execute({rule: site.api, action: 'episode', params: {id}});
        const selected = episode.list[episode.list.length - 1];
        const play = await adapter.execute({rule: site.api, action: 'play', params: {flag: selected.flag}});
        if (process.env.DRPY2_REQUIRE_HLS === '1' && !String(play.url).toLowerCase().includes('.m3u8')) {
          throw new Error('play URL is real but is not HLS');
        }
        process.stdout.write(JSON.stringify({
          site: {key: site.key, name: site.name, api: site.api},
          keyword,
          item: {id, name: item.vod_name || item.name},
          detail: {name: detail.vod_name || detail.name},
          episode: {name: selected.name, line: selected.line, flag: selected.flag},
          play: {url: play.url, parse: play.parse, header: play.header || play.headers || {}},
        }) + '\n');
        return;
      } catch (error) {
        errors.push(`${site.name}/${keyword}: ${error.message}`);
      }
    }
  }
  throw new Error(`no complete real chain found (${errors.slice(-10).join(' | ')})`);
}

main().catch(error => {
  console.error(error.message);
  process.exit(1);
});
