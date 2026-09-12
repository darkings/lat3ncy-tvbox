import json
import sqlite3

from ponyo_source_manager.probes import live


def test_parse_live_channels_normalizes_cctv_names():
    content = """#EXTM3U
#EXTINF:-1 group-title="央视",CCTV1综合
http://media.invalid/cctv1.m3u8
#EXTINF:-1,CCTV-5高清
http://media.invalid/cctv5.m3u8
#EXTINF:-1,CCTV6电影
http://media.invalid/cctv6.m3u8
"""
    channels = live.parse_live_channels(content)
    assert channels["CCTV1"] == "http://media.invalid/cctv1.m3u8"
    assert channels["CCTV5"] == "http://media.invalid/cctv5.m3u8"
    assert channels["CCTV6"] == "http://media.invalid/cctv6.m3u8"


def test_parse_live_channels_ignores_m3u_attribute_lines():
    content = """#EXTM3U
#EXTINF:-1,CCTV1
http-user-agent=AptvPlayer-UA
http://media.invalid/cctv1.m3u8
"""
    channels = live.parse_live_channels(content)
    assert channels["CCTV1"] == "http://media.invalid/cctv1.m3u8"


def test_parse_live_channels_keeps_first_route_for_duplicate_channel():
    content = """#EXTM3U
#EXTINF:-1,CCTV1综合
http://media.invalid/primary.m3u8
#EXTINF:-1,CCTV-1高清
http://media.invalid/backup.m3u8
"""
    channels = live.parse_live_channels(content)
    assert channels["CCTV1"] == "http://media.invalid/primary.m3u8"


def test_load_configured_live_candidates(tmp_path):
    path = tmp_path / "live_candidates.json"
    path.write_text(json.dumps([
        {"key": "a", "url": "https://example.invalid/a.m3u", "enabled": True},
        {"key": "b", "url": "https://example.invalid/b.m3u", "enabled": False},
    ]), encoding="utf-8")
    assert [item["key"] for item in live.load_configured_live_candidates(path)] == ["a"]


def test_failed_live_candidates_never_become_official(tmp_path, monkeypatch):
    db = tmp_path / "sources.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE raw_source (
            id INTEGER PRIMARY KEY, site_key TEXT, name TEXT, api TEXT, ext TEXT
        );
        CREATE TABLE norm_source (raw_id INTEGER, fingerprint TEXT, category TEXT);
        CREATE TABLE list_state (fingerprint TEXT, state TEXT);
    """)
    con.close()

    monkeypatch.setattr(live, "load_configured_live_candidates", lambda: [
        {"key": "failed", "name": "失败直播", "url": "https://example.invalid/live.m3u"}
    ])
    monkeypatch.setattr(live, "evaluate_live_source", lambda key, url, channels: {
        "key": key,
        "url": url,
        "total_score": 99.0,
        "validity_rate": 0.0,
        "avg_latency_ms": 9999,
        "hard_pass": False,
        "probed_channels": [],
    })

    result = live.select_official_live_source(str(db))
    assert result["official_key"] is None
    assert result["official_url"] is None


def test_parse_live_channels_deduplicates_by_normalized_name():
    """任务5：归一化后去重——同一频道只保留第一条线路"""
    content = """#EXTM3U
#EXTINF:-1,CCTV-5 Plus
http://media.invalid/cctv5plus.m3u8
#EXTINF:-1,CCTV5+
http://media.invalid/cctv5plus2.m3u8
#EXTINF:-1,CCTV-1
http://media.invalid/cctv1.m3u8
"""
    channels = live.parse_live_channels(content)
    # CCTV-5 Plus 和 CCTV5+ 归一化后都是 CCTV5P（独立频道），只保留第一条线路
    assert channels["CCTV5P"] == "http://media.invalid/cctv5plus.m3u8"
    assert "CCTV1" in channels


def test_parse_live_channel_routes_deduplicates_by_normalized_name():
    """任务5：归一化后去重——同一频道只保留第一条线路"""
    content = """#EXTM3U
#EXTINF:-1,CCTV-5 Plus
http://media.invalid/cctv5plus.m3u8
#EXTINF:-1,CCTV5+
http://media.invalid/cctv5plus2.m3u8
#EXTINF:-1,CCTV-1
http://media.invalid/cctv1.m3u8
"""
    routes = live.parse_live_channel_routes(content)
    # CCTV-5 Plus 和 CCTV5+ 归一化后都是 CCTV5P（独立频道），只保留第一条线路
    assert routes["CCTV5P"] == ["http://media.invalid/cctv5plus.m3u8"]
    assert "CCTV1" in routes


def test_classify_live_source_rejects_blacklist_domains():
    """任务4：虎牙/斗鱼/B站/YY 域名直接拒绝"""
    assert live._classify_live_source("test", "https://huya.com/live.m3u", "") == "carousel_rooms"
    assert live._classify_live_source("test", "https://douyu.com/live.m3u", "") == "carousel_rooms"
    assert live._classify_live_source("test", "https://bilibili.com/live.m3u", "") == "carousel_rooms"
    assert live._classify_live_source("test", "https://yy.com/live.m3u", "") == "carousel_rooms"


def test_classify_live_source_rejects_blacklist_name_keywords():
    """任务4：名称含轮播/一起看/虎牙/斗鱼 直接拒绝"""
    assert live._classify_live_source("虎牙一起看", "https://example.com/live.m3u", "") == "carousel_rooms"
    assert live._classify_live_source("斗鱼轮播", "https://example.com/live.m3u", "") == "carousel_rooms"


def test_classify_live_source_rejects_ipv6_only():
    """任务4：全部线路为 IPv6 地址直接拒绝"""
    content = """#EXTM3U
#EXTINF:-1,CCTV1
http://[2409:8087:1a09:df::401d]/ottrrs.hl.chinamobile.com/PLTV/88888888/224/3221226016/1.m3u8
#EXTINF:-1,CCTV2
http://[2409:8087:1a09:df::401d]/ottrrs.hl.chinamobile.com/PLTV/88888888/224/3221225588/1.m3u8
"""
    assert live._classify_live_source("IPv6直播", "https://example.com/live.m3u", content) == "ipv6_only"


def test_classify_live_source_marks_private_ip_only():
    """任务4：全部线路为内网 IP 标记为 private_ip（后续降权而非直接拒绝）"""
    content = """#EXTM3U
#EXTINF:-1,CCTV1
http://222.214.208.34:59901/tsfile/live/0001_1.m3u8
#EXTINF:-1,CCTV2
http://222.214.208.34:59901/tsfile/live/0002_1.m3u8
"""
    assert live._classify_live_source("四川电信IPTV", "https://example.com/live.m3u", content) == "private_ip"


def test_classify_live_source_rejects_carousel_rooms():
    """任务4：频道名全是房间名而非电视台命名直接拒绝"""
    content = """#EXTM3U
#EXTINF:-1,英雄联盟赛事直播
http://media.invalid/room1.m3u8
#EXTINF:-1,王者荣耀赛事直播
http://media.invalid/room2.m3u8
#EXTINF:-1,DOTA2赛事直播
http://media.invalid/room3.m3u8
#EXTINF:-1,CSGO赛事直播
http://media.invalid/room4.m3u8
#EXTINF:-1,和平精英赛事直播
http://media.invalid/room5.m3u8
#EXTINF:-1,绝地求生赛事直播
http://media.invalid/room6.m3u8
#EXTINF:-1,原神赛事直播
http://media.invalid/room7.m3u8
#EXTINF:-1,崩坏3赛事直播
http://media.invalid/room8.m3u8
#EXTINF:-1,明日方舟赛事直播
http://media.invalid/room9.m3u8
#EXTINF:-1,第五人格赛事直播
http://media.invalid/room10.m3u8
"""
    assert live._classify_live_source("游戏直播", "https://example.com/live.m3u", content) == "carousel_rooms"


def test_classify_live_source_passes_normal_tv():
    """任务4：正常电视台源通过预检"""
    content = """#EXTM3U
#EXTINF:-1,CCTV-1
http://media.invalid/cctv1.m3u8
#EXTINF:-1,湖南卫视
http://media.invalid/hunan.m3u8
#EXTINF:-1,浙江卫视
http://media.invalid/zhejiang.m3u8
"""
    assert live._classify_live_source("正常直播", "https://example.com/live.m3u", content) is None
