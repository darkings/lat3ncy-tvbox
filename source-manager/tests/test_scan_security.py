import scan_security as ss

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
