# Ponyo 源管理系统 阶段三 A+B 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 phase1-2 的 SQLite 库上加「源健康引擎 v1」：对每个指纹的唯一远程资产做静态安全扫描（第 2 层）与无代理连通性探测（第 3 层），沉淀到两张新表与脱敏报告，命中高危自动 `deny`。

**Architecture:** 三个单一职责脚本共享 `net.py`（网络 I/O 唯一出口，可注入 → 单测全 mock）：`scan_security.py`（下载文本 grep 危险规则 + jar 仅校验 md5）、`probe_conn.py`（DNS→TCP→TLS→HTTP 分层探测）。扫描对象是 148 指纹的**唯一 URL 集合**（同 URL 只扫一次再映射回各指纹）。代码进 git；`data/reports/logs` 仍 gitignore。TDD 本地开发，最后 scp 同步到 `jie` 真跑验收。

**Tech Stack:** Python 3.11（标准库 only：`sqlite3`/`hashlib`/`ssl`/`socket`/`urllib`/`json`/`re`/`argparse`）、pytest。

## Global Constraints

- Python 3.11+，仅标准库 + pytest，不引第三方运行时依赖。所有文件读写显式 `encoding="utf-8"`。
- 无代理：两脚本入口先 `common.assert_no_proxy()`，**非空即 abort**（与 phase1-2 的"仅告警"不同——本阶段真发网络请求，代理下必须停）。
- 扫描深度 ②：下载远程 `.js/.py/.txt/.json` 做正则 grep；jar 仅算 md5 与声明比对，**不反编译、不执行**。
- 命中任一 **high** → 该指纹 `list_state.state='deny'`，`reason` 记来源 rule_id，报告留脱敏证据。连通性失败**不改状态**（仅证据）。
- 网络纪律：并发 ≤8，同 host 串行 + 200ms 间隔，超时 8s，失败重试 ≤1，GET 带 `Range: bytes=0-0`。
- 脱敏：入库/入报告的 evidence 截断到 ~160 字符，对 `token=`/`password=`/`Authorization: Basic` 的值打 `****`；报告绝不含明文密钥/token/完整播放临时 URL。
- 复用 phase1-2：`common.compute_fingerprint/assert_no_proxy/strip_md5/is_critical_asset`；`norm_source.required_urls` 是 JSON 数组串，`norm_source.jar_md5` 为该指纹声明的 jar md5；`list_state=(fingerprint,state,reason,updated_at)`。
- 幂等：`initdb` 追加 phase3 两表用 `IF NOT EXISTS`；`scan_security` 重扫前按被扫指纹 DELETE 旧 finding 再插；`conn_probe` 按 timeslot 追加（保留历史）。
- 提交约定：不加 `Co-Authored-By`，作者保持 `_1at3ncy`，commit 用 `git -c commit.gpgsign=false`。
- 时间戳：脚本内 `datetime.now(timezone.utc).isoformat()`；测试注入固定 `now=` 便于断言。

## 文件结构

```text
source-manager/
├─ net.py               网络 I/O 唯一出口：classify_url(纯) + probe(分层,可注入) + fetch_text/fetch_bytes
├─ scan_security.py     纯匹配器(match_text_rules/sanitize_evidence/check_jar_md5) + run_scan 编排
├─ probe_conn.py        run_probe：读库→net.probe→conn_probe→报告
├─ schema_phase3.sql    security_finding + conn_probe + 2 索引
├─ initdb.py            [修改] 建库后追加执行 schema_phase3.sql
├─ config/
│  ├─ security_rules.json   文本危险规则集(rule_id/severity/pattern)，可 review
│  └─ allowlist.json        [已存在] 复用为 jar 白名单域来源
└─ tests/
   ├─ conftest.py       [修改] 加 phase3 fixture（含危险样本文本 + jar 字节）
   ├─ test_net.py       classify_url + probe 分层短路（mock）
   ├─ test_scan_security.py  匹配器纯函数 + run_scan 编排（临时 DB + mock fetch）
   └─ test_probe_conn.py     run_probe（临时 DB + mock probe）
```

每文件单一职责；`net.py` 是网络唯一出口，其余脚本经注入其函数实现「本地 mock / jie 真跑」切换。

---

### Task 0: phase3 schema 与 initdb 接线

**Files:**
- Create: `source-manager/schema_phase3.sql`
- Modify: `source-manager/initdb.py:9-24`（`SCHEMA` 常量段 + `init_db` 内 executescript 段）
- Test: `source-manager/tests/test_initdb.py`（追加 1 个用例）

**Interfaces:**
- Consumes: `initdb.init_db(db_path, reset=False)`（phase1-2 已有）
- Produces: 库中新增表 `security_finding`、`conn_probe`；`init_db` 仍幂等。

- [ ] **Step 1: 写 schema_phase3.sql**

```sql
CREATE TABLE IF NOT EXISTS security_finding (
  id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, target_url TEXT,
  asset_type TEXT, rule_id TEXT NOT NULL, severity TEXT NOT NULL,
  evidence TEXT, scanned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sf_fp ON security_finding(fingerprint, severity);
CREATE TABLE IF NOT EXISTS conn_probe (
  id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, target_url TEXT NOT NULL,
  timeslot TEXT NOT NULL, dns_ok INT, tcp_ok INT, tls_ok INT,
  http_status INT, latency_ms INT, ok INT NOT NULL, err TEXT, probed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_fp ON conn_probe(fingerprint, timeslot);
```

- [ ] **Step 2: 写失败测试**（追加到 test_initdb.py）

```python
def test_initdb_creates_phase3_tables(tmp_path):
    db = tmp_path / "s.db"
    initdb.init_db(str(db))
    import sqlite3
    con = sqlite3.connect(str(db))
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"security_finding", "conn_probe"} <= names
```

- [ ] **Step 3: 跑测试确认失败** — Run: `python -m pytest tests/test_initdb.py::test_initdb_creates_phase3_tables -v` — Expected: FAIL（表不存在）

- [ ] **Step 4: 改 initdb.py 追加执行 phase3 schema**

```python
SCHEMA = HERE / "schema.sql"
SCHEMA_PHASE3 = HERE / "schema_phase3.sql"
# ...在 init_db 内 executescript(ddl) 之后追加：
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        if SCHEMA_PHASE3.exists():
            con.executescript(SCHEMA_PHASE3.read_text(encoding="utf-8"))
        con.commit()
```

- [ ] **Step 5: 跑测试确认通过** — Run: `python -m pytest tests/test_initdb.py -v` — Expected: PASS（含原有 3 + 新 1）

- [ ] **Step 6: 提交**

```bash
git add source-manager/schema_phase3.sql source-manager/initdb.py source-manager/tests/test_initdb.py
git -c commit.gpgsign=false commit -m "feat(source-manager): add phase3 schema (security_finding, conn_probe)"
```

---

### Task 1: net.py — URL 分类与分层探测

**Files:**
- Create: `source-manager/net.py`
- Test: `source-manager/tests/test_net.py`

**Interfaces:**
- Produces:
  - `classify_url(url: str) -> str`：返回 `"template"`（含 `{`/`}` 占位）| `"local"`（localhost/127./10./192.168./172.16-31 内网）| `"probe"`（可探测）。
  - `probe(url, *, now, resolver=_getaddrinfo, opener=_urlopen, timeout=8.0, retries=1) -> dict`：返回 `{dns_ok,tcp_ok,tls_ok,http_status,latency_ms,ok,err,probed_at}`。单连接实现：`resolver(host)` 失败→`err="dns"` 短路；`opener(url,timeout)` 成功→`tcp=tls=1,http_status=resp.status,ok=(status<400)`；异常按类型归层：`gaierror→dns`、`ssl.SSLError→tls`、其余→`tcp`。`tls_ok` 对 http URL 记 `None`。transient（tcp/timeout）重试 ≤`retries`。
  - `fetch_text(url, *, opener=_urlopen, timeout=8.0, max_bytes=1_048_576) -> str`：GET 下载文本（截断 max_bytes，`errors="replace"` 解码），供 scan 用。
  - `fetch_bytes(url, *, opener=_urlopen, timeout=8.0, max_bytes=8_388_608) -> bytes`：GET 下载原始字节（截断 max_bytes），供 jar md5 校验用。
  - `_getaddrinfo`/`_urlopen`：真实默认实现（`jie` 上用），测试注入替身。

- [ ] **Step 1: 写失败测试**

```python
import net

def _resp(status):
    class R:
        def __init__(s): s.status = status
        def read(s, n=-1): return b""
        def close(s): pass
        def __enter__(s): return s
        def __exit__(s, *a): return False
    return R()

def test_classify_url():
    assert net.classify_url("https://x.com/api?wd={wd}") == "template"
    assert net.classify_url("http://127.0.0.1:9978/x") == "local"
    assert net.classify_url("http://192.168.1.5/a") == "local"
    assert net.classify_url("https://cdn.jsdelivr.net/gh/a/b.js") == "probe"

def test_probe_dns_fail():
    r = net.probe("https://nope.example/x", now="T",
                  resolver=lambda h, t: False)
    assert r["dns_ok"] == 0 and r["ok"] == 0 and r["err"].startswith("dns")

def test_probe_tls_fail():
    import ssl
    def boom(url, timeout): raise ssl.SSLError("bad cert")
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=boom)
    assert r["tls_ok"] == 0 and r["ok"] == 0 and r["err"].startswith("tls")

def test_probe_ok_206():
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=lambda u, t: _resp(206))
    assert r["ok"] == 1 and r["http_status"] == 206 and r["tcp_ok"] == 1

def test_probe_http_500_not_ok():
    r = net.probe("https://x.com/a", now="T",
                  resolver=lambda h, t: True, opener=lambda u, t: _resp(500))
    assert r["ok"] == 0 and r["http_status"] == 500
```

- [ ] **Step 2: 跑测试确认失败** — Run: `python -m pytest tests/test_net.py -v` — Expected: FAIL（`No module named net`）

- [ ] **Step 3: 写 net.py**

```python
#!/usr/bin/env python3
"""网络 I/O 唯一出口：URL 分类 + 分层探测 + 文本下载（可注入，便于 mock 测试）。"""
from __future__ import annotations
import socket, ssl, time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_LOCAL_PREFIXES = ("127.", "10.", "192.168.", "localhost")
_HDRS = {"Range": "bytes=0-0", "User-Agent": "ponyo-source-manager/1.0"}

def _is_local(host: str) -> bool:
    h = (host or "").lower()
    if h in ("localhost",) or any(h.startswith(p) for p in _LOCAL_PREFIXES):
        return True
    if h.startswith("172."):
        try:
            return 16 <= int(h.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    return False

def classify_url(url: str) -> str:
    if "{" in url or "}" in url:
        return "template"
    return "local" if _is_local(urlsplit(url).hostname or "") else "probe"

def _getaddrinfo(host: str, timeout: float) -> bool:
    socket.getaddrinfo(host, None)
    return True

def _urlopen(url: str, timeout: float):
    return urlopen(Request(url, headers=_HDRS), timeout=timeout)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def probe(url, *, now=None, resolver=_getaddrinfo, opener=_urlopen,
          timeout=8.0, retries=1) -> dict:
    parts = urlsplit(url)
    host, https = parts.hostname or "", parts.scheme == "https"
    r = {"dns_ok": 0, "tcp_ok": 0, "tls_ok": (0 if https else None),
         "http_status": None, "latency_ms": None, "ok": 0, "err": None,
         "probed_at": now or _now()}
    try:
        if not resolver(host, timeout):
            r["err"] = "dns: no address"; return r
    except Exception as e:  # gaierror 等
        r["err"] = f"dns: {e}"; return r
    r["dns_ok"] = 1
    attempt = 0
    while True:
        t0 = time.monotonic()
        try:
            resp = opener(url, timeout)
            try:
                status = getattr(resp, "status", None) or resp.getcode()
            finally:
                getattr(resp, "close", lambda: None)()
            r["tcp_ok"] = 1
            if https: r["tls_ok"] = 1
            r["http_status"] = status
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 1 if (status is not None and status < 400) else 0
            return r
        except HTTPError as e:  # 有响应即连通，状态码照记
            r["tcp_ok"] = 1
            if https: r["tls_ok"] = 1
            r["http_status"] = e.code
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 0
            return r
        except ssl.SSLError as e:
            r["tls_ok"] = 0; r["err"] = f"tls: {e}"; return r
        except (URLError, socket.timeout, OSError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, socket.gaierror):
                r["dns_ok"] = 0; r["err"] = f"dns: {reason}"; return r
            if isinstance(reason, ssl.SSLError):
                r["tls_ok"] = 0; r["err"] = f"tls: {reason}"; return r
            r["err"] = f"tcp: {reason}"
            if attempt < retries:
                attempt += 1; time.sleep(0.2); continue
            return r

def fetch_text(url, *, opener=_urlopen, timeout=8.0, max_bytes=1_048_576) -> str:
    resp = opener(url, timeout)
    try:
        return resp.read(max_bytes).decode("utf-8", errors="replace")
    finally:
        getattr(resp, "close", lambda: None)()

def fetch_bytes(url, *, opener=_urlopen, timeout=8.0, max_bytes=8_388_608) -> bytes:
    resp = opener(url, timeout)
    try:
        return resp.read(max_bytes)
    finally:
        getattr(resp, "close", lambda: None)()
```

- [ ] **Step 4: 跑测试确认通过** — Run: `python -m pytest tests/test_net.py -v` — Expected: PASS（5 项）

- [ ] **Step 5: 提交**

```bash
git add source-manager/net.py source-manager/tests/test_net.py
git -c commit.gpgsign=false commit -m "feat(source-manager): add net.py (url classify + layered probe, injectable)"
```

---

### Task 2: scan_security 纯匹配器 + 规则集

**Files:**
- Create: `source-manager/config/security_rules.json`
- Create: `source-manager/scan_security.py`（先只写纯函数，Task 3 加编排）
- Test: `source-manager/tests/test_scan_security.py`

**Interfaces:**
- Consumes: 无（纯函数）。
- Produces:
  - `load_rules(path: str) -> list[dict]`：读 security_rules.json，返回 `[{rule_id,severity,pattern}]`。
  - `sanitize_evidence(text: str, start: int, end: int, width: int = 160) -> str`：取 `[start,end]` 附近 `width` 窗口，去换行，并对 `token=/password=/Authorization: Basic` 后的值打 `****`。
  - `match_text_rules(text: str, rules: list[dict]) -> list[dict]`：每命中规则产出 `{rule_id,severity,evidence}`（同一 rule 只取首次命中）。
  - `check_jar_md5(declared_md5, jar_bytes, host, allow_hosts) -> dict|None`：declared 存在且不符→`{high,"jar-md5-mismatch"}`；无 declared 且 host∉allow→`{medium,"jar-unverified"}`；无 declared 且 host∈allow→`{low,"jar-unpinned"}`；declared 相符→`None`。

- [ ] **Step 1: 写 config/security_rules.json**

```json
[
  {"rule_id": "kill-process", "severity": "high", "pattern": "killProcess"},
  {"rule_id": "runtime-exec", "severity": "high", "pattern": "Runtime\\.getRuntime\\(\\)\\.exec"},
  {"rule_id": "system-exit", "severity": "high", "pattern": "System\\.exit"},
  {"rule_id": "cleartext-secret", "severity": "high", "pattern": "(?i)(token|password)\\s*[=:]\\s*[\"']?[A-Za-z0-9]{8,}"},
  {"rule_id": "package-guard", "severity": "medium", "pattern": "getPackageName"},
  {"rule_id": "intranet-dep", "severity": "medium", "pattern": "(127\\.0\\.0\\.1|192\\.168\\.|localhost|10\\.\\d{1,3}\\.)"},
  {"rule_id": "remote-eval", "severity": "medium", "pattern": "eval\\("},
  {"rule_id": "cleartext-http", "severity": "low", "pattern": "http://(?!127|localhost|192\\.168|10\\.)"}
]
```

- [ ] **Step 2: 写失败测试**

```python
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
```

- [ ] **Step 3: 跑测试确认失败** — Run: `python -m pytest tests/test_scan_security.py -v` — Expected: FAIL（`No module named scan_security`）

- [ ] **Step 4: 写 scan_security.py 纯函数段**

```python
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
```

- [ ] **Step 5: 跑测试确认通过** — Run: `python -m pytest tests/test_scan_security.py -v` — Expected: PASS（5 项）

- [ ] **Step 6: 提交**

```bash
git add source-manager/config/security_rules.json source-manager/scan_security.py source-manager/tests/test_scan_security.py
git -c commit.gpgsign=false commit -m "feat(source-manager): add security matchers (text rules + jar md5)"
```

---

### Task 3: scan_security.run_scan 编排

**Files:**
- Modify: `source-manager/scan_security.py`（加 `run_scan` + `main`）
- Test: `source-manager/tests/test_scan_security.py`（追加编排用例）

**Interfaces:**
- Consumes: `net.fetch_text`/`net.fetch_bytes`/`net.classify_url`、`common.assert_no_proxy`/`strip_md5`、Task 2 纯函数。
- Produces: `run_scan(db_path, rules_path, allowlist_path, report_path, *, fetch_text=net.fetch_text, fetch_bytes=net.fetch_bytes, now=None) -> dict`。
  流程：① `assert_no_proxy()` 非空→`raise SystemExit`；② 读 `norm_source` 每指纹的 `required_urls`(JSON) 与 `jar_md5`；③ 全局去重 URL，`classify_url != "template"` 才下载，文本类跑 `match_text_rules`，`.jar` 跑 `check_jar_md5`（用该指纹声明的 `jar_md5`）；下载失败计入 `summary.fetch_errors`，不产 finding；④ 被扫指纹先 `DELETE FROM security_finding WHERE fingerprint IN(...)` 再插新行；⑤ 含 high 的指纹 `INSERT OR REPLACE INTO list_state` 置 `deny`；⑥ 写 `report_path`（按 severity 分组，证据已脱敏）。返回 `{scanned_urls,high,medium,low,deny_fps,fetch_errors}`。

- [ ] **Step 1: 写失败测试**（追加）

```python
import json, sqlite3
import initdb, scan_security as ss

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
```

- [ ] **Step 2: 跑测试确认失败** — Run: `python -m pytest tests/test_scan_security.py::test_run_scan_flags_high_and_denies -v` — Expected: FAIL（`run_scan` 不存在）

- [ ] **Step 3: 写 run_scan + main**（在 scan_security.py 追加；顶部加 import）

```python
import argparse, sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit
import net
from common import assert_no_proxy, strip_md5

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
```

- [ ] **Step 4: 跑测试确认通过** — Run: `python -m pytest tests/test_scan_security.py -v` — Expected: PASS（6 项）

- [ ] **Step 5: 提交**

```bash
git add source-manager/scan_security.py source-manager/tests/test_scan_security.py
git -c commit.gpgsign=false commit -m "feat(source-manager): add run_scan orchestration (auto-deny on high)"
```

---

### Task 4: probe_conn.run_probe 连通性探测

**Files:**
- Create: `source-manager/probe_conn.py`
- Test: `source-manager/tests/test_probe_conn.py`

**Interfaces:**
- Consumes: `net.probe`/`net.classify_url`、`common.assert_no_proxy`。
- Produces: `run_probe(db_path, timeslot, report_path, *, probe=net.probe, now=None) -> dict`。
  流程：① `assert_no_proxy()` 非空→`raise SystemExit`；② 读 `norm_source` 每指纹 `required_urls`；③ 全局去重 URL，`classify_url`：`template`/`local` 计 `skipped` 不探测，`probe` 类调 `probe(url, now=now)` 并按 URL 缓存结果（礼貌：同 URL 只发一次）；④ 对每个 (指纹, 可探测 URL) 写一行 `conn_probe`（同 timeslot 追加）；⑤ 写报告。返回 `{total,ok,fail,skipped,timeslot}`。

- [ ] **Step 1: 写失败测试**

```python
import json, sqlite3
import initdb, probe_conn as pc

def _seed(db, rows):
    initdb.init_db(str(db))
    con = sqlite3.connect(str(db))
    for raw_id, fp, urls in rows:
        con.execute("INSERT INTO raw_source(id,import_batch,origin,site_key,raw_json)"
                    " VALUES(?,?,?,?,?)", (raw_id, "b", "o", f"k{raw_id}", "{}"))
        con.execute("INSERT INTO norm_source(raw_id,fingerprint,api_host,required_urls,"
                    "jar_md5,spider_class,category,capabilities) VALUES(?,?,?,?,?,?,?,?)",
                    (raw_id, fp, "h", json.dumps(urls), "", "", "影视", "[]"))
    con.commit(); con.close()

def test_run_probe_records_and_skips_template(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, [(1, "fp1", ["https://ok.com/a", "https://x.com/api?wd={wd}"]),
               (2, "fp2", ["https://bad.com/a"])])
    fakes = {
        "https://ok.com/a": {"dns_ok":1,"tcp_ok":1,"tls_ok":1,"http_status":200,
                             "latency_ms":12,"ok":1,"err":None,"probed_at":"T"},
        "https://bad.com/a": {"dns_ok":1,"tcp_ok":1,"tls_ok":0,"http_status":None,
                              "latency_ms":None,"ok":0,"err":"tls: bad","probed_at":"T"},
    }
    rep = tmp_path / "conn.json"
    res = pc.run_probe(str(db), "evening", str(rep),
                       probe=lambda u, now=None: fakes[u], now="T")
    assert res["ok"] == 1 and res["fail"] == 1 and res["skipped"] == 1
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT count(*) FROM conn_probe WHERE timeslot='evening'").fetchone()[0]
    con.close()
    assert n == 2  # 两个可探测 URL 各一行；模板被跳过
    assert json.loads(rep.read_text(encoding="utf-8"))["summary"]["timeslot"] == "evening"
```

- [ ] **Step 2: 跑测试确认失败** — Run: `python -m pytest tests/test_probe_conn.py -v` — Expected: FAIL（`No module named probe_conn`）

- [ ] **Step 3: 写 probe_conn.py**

（说明：v1 采用**顺序探测 + 同 host 200ms 间隔**，比并发 ≤8 更保守更礼貌，且对测试确定性友好；并发留待后续需要时再加。`sleeper` 可注入，测试传 `lambda s: None` 避免真 sleep。）

```python
#!/usr/bin/env python3
"""无代理连通性探测：DNS/TCP/TLS/HTTP 分层，按指纹写 conn_probe。"""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import net
from common import assert_no_proxy

def run_probe(db_path, timeslot, report_path, *,
              probe=net.probe, now=None, sleeper=time.sleep, pace=0.2) -> dict:
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，连通性探测中止（需无代理）。")
    now = now or datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT fingerprint, required_urls FROM norm_source").fetchall()
    fp_urls = {}
    for fp, req in rows:
        fp_urls.setdefault(fp, set()).update(json.loads(req or "[]"))
    cache, last_host_ts = {}, {}
    summary = {"total": 0, "ok": 0, "fail": 0, "skipped": 0, "timeslot": timeslot}
    inserts = []
    for fp, urls in fp_urls.items():
        for url in sorted(urls):
            summary["total"] += 1
            if net.classify_url(url) != "probe":
                summary["skipped"] += 1
                continue
            if url not in cache:
                host = urlsplit(url).hostname or ""
                prev = last_host_ts.get(host)
                if prev is not None:
                    wait = pace - (time.monotonic() - prev)
                    if wait > 0: sleeper(wait)
                cache[url] = probe(url, now=now)
                last_host_ts[host] = time.monotonic()
            r = cache[url]
            inserts.append((fp, url, timeslot, r["dns_ok"], r["tcp_ok"], r["tls_ok"],
                            r["http_status"], r["latency_ms"], r["ok"], r["err"], now))
            summary["ok" if r["ok"] else "fail"] += 1
    con.executemany("INSERT INTO conn_probe(fingerprint,target_url,timeslot,dns_ok,tcp_ok,"
                    "tls_ok,http_status,latency_ms,ok,err,probed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    inserts)
    con.commit(); con.close()
    report = {"summary": summary, "generated_at": now,
              "probes": [{"fingerprint": i[0], "target_url": i[1], "dns_ok": i[3],
                          "tcp_ok": i[4], "tls_ok": i[5], "http_status": i[6],
                          "latency_ms": i[7], "ok": i[8], "err": i[9]} for i in inserts]}
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--timeslot", required=True, choices=["morning", "noon", "evening", "night"])
    p.add_argument("--report", default="reports/connectivity-report.json")
    a = p.parse_args()
    print(json.dumps(run_probe(a.db, a.timeslot, a.report), ensure_ascii=False))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过** — Run: `python -m pytest tests/test_probe_conn.py -v` — Expected: PASS（注：测试调用未传 `sleeper`，2 个不同 host 无同 host 等待，不阻塞）

- [ ] **Step 5: 提交**

```bash
git add source-manager/probe_conn.py source-manager/tests/test_probe_conn.py
git -c commit.gpgsign=false commit -m "feat(source-manager): add run_probe (layered connectivity, polite pacing)"
```

---

### Task 5: 本地全量验证 + 部署 jie 真跑验收

**Files:**
- Modify: `source-manager/tests/conftest.py`（如需补 phase3 共享 fixture；若各测试自带 `_seed` 则本步可跳过实际改动，仅确认无重复夹具冲突）
- 无新代码；本任务是集成验收。

**Interfaces:**
- Consumes: Task 0-4 全部产物。
- Produces: `jie` 上 `sources.db` 新增两表并填充；`reports/security-report.json`、`reports/connectivity-report.json` 生成；phase3 验收结论。

- [ ] **Step 1: 本地跑全套测试** — Run: `cd source-manager && python -m pytest -v`
  Expected: PASS（phase1-2 的 20 项 + phase3 的 test_net 5 + test_scan_security 6 + test_probe_conn 1 + test_initdb 新增 1 = 33 项全绿）

- [ ] **Step 2: 本地无代理断言自测** — 临时设代理再跑，确认 abort：

```bash
cd source-manager
http_proxy=http://127.0.0.1:1 python scan_security.py --db data/sources.db 2>&1 | grep -q "中止" && echo ABORT-OK
http_proxy=http://127.0.0.1:1 python probe_conn.py --db data/sources.db --timeslot noon 2>&1 | grep -q "中止" && echo ABORT-OK
```
Expected: 两行均输出 `ABORT-OK`（有代理时脚本 SystemExit）。

- [ ] **Step 3: scp 同步到 jie**（scripts + 新配置；`allowlist.json` phase1-2 已在）

```bash
scp source-manager/net.py source-manager/scan_security.py source-manager/probe_conn.py \
    source-manager/initdb.py source-manager/schema_phase3.sql \
    jie:~/ponyo-source-manager/scripts/
scp source-manager/config/security_rules.json jie:~/ponyo-source-manager/config/
```

- [ ] **Step 4: jie 上追加建表（幂等）**

```bash
ssh jie 'cd ~/ponyo-source-manager && python3 scripts/initdb.py --db data/sources.db && \
  sqlite3 data/sources.db ".tables" | tr " " "\n" | grep -E "security_finding|conn_probe"'
```
Expected: 输出含 `security_finding` 与 `conn_probe`（不 `--reset`，phase1-2 数据保留）。

- [ ] **Step 5: jie 真跑安全扫描**

```bash
ssh jie 'cd ~/ponyo-source-manager && python3 scripts/scan_security.py \
  --db data/sources.db --rules config/security_rules.json \
  --allowlist config/allowlist.json --report reports/security-report.json'
```
Expected: 打印 `{scanned_urls, high, medium, low, deny_fps:[...], fetch_errors}`。记录 high 数与 deny 指纹数。

- [ ] **Step 6: jie 真跑连通性（记当前时段）**

```bash
ssh jie 'cd ~/ponyo-source-manager && python3 scripts/probe_conn.py \
  --db data/sources.db --timeslot evening --report reports/connectivity-report.json'
```
Expected: 打印 `{total, ok, fail, skipped, timeslot:"evening"}`。

- [ ] **Step 7: 验收断言（在 jie 上核对 7 条）**

```bash
ssh jie 'cd ~/ponyo-source-manager && \
  echo "== deny 指纹数 ==" && sqlite3 data/sources.db "SELECT count(*) FROM list_state WHERE state=\"deny\";" && \
  echo "== finding 分级 ==" && sqlite3 data/sources.db "SELECT severity,count(*) FROM security_finding GROUP BY severity;" && \
  echo "== conn_probe 行数 ==" && sqlite3 data/sources.db "SELECT count(*) FROM conn_probe WHERE timeslot=\"evening\";" && \
  echo "== 报告脱敏抽查(应为空) ==" && grep -iE "password=[A-Za-z0-9]{6}|token=[A-Za-z0-9]{6}" reports/*.json || echo "CLEAN"'
```
逐条对照：
  1. 两表存在（Step 4 已验）。
  2. 安全扫描产出 finding，high 对应指纹在 `list_state` 为 `deny`（deny 数 = high 指纹数）。
  3. jar 校验：若有 `jar-md5-mismatch` 则为 high；无声明的 jar 记 medium/low。
  4. 连通性：`conn_probe` 行数 = 各指纹可探测 URL 之和；含 `{}` 模板的 URL 不出现。
  5. 无代理：Step 2 本地已验 abort；jie 无代理故正常跑完。
  6. CVAT 无扰：`ssh jie 'docker ps --format "{{.Names}}\t{{.Status}}"'` 确认 CVAT 容器仍 Up。
  7. 报告脱敏：grep 输出 `CLEAN`（无明文 token/password）。

- [ ] **Step 8: 更新记忆 + 提交计划勾选状态**

```bash
git add docs/superpowers/plans/2026-07-25-source-manager-phase3-ab.md
git -c commit.gpgsign=false commit -m "docs: mark phase3 A+B plan tasks complete"
```
并更新 `~/.claude/.../memory/jie-server-env.md`：记 phase3 A+B 已部署、两表已建、首轮扫描/探测结论（high/deny/连通失败数）、时段标签用法，标注 C/D 仍待做。

---

## 自审对照（spec → plan）

- spec 第 2 层安全扫描 → Task 2（匹配器/jar 校验）+ Task 3（编排/自动 deny）✓
- spec 第 3 层连通性 → Task 1（分层 probe）+ Task 4（run_probe）✓
- spec 两张新表 → Task 0（schema_phase3.sql + initdb 接线）✓
- spec 规则集可配置 → Task 2（security_rules.json）✓
- spec 脱敏 → Task 2（sanitize_evidence）+ Task 5 Step7 grep 抽查 ✓
- spec 无代理 abort → 全局约束 + Task 3/4 入口 `assert_no_proxy` + Task 5 Step2 自测 ✓
- spec 多时段预埋 → conn_probe.timeslot + `--timeslot` 参数（Task 0/4）✓
- spec 不升 allow / C·D 留后 → 无升 allow 逻辑；Task 5 Step8 备注 ✓
- 类型一致性：`run_scan`/`run_probe` 签名、`probe` 返回字段（dns_ok/tcp_ok/tls_ok/http_status/latency_ms/ok/err/probed_at）在 net→scan/probe→测试三处一致 ✓






