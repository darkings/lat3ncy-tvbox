#!/usr/bin/env python3
import json

import pytest
from ponyo_source_manager.publishing import children_aggregate
from ponyo_source_manager.publishing.children_aggregate import (
    classify_children_content,
    is_safe_content,
    is_children_title,
    is_dedicated_kids_title,
    is_maccms_endpoint,
    is_playable_media_url,
    maccms_cache_id,
    maccms_play_fields,
    type_id_for_title,
    video_cache_id,
    dedupe_children_content,
    SEARCH_KEYWORDS_BY_CATEGORY,
    PREFERRED_RUNTIME_RULES,
    PLAYABLE_RUNTIME_RULES,
    EXCLUDED_RUNTIME_RULES,
    LIST_CLASSES_BY_RULE,
    MACCMS_KIDS_SOURCES,
)


def test_classify_children_content():
    assert classify_children_content("小猪佩奇第一季") == "学龄前"
    assert classify_children_content("熊出没之怪兽计划") == "国产动画"
    assert classify_children_content("猫和老鼠全集") == "经典动画"


def test_is_safe_content():
    assert is_safe_content("小猪佩奇") is True
    assert is_safe_content("成人午夜剧场") is False


def test_dedupe_children_content():
    items = [
        {"title": "小猪佩奇", "year": "2020", "season": "1", "source_fp": "fp1", "quality_score": 90, "play_url": "url1"},
        {"title": "小猪佩奇(第一季)", "year": "2020", "season": "1", "source_fp": "fp2", "quality_score": 95, "play_url": "url2"},
    ]
    deduped = dedupe_children_content(items)
    assert len(deduped) == 1
    assert deduped[0]["routes"][0]["source"] == "fp2"


def test_search_keywords_cover_all_categories():
    # 每个分类至少 2 个具象关键词，避免「每分类 1 词命中即停」导致只有十几条
    for cat, kws in SEARCH_KEYWORDS_BY_CATEGORY.items():
        assert len(kws) >= 2, cat
        assert all(kws), cat
    assert "动漫豆[漫]" in PREFERRED_RUNTIME_RULES
    assert "动漫豆[漫]" in PLAYABLE_RUNTIME_RULES
    assert "腾云驾雾[官]" in EXCLUDED_RUNTIME_RULES
    assert "优酷[官]" in EXCLUDED_RUNTIME_RULES
    assert LIST_CLASSES_BY_RULE["动漫豆[漫]"] == ["china", "cartoon", "occident"]


def test_is_children_title_keeps_kids_and_drops_xianxia():
    """整合源必须过滤修仙/解说，只留能给儿童看的 IP。"""
    assert is_children_title("汪汪队立大功第八季") is True
    assert is_children_title("熊出没之神奇宝物") is True
    assert is_children_title("小猪佩奇第十一季") is True
    assert is_children_title("哆啦A梦：大雄的绘画奇遇记") is True
    assert is_children_title("仙王的日常生活第五季") is False
    assert is_children_title("斗罗大陆2：绝世唐门") is False
    assert is_children_title("无数据,防无限请求") is False
    assert is_children_title("封号李长生") is False


def test_type_id_for_title_uses_source_class_fallback():
    # 学龄前
    assert type_id_for_title("汪汪队立大功") == "1"
    # 国产
    assert type_id_for_title("熊出没之年货") == "2"
    # 动漫豆 cartoon 分区、标题未命中细分类时归动画电影
    assert type_id_for_title("珍宝2025", "cartoon") == "5"


def test_search_collect_uses_all_keywords_and_fills_empty_title():
    """多关键词都要搜；搜索无标题时回源详情补齐（动漫豆场景）。"""
    calls = []

    def fake_search(api, kw):
        calls.append(("search", kw))
        if kw == "汪汪队":
            return {
                "success": 1,
                "items": [{"vod_id": "/show/a.html", "vod_name": "", "vod_pic": "p", "vod_remarks": "全26集"}],
            }
        if kw == "熊出没":
            return {
                "success": 1,
                "items": [{"vod_id": "/show/b.html", "vod_name": "熊出没之年货", "vod_pic": "p2", "vod_remarks": "HD"}],
            }
        return {"success": 1, "items": []}

    def fake_detail(api, vod_id):
        calls.append(("detail", vod_id))
        return {"success": 1, "detail": {"vod_name": "汪汪队立大功第八季"}}

    sources = [{
        "fingerprint": "runtime:动漫豆[漫]",
        "name": "动漫豆[漫]",
        "api": "http://ponyo-drpy-node:5757/api/动漫豆[漫]?pwd=x",
        "store_api": "http://ponyo-drpy-node:5757/api/动漫豆[漫]?pwd=x",
        "ext": "",
        "score": 100,
    }]
    items = []
    children_aggregate._search_collect(fake_search, sources, items, run_drpy_detail=fake_detail)

    titles = {x["title"] for x in items}
    assert "汪汪队立大功第八季" in titles
    assert "熊出没之年货" in titles
    assert ("detail", "/show/a.html") in calls
    # 每个分类的多个关键词都要被搜到，不能命中即停整个分类
    searched = [kw for kind, kw in calls if kind == "search"]
    assert "汪汪队" in searched
    assert "小猪佩奇" in searched
    assert "熊出没" in searched
    assert "猫和老鼠" in searched


def test_list_collect_pages_and_filters_non_kids(monkeypatch):
    """分类分页采集：翻页去重，丢掉修仙，保留儿童 IP。"""
    pages = {
        ("china", "1"): [
            {"vod_id": "china$/show/a.html", "vod_name": "汪汪队立大功第八季", "vod_pic": "p1", "vod_remarks": "全26集"},
            {"vod_id": "china$/show/x.html", "vod_name": "仙王的日常生活第五季", "vod_pic": "p2", "vod_remarks": "更新至10集"},
        ],
        ("china", "2"): [
            {"vod_id": "china$/show/b.html", "vod_name": "熊出没之年货", "vod_pic": "p3", "vod_remarks": "HD"},
            {"vod_id": "no_data", "vod_name": "无数据,防无限请求"},
        ],
        ("china", "3"): [
            {"vod_id": "no_data", "vod_name": "无数据,防无限请求"},
        ],
        ("cartoon", "1"): [
            {"vod_id": "cartoon$/show/c.html", "vod_name": "哆啦A梦：大雄的绘画奇遇记", "vod_pic": "p4", "vod_remarks": "HD"},
        ],
        ("cartoon", "2"): [
            {"vod_id": "no_data", "vod_name": "无数据,防无限请求"},
        ],
        ("occident", "1"): [
            {"vod_id": "occident$/show/d.html", "vod_name": "小猪佩奇第十一季", "vod_pic": "p5", "vod_remarks": "更新至12集"},
        ],
        ("occident", "2"): [
            {"vod_id": "no_data", "vod_name": "无数据,防无限请求"},
        ],
    }

    def fake_http(url, timeout=20):
        if "ac=list" in url or ("ac=" not in url and "t=" not in url):
            return {"class": [
                {"type_id": "china", "type_name": "国产动漫"},
                {"type_id": "cartoon", "type_name": "动漫电影"},
            ]}
        t = ""
        pg = "1"
        if "t=china" in url:
            t = "china"
        elif "t=cartoon" in url:
            t = "cartoon"
        elif "t=occident" in url:
            t = "occident"
        if "pg=2" in url:
            pg = "2"
        elif "pg=3" in url:
            pg = "3"
        return {"list": pages.get((t, pg), [])}

    monkeypatch.setattr(children_aggregate, "_http_json", fake_http)
    sources = [{
        "fingerprint": "runtime:动漫豆[漫]",
        "name": "动漫豆[漫]",
        "api": "http://ponyo-drpy-node:5757/api/动漫豆[漫]?pwd=x",
        "store_api": "http://ponyo-drpy-node:5757/api/动漫豆[漫]?pwd=x",
        "ext": "",
        "score": 100,
    }]
    items = []
    children_aggregate._list_collect(sources, items)
    titles = {x["title"] for x in items}
    assert "汪汪队立大功第八季" in titles
    assert "熊出没之年货" in titles
    assert "哆啦A梦：大雄的绘画奇遇记" in titles
    assert "小猪佩奇第十一季" in titles
    assert "仙王的日常生活第五季" not in titles
    assert all("无数据" not in x["title"] for x in items)


def test_dedicated_kids_title_allows_english_and_blocks_adult():
    """明确少儿分类允许英文儿歌，但仍拦截成人/擦边词。"""
    assert is_dedicated_kids_title("Dave_and_Ava Nursery Rhymes") is True
    assert is_dedicated_kids_title("Little Angel Kids Songs") is True
    assert is_dedicated_kids_title("Cocomelon ABC") is True
    assert is_dedicated_kids_title("自慰套教室女子全员妊娠计画") is False
    assert is_dedicated_kids_title("无数据,防无限请求") is False
    assert is_dedicated_kids_title("") is False
    # 普通动画分类仍必须命中中文 IP 白名单
    assert is_children_title("Dave_and_Ava Nursery Rhymes") is False
    assert is_children_title("仙王的日常生活第五季") is False


def test_maccms_kids_sources_exclude_miaobo_and_yutu():
    """秒播少儿/亲子为空、玉兔卡通动漫含成人内容，不得加入固定源。"""
    blobs = json.dumps(MACCMS_KIDS_SOURCES, ensure_ascii=False)
    assert "wujinapi.com" in blobs
    assert "suoniapi.com" in blobs
    assert "miaobo" not in blobs.lower()
    assert "秒播" not in blobs
    assert "yutu" not in blobs.lower()
    assert "玉兔" not in blobs
    fps = {s["fingerprint"] for s in MACCMS_KIDS_SOURCES}
    assert fps == {"maccms:api.wujinapi.com", "maccms:suoniapi.com"}


def test_maccms_cache_id_is_unique_per_endpoint():
    """不同 MacCMS endpoint 可能撞 vod_id，缓存主键必须带源指纹。"""
    a = maccms_cache_id("maccms:api.wujinapi.com", "100")
    b = maccms_cache_id("maccms:suoniapi.com", "100")
    assert a != b
    assert a == "maccms:api.wujinapi.com:100"
    item = {
        "kind": "maccms",
        "source_fp": "maccms:api.wujinapi.com",
        "vod_id": "100",
    }
    assert video_cache_id(item) == a
    # 写入缓存时 source_id 仍是原始 vod_id
    assert item["vod_id"] == "100"


def test_maccms_play_fields_keep_media_drop_web():
    """详情只保留真实媒体地址；网页/空地址不能出现在 vod_play_url。"""
    play_from, play_url = maccms_play_fields({
        "vod_play_from": "wjm3u8",
        "vod_play_url": "第1集$https://cdn.example.com/a.m3u8",
    })
    assert "a.m3u8" in play_url
    assert play_from == "wjm3u8"

    play_from, play_url = maccms_play_fields({
        "vod_play_from": "qq",
        "vod_play_url": "第1集$https://v.qq.com/x/cover/foo.html",
    })
    assert play_url == ""
    assert play_from == "儿童专线"
    assert "v.qq.com" not in play_url

    play_from, play_url = maccms_play_fields({
        "vod_play_from": "line",
        "vod_play_url": "第1集$",
    })
    assert play_url == ""

    mixed_from, mixed_url = maccms_play_fields({
        "vod_play_from": "web$$$m3u8",
        "vod_play_url": (
            "第1集$https://www.iqiyi.com/v_1.html"
            "$$$第1集$https://cdn.example.com/ok.m3u8"
        ),
    })
    # 网页线路整条丢弃，不生成假线路；下一条真实 m3u8 可以保留
    assert "iqiyi.com" not in mixed_url
    assert "ok.m3u8" in mixed_url
    assert mixed_from == "m3u8"
    assert is_playable_media_url("https://cdn.example.com/ok.m3u8") is True
    assert is_playable_media_url("https://v.qq.com/x/cover/foo.html") is False
    assert is_maccms_endpoint("https://api.wujinapi.com/api.php/provide/vod/", "maccms")
    assert not is_maccms_endpoint("http://ponyo-drpy-node:5757/api/动漫豆[漫]", "")


def test_maccms_list_collect_pages_english_and_filters_anime(monkeypatch):
    """MacCMS 分页：少儿分类收英文儿歌；普通动画分类仍走白名单。"""
    pages = {
        ("64", "1"): [
            {"vod_id": "1001", "vod_name": "Dave_and_Ava Nursery Rhymes", "vod_pic": "p1", "vod_remarks": "HD"},
            {"vod_id": "1002", "vod_name": "Little Angel Kids Songs", "vod_pic": "p2", "vod_remarks": "全10集"},
        ],
        ("64", "2"): [
            {"vod_id": "1003", "vod_name": "自慰套教室女子全员妊娠计画", "vod_pic": "p3", "vod_remarks": "HD"},
        ],
        ("64", "3"): [],
        ("29", "1"): [
            {"vod_id": "2001", "vod_name": "熊出没之年货", "vod_pic": "p4", "vod_remarks": "HD"},
            {"vod_id": "2002", "vod_name": "仙王的日常生活第五季", "vod_pic": "p5", "vod_remarks": "更新至10集"},
            {"vod_id": "2003", "vod_name": "Random English Cartoon", "vod_pic": "p6", "vod_remarks": "HD"},
        ],
        ("29", "2"): [],
    }

    def fake_http(url, timeout=20):
        if "ac=list" in url:
            return {"class": [
                {"type_id": "64", "type_name": "儿童儿歌"},
                {"type_id": "29", "type_name": "国产动漫"},
                {"type_id": "33", "type_name": "动画片"},
            ]}
        t = ""
        pg = "1"
        if "t=64" in url:
            t = "64"
        elif "t=29" in url:
            t = "29"
        if "pg=2" in url:
            pg = "2"
        elif "pg=3" in url:
            pg = "3"
        lst = pages.get((t, pg), [])
        return {"list": lst, "pagecount": 2}

    monkeypatch.setattr(children_aggregate, "_http_json", fake_http)
    sources = [{
        "name": "无尽资源",
        "fingerprint": "maccms:api.wujinapi.com",
        "api": "https://api.wujinapi.com/api.php/provide/vod/",
        "store_api": "https://api.wujinapi.com/api.php/provide/vod/",
        "ext": "maccms",
        "kind": "maccms",
        "score": 80,
        "kids_classes": ["64"],
        "anime_classes": ["29"],
    }]
    items = []
    children_aggregate._maccms_list_collect(sources, items)
    titles = {x["title"] for x in items}
    assert "Dave_and_Ava Nursery Rhymes" in titles
    assert "Little Angel Kids Songs" in titles
    assert "熊出没之年货" in titles
    assert "自慰套教室女子全员妊娠计画" not in titles
    assert "仙王的日常生活第五季" not in titles
    assert "Random English Cartoon" not in titles
    dave = next(x for x in items if x["title"].startswith("Dave_and_Ava"))
    assert dave["vod_id"] == "1001"
    assert dave["api"] == "https://api.wujinapi.com/api.php/provide/vod/"
    assert dave["kind"] == "maccms"
    assert "play_url" not in dave
    assert video_cache_id(dave) == "maccms:api.wujinapi.com:1001"


def test_populate_cache_keeps_old_rows_when_collect_empty(tmp_path, monkeypatch):
    """本次采集为空时不得 DELETE FROM videos，避免把已有动漫豆缓存清掉。"""
    cache_db = tmp_path / "children_cache.db"
    src_db = tmp_path / "sources.db"
    import sqlite3

    con = sqlite3.connect(cache_db)
    con.execute(
        "CREATE TABLE videos ("
        "id TEXT PRIMARY KEY, type_id TEXT, name TEXT, pic TEXT, latest TEXT, "
        "source_fp TEXT, source_id TEXT, api TEXT, ext TEXT)"
    )
    con.execute(
        "INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?)",
        ("old-1", "1", "汪汪队立大功", "", "", "runtime:动漫豆[漫]", "a", "http://x", ""),
    )
    con.commit()
    con.close()

    src = sqlite3.connect(src_db)
    src.executescript(
        """
        CREATE TABLE raw_source (id INTEGER PRIMARY KEY, api TEXT, ext TEXT);
        CREATE TABLE norm_source (raw_id INTEGER, fingerprint TEXT);
        INSERT INTO raw_source VALUES (1, 'csp_X', '');
        INSERT INTO norm_source VALUES (1, 'fp-0');
        """
    )
    src.commit()
    src.close()

    monkeypatch.setattr(children_aggregate, "DATA_DIR", tmp_path, raising=False)
    from ponyo_source_manager.core import common as common_mod

    monkeypatch.setattr(common_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(children_aggregate, "_runtime_fallback_rules", lambda: [])
    monkeypatch.setattr(children_aggregate, "_list_collect", lambda *a, **k: 0)
    monkeypatch.setattr(children_aggregate, "_search_collect", lambda *a, **k: 0)
    monkeypatch.setattr(children_aggregate, "_maccms_list_collect", lambda *a, **k: 0)

    children_aggregate._populate_cache_from_sources(
        str(src_db), [{"fingerprint": "fp-0", "name": "x", "score": 1}]
    )

    con = sqlite3.connect(cache_db)
    rows = con.execute("SELECT id, name FROM videos").fetchall()
    con.close()
    assert rows == [("old-1", "汪汪队立大功")]
