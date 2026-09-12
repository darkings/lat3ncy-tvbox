# -*- coding: utf-8 -*-
"""首页源策略：剔除坏 CMS/TG搜，注入 ryzy.tv，保留独立樱花动漫 Spider。"""

from ponyo_source_manager.publishing.generate_subscription import (
    _apply_home_source_policy,
)


def test_drops_tg_search_and_broken_hosts_then_injects_ryzy():
    sites = [
        {
            "key": "drpyS_TG搜[搜]",
            "name": "TG搜",
            "type": 4,
            "api": "http://127.0.0.1:5757/api/TG搜[搜]?pwd=ponyo-local-drpy",
        },
        {
            "key": "yhzy.cc",
            "name": "樱花资源2",
            "type": 0,
            "api": "https://yhzy.cc/api.php/provide/vod/",
        },
        {
            "key": "yinghua",
            "name": "樱花",
            "type": 1,
            "api": "https://api.apiyhzy.com/api.php/provide/vod",
        },
        {
            "key": "yinghua2",
            "name": "樱花",
            "type": 1,
            "api": "https://m3u8.apiyhzy.com/api.php/provide/vod/",
        },
        {
            "key": "如意资源",
            "name": "如意",
            "type": 0,
            "api": "https://cj.rycjapi.com/api.php/provide/vod/?ac=list",
        },
        {
            "key": "keep-me",
            "name": "暴风",
            "type": 1,
            "api": "https://bfzyapi.com/api.php/provide/vod/",
        },
        {
            "key": "drpyS_樱花动漫[优]",
            "name": "樱花动漫",
            "type": 4,
            "api": "http://127.0.0.1:5757/api/樱花动漫[优]?pwd=ponyo-local-drpy",
        },
        {
            "key": "csp_Ying",
            "name": "樱花-动漫",
            "type": 3,
            "api": "csp_Ying",
        },
    ]

    result = _apply_home_source_policy(sites)
    keys = [s.get("key") for s in result]
    apis = [str(s.get("api", "")) for s in result]

    assert "drpyS_TG搜[搜]" not in keys
    assert all("yhzy.cc" not in api for api in apis)
    assert all("api.apiyhzy.com" not in api for api in apis)
    assert all("m3u8.apiyhzy.com" not in api for api in apis)
    assert all("rycjapi.com" not in api for api in apis)
    assert "drpyS_樱花动漫[优]" in keys
    assert "csp_Ying" in keys
    assert "keep-me" in keys
    assert any("ryzy.tv" in api for api in apis)
    assert "php_如意资源" in keys


def test_keeps_existing_ryzy_and_respects_max_count_without_dropping_protected():
    sites = [
        {
            "key": "php_如意资源",
            "name": "如意",
            "type": 1,
            "api": "https://ryzy.tv/api.php/provide/vod/from/rym3u8/",
        },
        {"key": "a", "name": "A", "api": "https://a.example/api"},
        {"key": "b", "name": "B", "api": "https://b.example/api"},
        {"key": "csp_Ying", "name": "樱花-动漫", "type": 3, "api": "csp_Ying"},
        {
            "key": "drpyS_樱花动漫[优]",
            "name": "樱花动漫",
            "type": 4,
            "api": "http://127.0.0.1:5757/api/樱花动漫[优]",
        },
        {"key": "c", "name": "C", "api": "https://c.example/api"},
    ]

    result = _apply_home_source_policy(sites, max_count=4)
    keys = [s.get("key") for s in result]
    assert keys.count("php_如意资源") == 1
    assert "csp_Ying" in keys
    assert "drpyS_樱花动漫[优]" in keys
    assert len(result) == 4
