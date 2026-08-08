from ponyo_source_manager.discovery.verify_assets import collect_assets, verify_assets


def audit_fixture():
    return {"sources": [
        {
            "id": 1, "runtime_type": "drpy2", "testability": "needs_adapter", "content_roles": ["vod"],
            "resolved_dependencies": [
                {"field": "api", "resolved": "https://cdn/a.js", "status": "resolved"},
                {"field": "ext.rule", "resolved": "https://cdn/rule.js", "status": "resolved"},
                {"field": "jar", "resolved": "https://cdn/a.jar", "status": "resolved"},
            ],
        },
        {
            "id": 2, "runtime_type": "drpy2", "testability": "needs_adapter", "content_roles": ["vod"],
            "resolved_dependencies": [
                {"field": "api", "resolved": "https://cdn/a.js", "status": "resolved"},
            ],
        },
        {
            "id": 3, "runtime_type": "xbpq", "testability": "needs_adapter", "content_roles": ["vod"],
            "resolved_dependencies": [
                {"field": "ext", "resolved": "https://cdn/x.json", "status": "resolved"},
            ],
        },
    ]}


def test_collect_assets_deduplicates_and_keeps_provenance():
    assets = collect_assets(audit_fixture())
    assert [item["url"] for item in assets] == ["https://cdn/a.js", "https://cdn/rule.js"]
    assert assets[0]["sources"] == [1, 2]


def test_verify_assets_counts_sources_only_when_all_assets_pass():
    def fake_fetch(url):
        return {"success": not url.endswith("rule.js"), "status_code": 200, "error": None}

    report = verify_assets(audit_fixture(), fetcher=fake_fetch, workers=2)
    assert report["summary"]["unique_assets"] == 2
    assert report["summary"]["assets_passed"] == 1
    assert report["summary"]["sources_with_resolved_assets"] == 2
    assert report["summary"]["sources_all_assets_reachable"] == 1
