import sqlite3

from ponyo_source_manager.publishing.generate_subscription import (
    _attach_approved_jar,
    _load_approved_jar_urls,
)


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE dependency_asset_evidence ("
        "fingerprint TEXT, asset_type TEXT, content_sha256 TEXT, "
        "actual_md5 TEXT, source_field TEXT)"
    )
    con.execute(
        "CREATE TABLE dependency_asset_approval ("
        "content_sha256 TEXT, asset_type TEXT, status TEXT, expires_at TEXT)"
    )
    return con


def test_approved_jar_url_is_sha_pinned_and_keeps_md5():
    con = _db()
    sha256 = "a" * 64
    con.execute(
        "INSERT INTO dependency_asset_evidence VALUES(?,?,?,?,?)",
        ("fp1", "jar", sha256, "B" * 32, "config.spider"),
    )
    con.execute(
        "INSERT INTO dependency_asset_approval VALUES(?,?,?,?)",
        (sha256, "jar", "approved", "2099-01-01T00:00:00+00:00"),
    )

    urls = _load_approved_jar_urls(
        con,
        now="2026-07-30T00:00:00+00:00",
        base_url="https://api.test/assets/jar",
    )
    assert urls == {
        "fp1": f"https://api.test/assets/jar/{sha256}.jar;md5;{'b' * 32}"
    }
    assert _attach_approved_jar({"key": "s1"}, "fp1", urls) == {
        "key": "s1",
        "jar": urls["fp1"],
    }


def test_expired_or_revoked_jar_is_never_rewritten():
    con = _db()
    for fingerprint, sha256, status, expires_at in (
        ("expired", "1" * 64, "approved", "2020-01-01T00:00:00+00:00"),
        ("revoked", "2" * 64, "revoked", "2099-01-01T00:00:00+00:00"),
    ):
        con.execute(
            "INSERT INTO dependency_asset_evidence VALUES(?,?,?,?,?)",
            (fingerprint, "jar", sha256, None, "site.jar"),
        )
        con.execute(
            "INSERT INTO dependency_asset_approval VALUES(?,?,?,?)",
            (sha256, "jar", status, expires_at),
        )

    urls = _load_approved_jar_urls(
        con,
        now="2026-07-30T00:00:00+00:00",
    )
    assert urls == {}
    original = {"key": "s1", "jar": "https://unapproved.example/a.jar"}
    assert _attach_approved_jar(original, "expired", urls) is original
