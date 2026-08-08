from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.maccms_collector import (
    DEFAULT_KEYWORDS,
    MacCMSCollector,
    extract_play_urls,
    load_endpoints_from_db,
    normalize_endpoint,
)


def test_endpoint_normalization_and_play_url_extraction():
    endpoint = normalize_endpoint(
        "https://vod.test/api.php/provide/vod/?ac=detail&wd=x&token=kept"
    )
    assert endpoint == "https://vod.test/api.php/provide/vod/?token=kept"
    urls = extract_play_urls(
        {
            "vod_play_url": "第1集$https://cdn.test/1.m3u8#第2集$https://cdn.test/2.m3u8"
            "$$$网页$https://platform.test/watch/2#坏地址$javascript:x"
        }
    )
    assert urls == [
        "https://cdn.test/1.m3u8",
        "https://cdn.test/2.m3u8",
        "https://platform.test/watch/2",
    ]


def test_three_keyword_quick_probe_persists_evidence_without_list_state_change(
    tmp_path: Path,
):
    db = tmp_path / "sources.db"
    init_db(str(db))
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO list_state (fingerprint, state, reason, updated_at) "
            "VALUES ('existing', 'candidate', 'fixture', '2026-07-27T00:00:00Z')"
        )
        before = con.execute("SELECT * FROM list_state").fetchall()

    id_by_keyword = {
        keyword: str(index) for index, keyword in enumerate(DEFAULT_KEYWORDS, 1)
    }

    def fetch_json(url: str):
        query = parse_qs(urlsplit(url).query)
        if "wd" in query:
            keyword = query["wd"][0]
            return {
                "list": [
                    {
                        "vod_id": id_by_keyword.get(keyword, "0"),
                        "vod_name": f"高清 {keyword}",
                    }
                ]
            }
        content_id = query["ids"][0]
        return {
            "list": [
                {
                    "vod_id": content_id,
                    "vod_name": "detail",
                    "vod_play_url": f"正片$https://media.test/{content_id}/index.m3u8",
                }
            ]
        }

    collector = MacCMSCollector(
        db,
        fetch_json=fetch_json,
        safety_check=lambda _url: True,
        now=lambda: "2026-07-27T02:00:00+00:00",
    )
    result = collector.probe_endpoint(
        "https://vod.test/api.php/provide/vod/", run_id="run-1"
    )
    assert result["passed"] is True
    assert result["media_verified"] is False
    assert len(result["probes"]) == len(DEFAULT_KEYWORDS)
    assert all(probe["playable_url_count"] == 1 for probe in result["probes"])

    with sqlite3.connect(db) as con:
        after = con.execute("SELECT * FROM list_state").fetchall()
        probe_count = con.execute(
            "SELECT count(*) FROM maccms_probe_result WHERE run_id='run-1'"
        ).fetchone()[0]
        artifact = con.execute(
            "SELECT artifact_kind, metadata_json FROM discovered_artifact "
            "WHERE connector='maccms'"
        ).fetchone()
    assert after == before
    assert probe_count == len(DEFAULT_KEYWORDS)
    assert artifact[0] == "maccms_endpoint"
    assert '"media_verified": false' in artifact[1]


def test_keyword_miss_and_ssrf_fail_closed(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))
    collector = MacCMSCollector(
        db,
        fetch_json=lambda _url: {"list": [{"vod_id": "1", "vod_name": "完全无关"}]},
        safety_check=lambda url: "127.0.0.1" not in url,
    )
    missed = collector.probe_endpoint(
        "https://vod.test/cjapi/mc/vod/json.html", keywords=["熊出没"], run_id="miss"
    )
    assert missed["passed"] is False
    assert missed["failure_stage"] == "keyword_miss"

    blocked = collector.probe_endpoint(
        "http://127.0.0.1/api.php/provide/vod/", keywords=["熊出没"], run_id="ssrf"
    )
    assert blocked["passed"] is False
    assert blocked["failure_stage"] == "ssrf"
    with sqlite3.connect(db) as con:
        assert (
            con.execute("SELECT count(*) FROM discovered_artifact").fetchone()[0] == 0
        )


def test_load_endpoints_from_db_deduplicates_only_maccms(tmp_path: Path):
    db = tmp_path / "sources.db"
    init_db(str(db))
    with sqlite3.connect(db) as con:
        con.executemany(
            "INSERT INTO raw_source "
            "(import_batch, origin, site_key, name, type, api, raw_json) "
            "VALUES ('fixture', 'fixture', ?, ?, 1, ?, '{}')",
            [
                ("a", "A", "https://vod.test/api.php/provide/vod/?ac=detail"),
                ("b", "B", "https://vod.test/api.php/provide/vod/"),
                ("c", "C", "csp_Douban"),
            ],
        )
    assert load_endpoints_from_db(db) == ["https://vod.test/api.php/provide/vod/"]
