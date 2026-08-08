from __future__ import annotations

import json
import sqlite3

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.probes import drpy_runner
from ponyo_source_manager.probes.drpy_runner import (
    classify_content_lane,
    classify_drpy_route,
    load_keyword_profiles,
    run_batch_test,
)


TRUSTED_ORIGIN = "http://127.0.0.1:5757/config/1?pwd=ponyo-local-drpy"


def source(name, source_type, api, *, ext="", origin=TRUSTED_ORIGIN):
    raw = {
        "key": name,
        "name": name,
        "type": source_type,
        "api": api,
        "ext": ext,
    }
    return {
        "id": 1,
        "origin": origin,
        "site_key": name,
        "name": name,
        "type": source_type,
        "api": api,
        "ext": ext,
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def test_runtime_route_matrix_is_fail_closed():
    endpoint = "http://127.0.0.1:5757/api/影视?pwd=ponyo-local-drpy"
    cases = [
        (source("影视", 4, endpoint), "drpy_vod"),
        (source("设置中心", 4, endpoint), "excluded_tool"),
        (source("IPTV直播", 4, endpoint), "live_manager"),
        (source("夸克网盘", 4, endpoint), "cloud_adapter"),
        (source("欧哥[盘]", 4, endpoint), "cloud_adapter"),
        (
            source("规则影子", 3, "./libs/drpy2.min.js", ext="./js/rule.js"),
            "drpy2_shadow_needs_endpoint",
        ),
        (source("JAR源", 3, "csp_AppYs"), "unsupported_adapter"),
        (source("采集源", 1, "https://a.test/api.php/provide/vod/"), "maccms_probe"),
        (source("错误端点", 4, "https://a.test/api/rule"), "invalid_drpy_endpoint"),
    ]

    for item, expected in cases:
        assert classify_drpy_route(item)["route"] == expected


def test_content_lanes_and_keyword_profiles_keep_three_keyword_gate(tmp_path):
    endpoint = "http://127.0.0.1:5757/api/影视?pwd=ponyo-local-drpy"
    cases = [
        (source("普通影视", 4, endpoint), "general"),
        (source("哔哩少儿", 4, endpoint), "children"),
        (source("樱花動漫", 4, endpoint), "animation"),
        (source("番茄短剧", 4, endpoint), "short_drama"),
        (source("七猫小说[书]", 4, endpoint), "books_audio"),
        (source("DJ音乐[听]", 4, endpoint), "audio_music"),
        (source("蓝色纪录片", 4, endpoint), "documentary"),
    ]
    for item, expected in cases:
        assert classify_content_lane(item) == expected

    config = tmp_path / "keywords.json"
    config.write_text(json.dumps({
        "profiles": {
            "general": ["甲", "乙", "丙"],
            "children": ["丁", "戊", "己"],
        },
    }, ensure_ascii=False), encoding="utf-8")
    profiles = load_keyword_profiles(config)
    assert profiles["general"] == ["甲", "乙", "丙"]
    assert profiles["children"] == ["丁", "戊", "己"]
    assert all(len(values) == 3 for values in profiles.values())


def test_batch_only_executes_routed_drpy_endpoints(tmp_path, monkeypatch):
    db = tmp_path / "sources.db"
    init_db(db)
    endpoint = "http://127.0.0.1:5757/api/影视?pwd=ponyo-local-drpy"
    fixtures = [
        source("影视", 4, endpoint),
        source("JAR源", 3, "csp_AppYs", origin="https://config.test/box.json"),
    ]
    with sqlite3.connect(db) as con:
        for index, item in enumerate(fixtures, start=1):
            con.execute(
                "INSERT INTO raw_source"
                "(id,import_batch,origin,site_key,name,type,api,ext,raw_json)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    index, "batch", item["origin"], item["site_key"], item["name"],
                    item["type"], item["api"], item["ext"], item["raw_json"],
                ),
            )
            con.execute(
                "INSERT INTO norm_source(raw_id,fingerprint) VALUES(?,?)",
                (index, f"fp-{index}"),
            )

    calls = []

    def fake_chain(rule_path, keyword, db_path="", fp="", runner=None):
        calls.append((rule_path, keyword, fp))
        return [{
            "test_type": "search",
            "keyword": keyword,
            "success": 1,
            "result_count": 1,
            "latency_ms": 1,
            "error": None,
            "failure_stage": None,
        }]

    monkeypatch.setattr(drpy_runner, "run_full_chain", fake_chain)
    keywords = tmp_path / "keywords.json"
    keywords.write_text(json.dumps(["熊出没", "庆余年", "流浪地球"]), encoding="utf-8")
    report = tmp_path / "report.json"

    summary = run_batch_test(db, keywords, report_path=report)

    assert summary["discovered_sources"] == 2
    assert summary["total_sources"] == 1
    assert summary["tested"] == 1
    assert summary["passed"] == 1
    assert summary["routed_out"] == 1
    assert summary["routing_counts"] == {"drpy_vod": 1, "unsupported_adapter": 1}
    assert summary["keyword_profile_counts"] == {"general": 1}
    assert calls == [
        (endpoint, "熊出没", "fp-1"),
        (endpoint, "庆余年", "fp-1"),
        (endpoint, "流浪地球", "fp-1"),
    ]

    with sqlite3.connect(db) as con:
        run = con.execute(
            "SELECT total_sources,discovered_sources,routing_counts_json,"
            "keyword_profile_counts_json FROM drpy_run"
        ).fetchone()
        tested = con.execute(
            "SELECT DISTINCT fingerprint FROM drpy_test_result"
        ).fetchall()
    assert run[:2] == (1, 2)
    assert json.loads(run[2]) == summary["routing_counts"]
    assert json.loads(run[3]) == summary["keyword_profile_counts"]
    assert tested == [("fp-1",)]
