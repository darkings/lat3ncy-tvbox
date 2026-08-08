#!/usr/bin/env python3
import json
import sqlite3

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.classify_capabilities import classify_capabilities


def _insert_source(con, raw_id, fingerprint, name, category, api):
    raw = {"key": f"site-{raw_id}", "name": name, "type": 1, "api": api}
    con.execute(
        "INSERT INTO raw_source"
        "(id,import_batch,origin,site_key,name,type,api,ext,raw_json) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            raw_id,
            "fixture",
            "https://config.test/box.json",
            f"site-{raw_id}",
            name,
            1,
            api,
            "",
            json.dumps(raw, ensure_ascii=False),
        ),
    )
    con.execute(
        "INSERT INTO norm_source"
        "(raw_id,fingerprint,api_host,required_urls,category,capabilities) "
        "VALUES(?,?,?,?,?,?)",
        (raw_id, fingerprint, "config.test", "[]", category, "[]"),
    )
    con.execute(
        "INSERT INTO list_state(fingerprint,state,reason,updated_at) "
        "VALUES(?, 'candidate', 'fixture', datetime('now'))",
        (fingerprint,),
    )


def test_declared_and_observed_capabilities_are_persisted_without_state_change(tmp_path):
    db = tmp_path / "sources.db"
    report = tmp_path / "capability-report.json"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_source(
            con,
            1,
            "fp-declared",
            "儿童教学",
            "未分类",
            "http://127.0.0.1:5757/api/kids",
        )
        _insert_source(
            con,
            2,
            "fp-observed",
            "综合影视",
            "影视",
            "https://vod.test/api.php/provide/vod/",
        )
        con.execute(
            "INSERT INTO drpy_test_result"
            "(fingerprint,test_type,keyword,success,result_count,tested_at,run_id,adapter_version) "
            "VALUES('fp-observed','search','熊出没',1,8,datetime('now'),"
            "'maccms-media-1','maccms-media-v1')"
        )
        con.execute(
            "INSERT INTO drpy_run(run_id,adapter_version,started_at,finished_at) "
            "VALUES('unfinished','drpy-test',datetime('now'),NULL)"
        )
        con.execute(
            "INSERT INTO drpy_test_result"
            "(fingerprint,test_type,keyword,success,result_count,tested_at,run_id,adapter_version) "
            "VALUES('fp-observed','search','名侦探柯南',1,9,datetime('now'),"
            "'unfinished','drpy-test')"
        )

    summary = classify_capabilities(db, report_path=report)

    with sqlite3.connect(db) as con:
        declared = con.execute(
            "SELECT category,capabilities FROM norm_source "
            "WHERE fingerprint='fp-declared'"
        ).fetchone()
        observed = con.execute(
            "SELECT category,capabilities FROM norm_source "
            "WHERE fingerprint='fp-observed'"
        ).fetchone()
        evidence = json.loads(
            con.execute(
                "SELECT sampling_evidence FROM capability_sampling "
                "WHERE fingerprint='fp-observed' AND capability='children'"
            ).fetchone()[0]
        )
        states = con.execute(
            "SELECT DISTINCT state FROM list_state ORDER BY state"
        ).fetchall()

    assert declared[0] == "儿童"
    assert json.loads(declared[1]) == ["children"]
    assert observed[0] == "影视"
    assert json.loads(observed[1]) == ["children"]
    assert evidence["classifier_version"] == "capability-v1"
    assert evidence["items"][0]["kind"] == "observed_search"
    assert summary["children_capable"] == 2
    assert summary["observed_sources"] == 1
    assert states == [("candidate",)]
    assert report.exists()


def test_refresh_removes_stale_observed_capability(tmp_path):
    db = tmp_path / "sources.db"
    init_db(db)
    with sqlite3.connect(db) as con:
        _insert_source(
            con,
            1,
            "fp1",
            "综合影视",
            "影视",
            "https://vod.test/api.php/provide/vod/",
        )
        con.execute(
            "INSERT INTO drpy_test_result"
            "(fingerprint,test_type,keyword,success,result_count,tested_at,run_id,adapter_version) "
            "VALUES('fp1','search','熊出没',1,2,datetime('now'),"
            "'maccms-media-1','maccms-media-v1')"
        )
    classify_capabilities(db)

    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM drpy_test_result")
    classify_capabilities(db)

    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM capability_sampling WHERE fingerprint='fp1'"
        ).fetchone()[0] == 0
        assert json.loads(
            con.execute(
                "SELECT capabilities FROM norm_source WHERE fingerprint='fp1'"
            ).fetchone()[0]
        ) == []
