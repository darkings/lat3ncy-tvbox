import json
import sqlite3

import pytest

from ponyo_source_manager.core.initdb import init_db
from ponyo_source_manager.discovery.drpy_connector import (
    DEFAULT_CONFIG_URL,
    import_drpy_config,
    validate_config_url,
)


def _policy_file(tmp_path, policy):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    return path


def test_trusted_connector_url_is_narrowly_scoped():
    assert validate_config_url(DEFAULT_CONFIG_URL) == DEFAULT_CONFIG_URL
    for rejected in (
        "http://localhost:5757/config/1",
        "http://127.0.0.1:5758/config/1",
        "http://127.0.0.1:5757/config/2",
        "http://169.254.169.254:5757/config/1",
        "https://127.0.0.1:5757/config/1",
    ):
        with pytest.raises(ValueError):
            validate_config_url(rejected)


def test_trusted_connector_imports_and_is_idempotent(tmp_path, policy):
    db_path = tmp_path / "sources.db"
    init_db(str(db_path))
    policy_path = _policy_file(tmp_path, policy)
    document = {
        "sites": [
            {
                "key": "drpys_real",
                "name": "DRPYS real module",
                "type": 4,
                "api": "http://127.0.0.1:5757/api/real-module",
            }
        ]
    }

    def fake_fetch(url, timeout=20.0):
        assert url == DEFAULT_CONFIG_URL
        return json.dumps(document)

    first = import_drpy_config(
        str(db_path), str(policy_path), fetch_fn=fake_fetch, now="2026-07-26T00:00:00+00:00"
    )
    second = import_drpy_config(
        str(db_path), str(policy_path), fetch_fn=fake_fetch, now="2026-07-26T00:01:00+00:00"
    )
    assert first["added"] == 1
    assert second["added"] == 0
    assert second["skipped"] == 1

    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM norm_source").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM list_state").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM candidate_version").fetchone()[0] == 1

