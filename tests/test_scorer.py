#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.scoring.scorer import (
    check_hard_thresholds,
    classify_source_media_role,
    compute_consecutive_fail,
    compute_func_success,
    compute_speed,
    compute_stability,
    compute_timeslot_completeness,
    score_fingerprint,
)


def test_check_hard_thresholds():
    metrics_pass = {
        "func": {"rate": 0.95},
        "play": {"rate": 0.90},
        "quality": {"hd_ratio": 0.85, "duration_total": 1, "duration_pass_rate": 1.0},
        "consecutive_fail": 0,
        "speed": {"p50": 1200},
        "timeslot_completeness": {"complete": True},
    }
    passed, errs = check_hard_thresholds(metrics_pass)
    assert passed is True
    assert len(errs) == 0

    metrics_fail = {
        "func": {"rate": 0.80},  # < 90%
        "play": {"rate": 0.70},  # < 85%
        "quality": {"hd_ratio": 0.50, "duration_total": 1, "duration_pass_rate": 0.0},
        "consecutive_fail": 4,
        "speed": {"p50": 5000},
        "timeslot_completeness": {"complete": False},
    }
    passed, errs = check_hard_thresholds(metrics_fail)
    assert passed is False
    assert len(errs) == 7
    assert any("duration" in err.lower() or "时长" in err for err in errs)


def test_check_hard_thresholds_audio_skips_hd_gate():
    # 纯音频源无视频流，高清比例门禁不适用
    metrics_audio = {
        "func": {"rate": 0.95},
        "play": {"rate": 0.90},
        "quality": {"hd_ratio": 0.0, "duration_total": 1, "duration_pass_rate": 1.0},
        "consecutive_fail": 0,
        "speed": {"p50": 1200},
        "timeslot_completeness": {"complete": True},
    }
    passed, errs = check_hard_thresholds(metrics_audio, media_role="audio_music")
    assert passed is True
    assert len(errs) == 0

    # short_drama 仍保留高清门槛（竖屏短剧仍是视频）
    passed2, errs2 = check_hard_thresholds(metrics_audio, media_role="short_drama")
    assert passed2 is False
    assert any("高清" in e for e in errs2)


def test_classify_source_media_role_by_name(tmp_path):
    db = tmp_path / "test.db"
    init_db(str(db))
    con = sqlite3.connect(str(db))
    for raw_id, name in [(1, "啊哈DJ[听]"), (2, "短剧聚合[短]"), (3, "360资源")]:
        con.execute(
            "INSERT INTO raw_source(id,import_batch,origin,site_key,name,raw_json)"
            " VALUES(?,?,?,?,?,?)",
            (raw_id, "b", "o", f"k{raw_id}", name, "{}"),
        )
        con.execute(
            "INSERT INTO norm_source(raw_id,fingerprint,api_host,required_urls)"
            " VALUES(?,?,?,?)",
            (raw_id, f"fp{raw_id}", "h", "[]"),
        )
    con.commit()
    assert classify_source_media_role(con, "fp1") == "audio_music"
    assert classify_source_media_role(con, "fp2") == "short_drama"
    assert classify_source_media_role(con, "fp3") == "general"


def test_compute_speed_picks_best_when_samples_are_scarce(tmp_path):
    # 1-2 个样本：取最低值，避免单次冷启动抖动判源死刑。
    # 注意：_logical_test_rows 会按 (run_id, test_type, keyword, adapter) 去重，
    # 所以多个样本需用不同 keyword（模拟测了不同剧集）。
    db = tmp_path / "speed.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        _insert_test(con, "r1", "playback", 1, keyword="k1", latency_ms=4749)
        _insert_test(con, "r1", "playback", 1, keyword="k2", latency_ms=1648)
    with sqlite3.connect(db) as con:
        result = compute_speed(con, "fp1")
    assert result["samples"] == 2
    assert result["p50"] == 1648  # 取最低值代表可达能力


def test_compute_speed_uses_trimmed_mean_for_three_or_four_samples(tmp_path):
    # 3 个样本：去掉最高单次抖动后取均值
    db = tmp_path / "speed3.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        _insert_test(con, "r1", "playback", 1, keyword="k1", latency_ms=4749)
        _insert_test(con, "r1", "playback", 1, keyword="k2", latency_ms=4644)
        _insert_test(con, "r1", "playback", 1, keyword="k3", latency_ms=1648)
    with sqlite3.connect(db) as con:
        result = compute_speed(con, "fp1")
    assert result["samples"] == 3
    assert result["p50"] == int((1648 + 4644) / 2)  # 截掉 4749 后取均值


def test_compute_speed_uses_median_for_five_or_more_samples(tmp_path):
    # 5 个样本：标准中位
    db = tmp_path / "speed5.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        for i, lat in enumerate([1500, 1800, 2200, 3500, 8000], start=1):
            _insert_test(con, "r1", "playback", 1, keyword=f"k{i}", latency_ms=lat)
    with sqlite3.connect(db) as con:
        result = compute_speed(con, "fp1")
    assert result["samples"] == 5
    assert result["p50"] == 2200  # 排序后中位 latencies[2]


def test_compute_speed_no_samples_returns_none(tmp_path):
    db = tmp_path / "empty.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        _insert_test(con, "r1", "playback", 0, keyword="k1", latency_ms=5000)
        result = compute_speed(con, "fp1")
    assert result["samples"] == 0
    assert result["p50"] is None


def test_compute_timeslot_completeness_requires_all_four_slots(tmp_path):
    from ponyo_source_manager.scoring.scorer import compute_timeslot_completeness

    db = tmp_path / "ts.db"
    con = sqlite3.connect(str(db))
    con.execute("""
        CREATE TABLE conn_probe (
            fingerprint TEXT,
            timeslot TEXT,
            ok INT,
            probed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    fp = "fp_test"

    # 0 个时段
    res0 = compute_timeslot_completeness(con, fp)
    assert res0["complete"] is False
    assert len(res0["missing"]) == 4

    # 1 个时段
    con.execute(
        "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, 'morning', 1)",
        (fp,),
    )
    con.commit()
    res1 = compute_timeslot_completeness(con, fp)
    assert res1["complete"] is False
    assert set(res1["missing"]) == {"noon", "evening", "night"}

    # 2 个时段
    con.execute(
        "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, 'noon', 1)",
        (fp,),
    )
    con.commit()
    res2 = compute_timeslot_completeness(con, fp)
    assert res2["complete"] is False

    # 3 个时段
    con.execute(
        "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, 'evening', 1)",
        (fp,),
    )
    con.commit()
    res3 = compute_timeslot_completeness(con, fp)
    assert res3["complete"] is False

    # 4 个完整时段
    con.execute(
        "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, 'night', 1)",
        (fp,),
    )
    con.commit()
    res4 = compute_timeslot_completeness(con, fp)
    assert res4["complete"] is True
    assert len(res4["missing"]) == 0
    con.close()


def _insert_run(con, run_id, *, finished=True):
    con.execute(
        "INSERT INTO drpy_run(run_id,adapter_version,started_at,finished_at) "
        "VALUES(?,?,datetime('now'),?)",
        (run_id, "drpy-test", "2026-07-30T00:01:00+00:00" if finished else None),
    )


def _insert_test(
    con,
    run_id,
    test_type,
    success,
    *,
    keyword="测试",
    adapter="drpy-test",
    latency_ms=None,
    evidence_json=None,
):
    con.execute(
        "INSERT INTO drpy_test_result"
        "(fingerprint,test_type,keyword,success,latency_ms,tested_at,run_id,"
        "adapter_version,evidence_json) "
        "VALUES('fp1',?,?,?,?,datetime('now'),?,?,?)",
        (
            test_type,
            keyword,
            success,
            latency_ms,
            run_id,
            adapter,
            evidence_json if evidence_json is not None else "{}",
        ),
    )


def test_compute_speed_prefers_first_frame_ms_over_total_latency(tmp_path):
    """首帧口径：latency_ms 是 m3u8+3 段总耗时，应优先用 evidence.first_frame_ms。"""
    db = tmp_path / "speed_ff.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        _insert_test(
            con,
            "r1",
            "playback",
            1,
            keyword="k1",
            latency_ms=10948,
            evidence_json='{"first_frame_ms": 2539, "segments_ok": 3}',
        )
        _insert_test(
            con,
            "r1",
            "playback",
            1,
            keyword="k2",
            latency_ms=8835,
            evidence_json='{"first_frame_ms": 2314, "segments_ok": 3}',
        )
        _insert_test(
            con,
            "r1",
            "playback",
            1,
            keyword="k3",
            latency_ms=3000,
            evidence_json="{}",  # 无 first_frame_ms → 回退 latency_ms
        )
    with sqlite3.connect(db) as con:
        result = compute_speed(con, "fp1")
    assert result["samples"] == 3
    # 3 样本走截尾均值：(2314+2539)/2
    assert result["p50"] == 2426
    # 若错误使用 latency_ms，截尾均值为 (8835+10948)/2
    assert result["p50"] < 4000


def test_compute_speed_first_frame_null_falls_back_to_latency(tmp_path):
    db = tmp_path / "speed_ff2.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "r1")
        _insert_test(
            con,
            "r1",
            "playback",
            1,
            keyword="k1",
            latency_ms=2500,
            evidence_json=None,
        )
    with sqlite3.connect(db) as con:
        result = compute_speed(con, "fp1")
    assert result["p50"] == 2500


def test_function_evidence_deduplicates_a_logical_check_and_ignores_unfinished_run(
    tmp_path,
):
    db = tmp_path / "evidence.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "complete")
        _insert_run(con, "unfinished", finished=False)
        _insert_test(con, "complete", "search", 0)
        _insert_test(con, "complete", "search", 1)
        _insert_test(con, "unfinished", "search", 0)

        result = compute_func_success(con, "fp1")

    assert result["rate"] == 1.0
    assert result["total"] == 1
    assert result["runs"] == 1
    assert result["applicable"] is True


def test_function_rate_balances_completed_runs_instead_of_row_counts(tmp_path):
    db = tmp_path / "balanced.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_run(con, "large-profile")
        _insert_run(con, "small-profile")
        for test_type in ("search", "detail", "episode"):
            _insert_test(con, "large-profile", test_type, 1)
        _insert_test(con, "small-profile", "search", 0)

        result = compute_func_success(con, "fp1")

    assert result["ok"] == 3
    assert result["total"] == 4
    assert result["runs"] == 2
    assert result["rate"] == 0.5


def test_maccms_connector_run_is_applicable_without_drpy_run_row(tmp_path):
    db = tmp_path / "maccms.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        for test_type in ("search", "detail", "episode"):
            _insert_test(
                con,
                "maccms-media-1",
                test_type,
                1,
                adapter="maccms-media-v1",
            )

        result = compute_func_success(con, "fp1")

    assert result["rate"] == 1.0
    assert result["applicable"] is True
    assert result["adapters"] == ["maccms-media-v1"]


def test_consecutive_failure_counts_probe_batches_not_urls(tmp_path):
    db = tmp_path / "conn.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        for url in ("https://a.test", "https://b.test", "https://c.test"):
            con.execute(
                "INSERT INTO conn_probe"
                "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,http_status,"
                "latency_ms,ok,err,probed_at) VALUES(?,?, 'night',1,1,1,500,10,0,'x',?)",
                ("fp1", url, "2026-07-30T03:00:00+00:00"),
            )
        con.execute(
            "INSERT INTO conn_probe"
            "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,http_status,"
            "latency_ms,ok,err,probed_at) VALUES('fp1','https://a.test','evening',"
            "1,1,1,200,10,1,NULL,'2026-07-30T02:00:00+00:00')"
        )

        assert compute_consecutive_fail(con, "fp1") == 1


def test_timeslot_and_stability_require_the_whole_probe_batch(tmp_path):
    db = tmp_path / "batch.db"
    init_db(db)
    base = datetime.now(timezone.utc) - timedelta(hours=6)
    with sqlite3.connect(db) as con:
        rows = [
            ("morning", base.isoformat(), 1, "a"),
            ("morning", base.isoformat(), 0, "b"),
            ("morning", (base + timedelta(hours=1)).isoformat(), 1, "a"),
            ("noon", (base + timedelta(hours=2)).isoformat(), 1, "a"),
            ("evening", (base + timedelta(hours=3)).isoformat(), 1, "a"),
            ("night", (base + timedelta(hours=4)).isoformat(), 1, "a"),
        ]
        for timeslot, probed_at, ok, suffix in rows:
            con.execute(
                "INSERT INTO conn_probe"
                "(fingerprint,target_url,timeslot,dns_ok,tcp_ok,tls_ok,http_status,"
                "latency_ms,ok,err,probed_at) VALUES(?,?,?,1,1,1,200,10,?,NULL,?)",
                ("fp1", f"https://{suffix}.test", timeslot, ok, probed_at),
            )

        completeness = compute_timeslot_completeness(con, "fp1")
        stability = compute_stability(con, "fp1")

    assert completeness["complete"] is True
    assert stability["timeslots"]["morning"] == 0.5
    assert stability["rate"] == 0.65
