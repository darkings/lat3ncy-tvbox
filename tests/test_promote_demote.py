#!/usr/bin/env python3
import json
import sqlite3
import pytest
from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.scoring.promote_demote import evaluate_promotion, evaluate_demotion


def test_evaluate_promotion_new_candidate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    con = sqlite3.connect(str(db_path))
    con.execute("INSERT OR REPLACE INTO list_state VALUES ('fp1', 'candidate', '', '2026-07-25')")
    con.commit()

    res = evaluate_promotion(con, "fp1")
    # 没有观察天数和评分，保持 hold
    assert res["action"] == "hold"
    con.close()
