#!/usr/bin/env python3
"""静态安全扫描：文本危险规则匹配 + jar md5 完整性校验（纯函数段）。"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

_SECRET_RE = re.compile(
    r"(?i)(token|password|authorization)\s*[=:]\s*(?:basic\s+)?[\"']?([A-Za-z0-9+/]{6,})")

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
