import json, sqlite3
import initdb, scan_security as ss

RULES = [
    {"rule_id": "system-exit", "severity": "high", "pattern": r"System\.exit"},
    {"rule_id": "cleartext-secret", "severity": "high",
     "pattern": r"(?i)token\s*=\s*[A-Za-z0-9]{8,}"},
]

def test_match_detects_system_exit():
    hits = ss.match_text_rules("if(x){System.exit(0);}", RULES)
    ids = {h["rule_id"] for h in hits}
    assert "system-exit" in ids

def test_sanitize_masks_token():
    ev = ss.sanitize_evidence("k token=ABCD1234EFGH tail", 2, 22)
    assert "ABCD1234EFGH" not in ev and "****" in ev and "\n" not in ev

def test_check_jar_md5_mismatch_high():
    f = ss.check_jar_md5("deadbeef", b"real-bytes", "x.com", set())
    assert f and f["severity"] == "high" and f["rule_id"] == "jar-md5-mismatch"

def test_check_jar_md5_unverified_medium():
    f = ss.check_jar_md5("", b"j", "evil.com", {"cdn.jsdelivr.net"})
    assert f and f["severity"] == "medium" and f["rule_id"] == "jar-unverified"

def test_check_jar_md5_match_returns_none():
    import hashlib
    good = hashlib.md5(b"j").hexdigest()
    assert ss.check_jar_md5(good, b"j", "x.com", set()) is None

def test_sanitize_masks_underscore_token():
    ev = ss.sanitize_evidence("x password=ghp_1A2b3C4d5E6f7G8h9I0j tail", 2, 40)
    assert "ghp_1A2b3C4d5E6f7G8h9I0j" not in ev and "****" in ev

def test_sanitize_masks_dotted_and_dashed():
    ev1 = ss.sanitize_evidence("token=aaa.bbb.ccc-ddd end", 0, 22)
    assert "aaa.bbb.ccc-ddd" not in ev1 and "****" in ev1

def test_check_jar_md5_unpinned_low():
    f = ss.check_jar_md5("", b"j", "cdn.jsdelivr.net", {"cdn.jsdelivr.net"})
    assert f and f["severity"] == "low" and f["rule_id"] == "jar-unpinned"

def _seed(db, rows):
    initdb.init_db(str(db))
    con = sqlite3.connect(str(db))
    for raw_id, fp, urls, jar_md5 in rows:
        con.execute("INSERT INTO raw_source(id,import_batch,origin,site_key,raw_json)"
                    " VALUES(?,?,?,?,?)", (raw_id, "b", "o", f"k{raw_id}", "{}"))
        con.execute("INSERT INTO norm_source(raw_id,fingerprint,api_host,required_urls,"
                    "jar_md5,spider_class,category,capabilities) VALUES(?,?,?,?,?,?,?,?)",
                    (raw_id, fp, "h", json.dumps(urls), jar_md5, "", "影视", "[]"))
        con.execute("INSERT OR IGNORE INTO list_state(fingerprint,state,reason,updated_at)"
                    " VALUES(?,?,?,?)", (fp, "candidate", "", "T"))
    con.commit(); con.close()

def test_run_scan_flags_high_and_denies(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, [(1, "fp1", ["https://x.com/rule.js"], "")])
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps(
        [{"rule_id": "system-exit", "severity": "high", "pattern": r"System\.exit"}]),
        encoding="utf-8")
    allow = tmp_path / "a.json"; allow.write_text("[]", encoding="utf-8")
    rep = tmp_path / "sec.json"
    res = ss.run_scan(str(db), str(rules), str(allow), str(rep),
                      fetch_text=lambda u: "x=1;System.exit(0);",
                      fetch_bytes=lambda u: b"", now="T")
    assert res["high"] == 1 and "fp1" in res["deny_fps"]
    con = sqlite3.connect(str(db))
    state = con.execute("SELECT state FROM list_state WHERE fingerprint='fp1'").fetchone()[0]
    con.close()
    assert state == "deny"
    assert json.loads(rep.read_text(encoding="utf-8"))["summary"]["high"] == 1
