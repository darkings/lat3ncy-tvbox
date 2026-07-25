#!/usr/bin/env python3
"""静态安全扫描：文本危险规则匹配 + jar md5 完整性校验（纯函数段）。"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
import argparse, sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit
import net
from common import assert_no_proxy, strip_md5

_SECRET_RE = re.compile(
    r"(?i)(token|password|authorization)\s*[=:]\s*(?:basic\s+)?[\"']?([^\s\"'<>]{6,})")

def load_rules(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sanitize_evidence(text: str, start: int, end: int, width: int = 160) -> str:
    lo = max(0, start - width // 4)
    hi = min(len(text), end + width // 2)
    snippet = text[lo:hi].replace("\n", " ").replace("\r", " ")
    snippet = _SECRET_RE.sub(lambda m: f"{m.group(1)}={'*' * 4}", snippet)
    return snippet[:width]

def match_text_rules(text: str, rules: list[dict]) -> list[dict]:
    out = []
    for rule in rules:
        m = re.search(rule["pattern"], text)
        if m:
            out.append({"rule_id": rule["rule_id"], "severity": rule["severity"],
                        "evidence": sanitize_evidence(text, m.start(), m.end())})
    return out

def check_jar_md5(declared_md5, jar_bytes, host, allow_hosts) -> dict | None:
    declared = (declared_md5 or "").strip().lower()
    if declared:
        actual = hashlib.md5(jar_bytes).hexdigest()
        if actual != declared:
            return {"rule_id": "jar-md5-mismatch", "severity": "high",
                    "evidence": f"declared={declared[:12]}.. actual={actual[:12]}.."}
        return None
    if host in allow_hosts:
        return {"rule_id": "jar-unpinned", "severity": "low",
                "evidence": f"no md5 declared, host allowlisted: {host}"}
    return {"rule_id": "jar-unverified", "severity": "medium",
            "evidence": f"no md5 declared, host not allowlisted: {host}"}

_TEXT_EXT = (".js", ".py", ".txt", ".json")

def _asset_type(url: str) -> str:
    path = urlsplit(strip_md5(url)).path.lower()
    for ext in (".js", ".py", ".txt", ".json", ".jar"):
        if path.endswith(ext): return ext[1:]
    return "txt"

def run_scan(db_path, rules_path, allowlist_path, report_path, *,
             fetch_text=net.fetch_text, fetch_bytes=net.fetch_bytes, now=None) -> dict:
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，安全扫描中止（需无代理）。")
    now = now or datetime.now(timezone.utc).isoformat()
    rules = load_rules(rules_path)
    allow_hosts = set(json.loads(Path(allowlist_path).read_text(encoding="utf-8")))
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT fingerprint, required_urls, jar_md5 FROM norm_source").fetchall()
    fps = {}
    for fp, req, jar_md5 in rows:
        fps.setdefault(fp, {"urls": set(), "jar_md5": jar_md5 or ""})
        fps[fp]["urls"].update(json.loads(req or "[]"))
    findings = []  # (fp, url, asset_type, rule_id, severity, evidence)
    text_cache, summary = {}, {"scanned_urls": 0, "fetch_errors": 0}
    for fp, info in fps.items():
        for url in sorted(info["urls"]):
            if net.classify_url(url) == "template":
                continue
            atype = _asset_type(url)
            try:
                if atype == "jar":
                    host = urlsplit(strip_md5(url)).hostname or ""
                    f = check_jar_md5(info["jar_md5"], fetch_bytes(url), host, allow_hosts)
                    if f: findings.append((fp, url, atype, f["rule_id"], f["severity"], f["evidence"]))
                else:
                    if url not in text_cache:
                        text_cache[url] = fetch_text(url)
                    for h in match_text_rules(text_cache[url], rules):
                        findings.append((fp, url, atype, h["rule_id"], h["severity"], h["evidence"]))
                summary["scanned_urls"] += 1
            except Exception:
                summary["fetch_errors"] += 1
    scanned_fps = list(fps.keys())
    if scanned_fps:
        con.execute("DELETE FROM security_finding WHERE fingerprint IN (%s)"
                    % ",".join("?" * len(scanned_fps)), scanned_fps)
    con.executemany("INSERT INTO security_finding(fingerprint,target_url,asset_type,"
                    "rule_id,severity,evidence,scanned_at) VALUES(?,?,?,?,?,?,?)",
                    [(f[0], f[1], f[2], f[3], f[4], f[5], now) for f in findings])
    deny_fps = sorted({f[0] for f in findings if f[4] == "high"})
    for fp in deny_fps:
        con.execute("INSERT OR REPLACE INTO list_state(fingerprint,state,reason,updated_at)"
                    " VALUES(?,?,?,?)", (fp, "deny", "security:high", now))
    con.commit(); con.close()
    for sev in ("high", "medium", "low"):
        summary[sev] = sum(1 for f in findings if f[4] == sev)
    summary["deny_fps"] = deny_fps
    report = {"summary": summary, "generated_at": now,
              "findings": [{"fingerprint": f[0], "target_url": f[1], "asset_type": f[2],
                            "rule_id": f[3], "severity": f[4], "evidence": f[5]}
                           for f in sorted(findings, key=lambda x: {"high":0,"medium":1,"low":2}[x[4]])]}
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scanned_urls": summary["scanned_urls"], "high": summary["high"],
            "medium": summary["medium"], "low": summary["low"],
            "deny_fps": deny_fps, "fetch_errors": summary["fetch_errors"]}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--rules", default="config/security_rules.json")
    p.add_argument("--allowlist", default="config/allowlist.json")
    p.add_argument("--report", default="reports/security-report.json")
    a = p.parse_args()
    print(json.dumps(run_scan(a.db, a.rules, a.allowlist, a.report), ensure_ascii=False))

if __name__ == "__main__":
    main()
