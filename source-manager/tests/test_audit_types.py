import json
import sqlite3

from ponyo_source_manager.discovery.audit_types import audit_database, audit_source, write_reports


def source(api, *, name="影视", ext=None, jar=None, site_id=1):
    raw = {"key": f"k{site_id}", "name": name, "type": 3, "api": api}
    if ext is not None:
        raw["ext"] = ext
    if jar is not None:
        raw["jar"] = jar
    return {
        "id": site_id, "origin": "fixture", "site_key": raw["key"],
        "name": name, "type": 3, "api": api,
        "ext": json.dumps(ext, ensure_ascii=False) if isinstance(ext, dict) else ext,
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def test_runtime_and_path_classification_matrix():
    cases = [
        (source("https://cdn/a/drpy2.min.js", ext="https://cdn/a/rule.js"), "drpy2", "absolute", "needs_adapter"),
        (source("./libs/js/drpy2.min.js", ext="./libs/js/rule.js"), "drpy2", "relative_unresolved", "needs_resolution"),
        (source("http://127.0.0.1:5757/api/rule"), "drpys", "local_only", "testable_now"),
        (source("https://a.test/api.php/provide/vod"), "maccms", "absolute", "needs_adapter"),
        (source("csp_XBPQ", ext="./libs/x.json"), "xbpq", "relative_unresolved", "needs_resolution"),
        (source("csp_DouDou", jar="./libs/spider.jar"), "jar_csp", "relative_unresolved", "needs_resolution"),
        (source("https://cdn/a/rule.py"), "python", "absolute", "needs_adapter"),
        (source("py_qie"), "python", "absolute", "needs_adapter"),
        (source("http://127.0.0.1:5757/cat/rule.js"), "catvod", "local_only", "needs_adapter"),
        (source("./libs/js/custom.min.js", site_id=9), "unknown", "relative_unresolved", "needs_resolution"),
    ]
    for item, runtime, path_state, testability in cases:
        result = audit_source(item)
        assert result["runtime_type"] == runtime
        assert result["path_state"] == path_state
        assert result["testability"] == testability


def test_multi_labels_do_not_hide_runtime():
    result = audit_source(source(
        "https://cdn/a/drpy2.min.js", name="虎牙直播", ext="https://cdn/a/huya.js"
    ))
    assert result["runtime_type"] == "live"
    assert result["runtime_tags"] == ["live", "drpy2"]
    assert result["content_roles"] == ["live"]
    assert result["testability"] == "needs_adapter"
    assert result["true_testable_vod"] is False


def test_drpy_site_key_and_nonstandard_maccms_are_identified():
    drpy = source("./libs/js/custom.min.js", ext="./libs/js/rule.js")
    drpy["site_key"] = "drpy_js_custom"
    drpy["raw_json"] = json.dumps({
        "key": "drpy_js_custom", "name": "影视", "type": 3,
        "api": drpy["api"], "ext": drpy["ext"],
    }, ensure_ascii=False)
    maccms = source("https://a.test/cjapi/mc/vod/json.html")
    assert audit_source(drpy)["runtime_type"] == "drpy2"
    assert audit_source(maccms)["runtime_type"] == "maccms"


def test_remote_origin_resolves_drpy_assets_without_mutating_raw_values():
    item = source("./libs/js/drpy2.min.js", ext="./libs/js/kids.js")
    item["origin"] = "https://raw.example/box/config.json"
    result = audit_source(item)
    assert result["path_state"] == "relative_resolved"
    assert result["resolution_status"] == "resolved"
    assert result["testability"] == "needs_adapter"
    assert result["effective_api"] == "https://raw.example/box/libs/js/drpy2.min.js"
    assert item["api"] == "./libs/js/drpy2.min.js"


def test_tool_cloud_children_and_true_vod_rules():
    config = audit_source(source("csp_Config", name="配置中心"))
    cloud = audit_source(source("csp_PanSearch", name="夸克网盘搜索"))
    children = audit_source(source(
        "https://cdn/a/drpy2.min.js", name="儿童教学", ext="https://cdn/a/kids.js"
    ))
    assert config["content_roles"] == ["settings", "tool"]
    assert config["testability"] == "excluded"
    assert "cloud_drive" in cloud["content_roles"]
    assert cloud["testability"] == "needs_adapter"
    assert children["content_roles"] == ["vod", "children"]
    assert children["true_testable_vod"] is False


def test_compact_cloud_name_markers_are_outside_normal_vod_quota():
    for name in ("欧哥[盘]", "资源┃盘", "资源站(盘)"):
        result = audit_source(source(
            "http://127.0.0.1:5757/api/cloud", name=name,
        ))
        assert "cloud_drive" in result["content_roles"]
        assert result["testability"] == "needs_adapter"
        assert result["true_testable_vod"] is False


def test_database_audit_is_complete_and_does_not_modify_list_state(tmp_path):
    db = tmp_path / "sources.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE raw_source (
          id INTEGER PRIMARY KEY, import_batch TEXT, origin TEXT, site_key TEXT,
          name TEXT, type INTEGER, api TEXT, ext TEXT, raw_json TEXT
        );
        CREATE TABLE list_state (fingerprint TEXT PRIMARY KEY, state TEXT, reason TEXT, updated_at TEXT);
        INSERT INTO list_state VALUES ('fp1', 'candidate', 'keep', '2026-07-27');
    """)
    fixtures = [
        source("https://cdn/a/drpy2.min.js", ext="https://cdn/a/a.js", site_id=1),
        source("csp_XBPQ", ext="./libs/a.json", site_id=2),
        source("https://a.test/api.php/provide/vod", site_id=3),
    ]
    for item in fixtures:
        con.execute(
            "INSERT INTO raw_source VALUES (?,?,?,?,?,?,?,?,?)",
            (item["id"], "b", item["origin"], item["site_key"], item["name"],
             item["type"], item["api"], item["ext"], item["raw_json"]),
        )
    before = con.execute("SELECT * FROM list_state").fetchall()
    con.commit()
    con.close()

    report = audit_database(db)
    assert report["summary"]["total"] == 3
    assert sum(report["summary"]["runtime_primary"].values()) == 3
    assert len(report["sources"]) == 3

    con = sqlite3.connect(db)
    assert con.execute("SELECT * FROM list_state").fetchall() == before
    con.close()

    json_path, md_path = tmp_path / "audit.json", tmp_path / "audit.md"
    write_reports(report, json_path, md_path)
    assert len(json.loads(json_path.read_text(encoding="utf-8"))["sources"]) == 3
    assert "逐源明细" in md_path.read_text(encoding="utf-8")
