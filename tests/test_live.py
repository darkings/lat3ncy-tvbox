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
    path.write_text(
        json.dumps(
            [
                {"key": "a", "url": "https://example.invalid/a.m3u", "enabled": True},
                {"key": "b", "url": "https://example.invalid/b.m3u", "enabled": False},
            ]
        ),
        encoding="utf-8",
    )
    assert [item["key"] for item in live.load_configured_live_candidates(path)] == ["a"]


def test_inspect_live_metadata_extracts_epg_logo_catchup():
    content = (
        '#EXTM3U x-tvg-url="https://epg.invalid/xml,https://backup.invalid/xml" '
        'catchup="append" catchup-source="&t=${(b)yyyyMMddHHmmss}"\n'
        '#EXTINF:-1 tvg-logo="http://logo.invalid/1.png",CCTV1\n'
        "http://media.invalid/cctv1.m3u8\n"
        '#EXTINF:-1 tvg-logo="http://logo.invalid/2.png",CCTV2\n'
        "http://media.invalid/cctv2.m3u8\n"
    )
    meta = live.inspect_live_metadata(content)
    assert meta["has_epg"] is True
    assert meta["epg_url"] == "https://epg.invalid/xml"
    assert meta["catchup"] is True
    assert meta["logo_count"] == 2
    assert meta["channel_count"] == 2


def test_inspect_live_metadata_txt_without_epg():
    content = "CCTV1,http://media.invalid/cctv1.m3u8\n"
    meta = live.inspect_live_metadata(content)
    assert meta["has_epg"] is False
    assert meta["logo_count"] == 0
    assert meta["catchup"] is False
    assert meta["channel_count"] == 1


def test_parse_live_channel_routes_m3u_multiple_urls():
    content = (
        "#EXTM3U\n"
        "#EXTINF:-1,CCTV1\n"
        "http://media.invalid/primary.m3u8\n"
        "http://media.invalid/backup.m3u8\n"
        "#EXTINF:-1,CCTV5\n"
        "http://media.invalid/cctv5.m3u8\n"
    )
    routes = live.parse_live_channel_routes(content)
    assert routes["CCTV1"] == [
        "http://media.invalid/primary.m3u8",
        "http://media.invalid/backup.m3u8",
    ]
    assert routes["CCTV5"] == ["http://media.invalid/cctv5.m3u8"]


def test_parse_live_channel_routes_txt_duplicate_lines():
    content = "CCTV1,http://media.invalid/a.m3u8\nCCTV1,http://media.invalid/b.m3u8\n"
    routes = live.parse_live_channel_routes(content)
    assert routes["CCTV1"] == [
        "http://media.invalid/a.m3u8",
        "http://media.invalid/b.m3u8",
    ]


def test_evaluate_live_source_falls_back_to_second_route(monkeypatch):
    calls = []

    def fake_probe(url, timeout=5):
        calls.append(url)
        if "primary" in url:
            return {"ok": 0, "latency_ms": 5000, "err": "dead"}
        return {"ok": 1, "latency_ms": 900, "err": None}

    monkeypatch.setattr(
        live,
        "net",
        type(
            "Net",
            (),
            {
                "fetch_text": lambda *a, **k: (
                    "#EXTM3U\n#EXTINF:-1,CCTV1\n"
                    "http://media.invalid/primary.m3u8\n"
                    "http://media.invalid/backup.m3u8\n"
                )
            },
        )(),
    )
    res = live.evaluate_live_source(
        "k",
        "https://x.invalid/list.m3u",
        ["CCTV1"],
        probe_channel_fn=fake_probe,
    )
    assert res["validity_rate"] == 1.0
    assert res["probed_channels"][0]["ok"] == 1
    assert res["probed_channels"][0]["latency_ms"] == 900
    assert "backup" in calls[-1]


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

    monkeypatch.setattr(
        live,
        "load_configured_live_candidates",
        lambda: [
            {
                "key": "failed",
                "name": "失败直播",
                "url": "https://example.invalid/live.m3u",
            }
        ],
    )
    monkeypatch.setattr(
        live,
        "evaluate_live_source",
        lambda key, url, channels: {
            "key": key,
            "url": url,
            "total_score": 99.0,
            "validity_rate": 0.0,
            "avg_latency_ms": 9999,
            "hard_pass": False,
            "probed_channels": [],
        },
    )

    result = live.select_official_live_source(str(db))
    assert result["official_key"] is None
    assert result["official_url"] is None
