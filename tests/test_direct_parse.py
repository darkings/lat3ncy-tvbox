#!/usr/bin/env python3
"""直连解析：预告/花絮/解说必须让路给正片，且跨源按分数全局排序。"""
from __future__ import annotations

import asyncio

from ponyo_source_manager.api import direct_parse as dp


def _vod(name, *, vod_id="1", type_name="", vod_class="", vod_remarks=""):
    """构造采集站条目，字段与苹果 CMS 搜索/详情返回对齐。"""
    return {
        "vod_id": vod_id,
        "vod_name": name,
        "type_name": type_name,
        "vod_class": vod_class,
        "vod_remarks": vod_remarks,
    }


def test_non_feature_detects_name_type_and_remarks():
    """片名、类型、分类、备注任一命中关键词都应视为非正片。"""
    title = "出入平安"
    assert dp.is_non_feature(_vod("出入平安[预告片]"), title) is True
    assert dp.is_non_feature(_vod("出入平安", type_name="预告片"), title) is True
    assert dp.is_non_feature(_vod("出入平安", vod_class="花絮"), title) is True
    assert dp.is_non_feature(_vod("出入平安", vod_remarks="片花"), title) is True
    assert dp.is_non_feature(_vod("出入平安[电影解说]"), title) is True
    assert dp.is_non_feature(_vod("出入平安 MV"), title) is True
    assert dp.is_non_feature(_vod("出入平安"), title) is False
    assert dp.is_non_feature(_vod("出入平安 HD国语"), title) is False


def test_non_feature_allows_explicit_trailer_request():
    """用户请求本身带预告词时，不过滤，避免搜不到预告。"""
    vod = _vod("出入平安[预告片]", type_name="预告片")
    assert dp.is_non_feature(vod, "出入平安[预告片]") is False
    assert dp.is_non_feature(vod, "出入平安 预告") is False


def test_candidate_score_zeros_trailer_and_keeps_feature():
    """预告前缀匹配必须清零；精确正片仍是 4.0。"""
    title = "出入平安"
    assert dp._candidate_score(_vod("出入平安[预告片]"), title) == 0
    assert dp._candidate_score(_vod("出入平安[电影解说]"), title) == 0
    assert dp._candidate_score(_vod("出入平安"), title) == 4.0
    assert dp._candidate_score(_vod("出入平安 HD国语"), title) == 3.0


def test_collect_ranked_skips_lz_trailer_and_prefers_exact_feature():
    """复现《出入平安》：量子预告不能压过非凡/暴风正片。"""
    lz, ff, bf, wl = dp.DIRECT_SOURCES
    results = [
        [_vod("出入平安[预告片]", vod_id="lz-trailer", type_name="预告片")],
        [_vod("出入平安", vod_id="ff-feature")],
        [
            _vod("出入平安", vod_id="bf-feature"),
            _vod("出入平安[电影解说]", vod_id="bf-recap"),
        ],
        [],
    ]
    ranked = dp._collect_ranked("出入平安", results, 2.0)
    ids = [vod["vod_id"] for vod, _src in ranked]
    # 预告/解说被清零，不进候选
    assert "lz-trailer" not in ids
    assert "bf-recap" not in ids
    # 精确正片按源优先级：非凡(1) 先于 暴风(2)
    assert ids == ["ff-feature", "bf-feature"]
    assert ranked[0][1] is ff
    assert ranked[1][1] is bf
    # 四个源对象都引用过，避免误删白名单
    assert lz["name"] == "lzm3u8" and wl["name"] == "wlm3u8"


def test_collect_ranked_prefers_exact_over_prefix_across_sources():
    """跨源必须按分数全局排序：后出现的精确命中也要压过先出现的前缀命中。"""
    results = [
        [_vod("狂飙 第二部", vod_id="lz-prefix")],
        [_vod("狂飙", vod_id="ff-exact")],
        [],
        [],
    ]
    ranked = dp._collect_ranked("狂飙", results, 2.0)
    assert [vod["vod_id"] for vod, _src in ranked] == ["ff-exact", "lz-prefix"]


def test_try_ranked_skips_trailer_revealed_only_in_detail(monkeypatch):
    """搜索列表看不出预告、详情 type_name 才标预告片时，也应跳过改试下一条。"""
    src = dp.DIRECT_SOURCES[0]
    trailer = _vod("出入平安", vod_id="1")
    feature = _vod("出入平安", vod_id="2")
    ranked = [(trailer, src), (feature, src)]

    async def fake_detail(_client, _api, vod_id):
        if str(vod_id) == "1":
            return {
                "vod_id": "1",
                "vod_name": "出入平安",
                "type_name": "预告片",
                "vod_play_url": "正片$https://cdn.test/trailer.m3u8",
            }
        return {
            "vod_id": "2",
            "vod_name": "出入平安",
            "type_name": "剧情片",
            "vod_play_url": "正片$https://cdn.test/feature.m3u8",
        }

    async def fake_share(_client, url):
        # 已经是 m3u8 直链，原样返回，模拟 resolve_share_link 快路径
        return url

    monkeypatch.setattr(dp, "fetch_detail", fake_detail)
    monkeypatch.setattr(dp, "resolve_share_link", fake_share)
    hit = asyncio.run(dp._try_ranked(None, ranked, None, title="出入平安"))
    assert hit["url"] == "https://cdn.test/feature.m3u8"
    assert hit["jxFrom"] == "direct:lzm3u8"
    assert hit["parse"] == 0


def test_language_and_season_scoring_still_work():
    """预告过滤不能破坏语言感知和季数系列匹配。"""
    title = "小猪佩奇 第12季[普通话版]"
    mandarin = _vod("小猪佩奇 第12季[普通话版]")
    cantonese = _vod("小猪佩奇 第12季[粤语版]")
    assert dp._candidate_score(mandarin, title) == 4.5
    assert dp._candidate_score(cantonese, title) == 2.0
    # 系列名是前缀命中 3.0；请求带季数时不同季走 R2 系列档 1.0
    other_season = _vod("小猪佩奇第九季")
    assert dp._candidate_score(other_season, "小猪佩奇") == 3.0
    assert dp._candidate_score(other_season, "小猪佩奇 第12季") == 1.0
