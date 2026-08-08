from __future__ import annotations

import json
import sqlite3

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.probes.maccms_media import MacCMSMediaBridge


ENDPOINT = "https://vod.test/api.php/provide/vod/"


def insert_candidate(
    db,
    *,
    raw_id: int = 1,
    fingerprint: str = "fp-maccms",
    endpoint: str = ENDPOINT,
    keyword: str = "熊出没",
    search_ok: int = 1,
    detail_ok: int = 1,
    urls: tuple[str, ...] = ("https://media.test/video/index.m3u8",),
):
    evidence = {
        "matched_name": f"高清 {keyword}",
        "content_id": "100",
        "sample_urls": urls,
        "media_verified": False,
    }
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO raw_source"
            "(id,import_batch,origin,site_key,name,type,api,ext,raw_json) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                raw_id,
                "fixture",
                "fixture.json",
                f"site-{raw_id}",
                f"候选-{raw_id}",
                1,
                endpoint,
                "",
                json.dumps({"key": f"site-{raw_id}", "api": endpoint}),
            ),
        )
        con.execute(
            "INSERT INTO norm_source(raw_id,fingerprint,api_host,required_urls,category,capabilities) "
            "VALUES(?,?,?,?,?,?)",
            (raw_id, fingerprint, "vod.test", "[]", "影视", "[]"),
        )
        con.execute(
            "INSERT INTO list_state(fingerprint,state,reason,updated_at) "
            "VALUES(?,?,?,?)",
            (fingerprint, "candidate", "fixture", "2026-07-30T00:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO maccms_probe_result"
            "(run_id,endpoint,keyword,search_ok,keyword_hit,detail_ok,"
            "playable_url_count,failure_stage,evidence_json,probed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "quick-run",
                endpoint,
                keyword,
                search_ok,
                search_ok,
                detail_ok,
                len(urls),
                None if search_ok and detail_ok and urls else "search",
                json.dumps(evidence, ensure_ascii=False),
                "2026-07-30T00:00:00+00:00",
            ),
        )
        con.execute(
            "INSERT INTO discovered_artifact"
            "(connector,scope,artifact_url,effective_url,artifact_kind,revision,"
            "content_sha256,metadata_json,first_seen_at,last_seen_at,last_changed_at) "
            "VALUES('maccms','vod.test',?,?,'maccms_endpoint',NULL,'hash','{}',?,?,?)",
            (
                endpoint,
                endpoint,
                "2026-07-30T00:00:00+00:00",
                "2026-07-30T00:00:00+00:00",
                "2026-07-30T00:00:00+00:00",
            ),
        )


def successful_playback(*_args, **_kwargs):
    return {
        "success": 1,
        "m3u8_ok": 1,
        "segments_total": 5,
        "segments_checked": 3,
        "segments_ok": 3,
        "ffprobe_valid": 1,
        "latency_ms": 800,
        "first_frame_ms": 300,
        "throughput_kbps": 5000,
        "error": None,
    }


def successful_ffprobe(*_args, **_kwargs):
    return {
        "success": True,
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "codec_name": "h264",
                "bit_rate": "4000000",
                "r_frame_rate": "25/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "600", "bit_rate": "4500000"},
    }


def test_successful_maccms_media_bridge_persists_all_hard_gate_evidence(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    insert_candidate(db)
    bridge = MacCMSMediaBridge(
        db,
        playback_check=successful_playback,
        ffprobe_runner=successful_ffprobe,
        safety_check=lambda _url: True,
        now=lambda: "2026-07-30T01:00:00+00:00",
    )

    report = bridge.run(limit=10)

    assert report["summary"] == {
        "selected": 1,
        "quick_probe_ready": 1,
        "media_passed": 1,
        "media_failed": 0,
        "failure_stages": {},
    }
    with sqlite3.connect(db) as con:
        media = con.execute(
            "SELECT success,content_type,min_duration_s,duration_pass,"
            "ffprobe_success,quality_tier,height FROM media_probe"
        ).fetchone()
        tests = con.execute(
            "SELECT test_type,success FROM drpy_test_result ORDER BY id"
        ).fetchall()
        state = con.execute("SELECT state FROM list_state").fetchone()[0]
        probe_evidence = json.loads(con.execute(
            "SELECT evidence_json FROM maccms_probe_result"
        ).fetchone()[0])
        artifact = json.loads(con.execute(
            "SELECT metadata_json FROM discovered_artifact WHERE connector='maccms'"
        ).fetchone()[0])
    assert media == (1, "children", 180.0, 1, 1, "fhd", 1080)
    assert tests == [
        ("search", 1),
        ("detail", 1),
        ("episode", 1),
        ("playback", 1),
        ("ffprobe", 1),
    ]
    assert state == "candidate"
    assert probe_evidence["media_verified"] is True
    assert probe_evidence["media_attempt"]["success"] is True
    assert artifact["media_verified"] is True


def test_playback_failure_records_stage_without_running_ffprobe(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    insert_candidate(db)

    def failed_playback(*_args, **_kwargs):
        return {
            "success": 0,
            "m3u8_ok": 1,
            "segments_checked": 3,
            "segments_ok": 0,
            "latency_ms": 900,
            "error": "segments unreadable",
        }

    def forbidden_ffprobe(*_args, **_kwargs):
        raise AssertionError("ffprobe must not run after playback failure")

    report = MacCMSMediaBridge(
        db,
        playback_check=failed_playback,
        ffprobe_runner=forbidden_ffprobe,
        safety_check=lambda _url: True,
    ).run(limit=1)

    assert report["summary"]["failure_stages"] == {"media_playback_failed": 1}
    with sqlite3.connect(db) as con:
        media = con.execute(
            "SELECT success,ffprobe_success,duration_pass,error FROM media_probe"
        ).fetchone()
        playback_row = con.execute(
            "SELECT success,failure_stage FROM drpy_test_result "
            "WHERE test_type='playback'"
        ).fetchone()
    assert media[:3] == (0, 0, 0)
    assert "segments unreadable" in media[3]
    assert playback_row == (0, "media_playback_failed")


def test_quick_probe_failure_is_evidence_but_not_a_fake_media_probe(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    insert_candidate(db, search_ok=0, detail_ok=0, urls=())

    report = MacCMSMediaBridge(
        db,
        playback_check=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("playback must not run")
        ),
        safety_check=lambda _url: True,
    ).run(limit=1)

    assert report["summary"]["failure_stages"] == {"search": 1}
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM media_probe").fetchone()[0] == 0
        tests = con.execute(
            "SELECT test_type,success FROM drpy_test_result ORDER BY id"
        ).fetchall()
    assert tests == [("search", 0), ("detail", 0), ("episode", 0)]


def test_attempt_cursor_rotates_even_when_quick_probe_is_incomplete(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    insert_candidate(db, raw_id=1, fingerprint="fp-1", search_ok=0, detail_ok=0, urls=())
    insert_candidate(
        db,
        raw_id=2,
        fingerprint="fp-2",
        endpoint="https://vod2.test/api.php/provide/vod/",
        search_ok=0,
        detail_ok=0,
        urls=(),
    )
    bridge = MacCMSMediaBridge(db, safety_check=lambda _url: True)

    first = bridge.run(limit=1)
    second = bridge.run(limit=1)

    assert first["results"][0]["fingerprint"] == "fp-1"
    assert second["results"][0]["fingerprint"] == "fp-2"
