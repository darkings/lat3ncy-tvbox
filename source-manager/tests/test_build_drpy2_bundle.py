import hashlib
import json
from pathlib import Path

import pytest

from ponyo_source_manager.discovery import build_drpy2_bundle as bundle


def test_scan_rejects_node_and_private_access():
    assert {x["rule_id"] for x in bundle.scan_rule_text("require('fs'); fetch('http://127.0.0.1/x')")} == {
        "node-module", "private-target",
    }


def test_request_url_encodes_unicode_path():
    assert bundle.request_url("https://cdn.test/js/儿童.js?wd=熊出没") == (
        "https://cdn.test/js/%E5%84%BF%E7%AB%A5.js?wd=%E7%86%8A%E5%87%BA%E6%B2%A1"
    )


def test_github_raw_uses_jsdelivr_mirror():
    assert bundle.github_mirror_urls(
        "https://raw.githubusercontent.com/owner/repo/main/js/儿童.js"
    ) == ["https://cdn.jsdelivr.net/gh/owner/repo@main/js/儿童.js"]


def test_fetch_rule_preserves_security_rejection(monkeypatch):
    calls = []

    def reject(candidate, **_kwargs):
        calls.append(candidate)
        return {"success": False, "url": candidate, "error": "static security rejection",
                "findings": [{"rule_id": "node-module"}]}

    monkeypatch.setattr(bundle, "_fetch_rule_candidate", reject)
    result = bundle.fetch_rule("https://raw.githubusercontent.com/o/r/main/a.js")
    assert result["error"] == "static security rejection"
    assert result["findings"][0]["rule_id"] == "node-module"
    assert len(calls) == 1


def test_build_bundle_is_read_only_and_deduplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "assert_no_proxy", lambda: False)
    url = "https://cdn.test/rule.js"
    audit = {
        "sources": [
            {"id": 1, "name": "规则A", "runtime_type": "drpy2", "content_role": "vod", "effective_ext": url,
             "resolved_dependencies": [{"resolved": url}]},
            {"id": 2, "name": "规则A副本", "runtime_type": "drpy2", "content_role": "vod", "effective_ext": url,
             "resolved_dependencies": [{"resolved": url}]},
        ]
    }
    health = {"assets": [{"url": url, "success": True}]}
    audit_path, health_path = tmp_path / "audit.json", tmp_path / "health.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    health_path.write_text(json.dumps(health), encoding="utf-8")
    text = "var rule={title:'ok'};"

    def fake_fetch(target, **_kwargs):
        return {"success": True, "url": target, "final_url": target, "status_code": 200,
                "content_type": "text/javascript", "bytes": len(text.encode()),
                "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}

    report = bundle.build_bundle(
        str(audit_path), str(health_path), str(tmp_path / "bundle"), str(tmp_path / "report.json"),
        fetcher=fake_fetch,
    )
    assert report["read_only"] is True
    assert report["summary"]["accepted_rules"] == 1
    assert report["summary"]["accepted_sources"] == 2
    mapping = json.loads((tmp_path / "bundle/rule-map.json").read_text(encoding="utf-8"))["rules"]
    assert mapping[url]["source_ids"] == [1, 2]
    assert (tmp_path / "bundle/rules" / f"{mapping[url]['module']}.js").is_file()


def test_build_bundle_rejects_failed_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "assert_no_proxy", lambda: False)
    url = "https://cdn.test/bad.js"
    audit = {"sources": [{"id": 9, "name": "坏规则", "runtime_type": "drpy2", "content_role": "vod",
                           "effective_ext": url, "resolved_dependencies": [{"resolved": url}]}]}
    audit_path, health_path = tmp_path / "audit.json", tmp_path / "health.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    health_path.write_text(json.dumps({"assets": [{"url": url, "success": False}]}), encoding="utf-8")
    report = bundle.build_bundle(
        str(audit_path), str(health_path), str(tmp_path / "bundle"), str(tmp_path / "report.json"),
        fetcher=lambda *_args, **_kwargs: pytest.fail("failed asset must not be fetched"),
    )
    assert report["summary"]["accepted_rules"] == 0
    assert report["summary"]["rejected_sources"] == 1
