import base64
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient

from ponyo_source_manager.api import children
from ponyo_source_manager.api.children import resolve_approved_jar
from ponyo_source_manager.publishing.materialize_approved_assets import (
    materialize_approved_assets,
)


def _approval_db(path, *, sha256, status="approved", expires_at="2099-01-01T00:00:00+00:00"):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE dependency_asset_approval ("
        "content_sha256 TEXT PRIMARY KEY, asset_type TEXT, upstream_repo TEXT, "
        "status TEXT, expires_at TEXT, git_blob_sha TEXT)"
    )
    con.execute(
        "INSERT INTO dependency_asset_approval VALUES(?,?,?,?,?,?)",
        (sha256, "jar", "owner/repo", status, expires_at, "a" * 40),
    )
    con.commit()
    con.close()


def test_resolve_approved_jar_requires_active_approval_and_file(tmp_path):
    payload = b"approved immutable jar"
    sha256 = hashlib.sha256(payload).hexdigest()
    db_path = tmp_path / "sources.db"
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    _approval_db(db_path, sha256=sha256)
    target = asset_dir / f"{sha256}.jar"
    target.write_bytes(payload)

    assert resolve_approved_jar(
        sha256.upper(), db_path=db_path, asset_dir=asset_dir
    ) == target
    assert resolve_approved_jar(
        "not-a-sha", db_path=db_path, asset_dir=asset_dir
    ) is None


def test_approved_jar_http_endpoint_returns_exact_bytes(tmp_path, monkeypatch):
    payload = b"approved jar over http"
    sha256 = hashlib.sha256(payload).hexdigest()
    db_path = tmp_path / "sources.db"
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    _approval_db(db_path, sha256=sha256)
    (asset_dir / f"{sha256}.jar").write_bytes(payload)
    monkeypatch.setattr(children, "SOURCES_DB", db_path)
    monkeypatch.setattr(children, "APPROVED_JAR_DIR", asset_dir)
    monkeypatch.setattr(children, "init_children_db", lambda: None)

    with TestClient(children.app) as client:
        response = client.get(f"/assets/jar/{sha256}.jar")
        missing = client.get(f"/assets/jar/{'0' * 64}.jar")

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "application/java-archive"
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["cdn-cache-control"] == "public, max-age=300"
    assert response.headers["cloudflare-cdn-cache-control"] == "public, max-age=300"
    assert response.headers["etag"] == f'"{sha256}"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert missing.status_code == 404
    assert resolve_approved_jar(
        sha256,
        db_path=db_path,
        asset_dir=asset_dir,
        now="2100-01-01T00:00:00+00:00",
    ) is None


def test_materialize_approved_asset_verifies_sha_and_reuses_cache(tmp_path):
    payload = b"PK\x03\x04approved jar bytes"
    sha256 = hashlib.sha256(payload).hexdigest()
    db_path = tmp_path / "sources.db"
    output = tmp_path / "approved-assets"
    _approval_db(db_path, sha256=sha256)
    calls = []

    def fetch(url, **_kwargs):
        calls.append(url)
        return json.dumps(
            {
                "encoding": "base64",
                "content": base64.b64encode(payload).decode(),
            }
        )

    first = materialize_approved_assets(db_path, output, fetch_text=fetch)
    assert first["failures"] == []
    assert first["materialized"] == [
        {"sha256": sha256, "size": len(payload), "cached": False}
    ]
    assert (output / f"{sha256}.jar").read_bytes() == payload
    assert len(calls) == 1

    second = materialize_approved_assets(db_path, output, fetch_text=fetch)
    assert second["materialized"][0]["cached"] is True
    assert len(calls) == 1


def test_materialize_rejects_blob_that_does_not_match_approved_sha(tmp_path):
    expected_sha = hashlib.sha256(b"expected").hexdigest()
    db_path = tmp_path / "sources.db"
    output = tmp_path / "approved-assets"
    _approval_db(db_path, sha256=expected_sha)

    def fetch(_url, **_kwargs):
        return json.dumps(
            {
                "encoding": "base64",
                "content": base64.b64encode(b"different").decode(),
            }
        )

    result = materialize_approved_assets(db_path, output, fetch_text=fetch)
    assert len(result["failures"]) == 1
    assert "approved SHA mismatch" in result["failures"][0]["error"]
    assert not (output / f"{expected_sha}.jar").exists()
