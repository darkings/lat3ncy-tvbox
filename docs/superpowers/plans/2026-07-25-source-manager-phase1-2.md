# Ponyo 源管理系统 阶段一+二 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地建立 `source-manager/` 工具集（建库/导入/去重），完成 175 源的 SQLite 落库、静态指纹去重与粗分类，并部署到 SSH 主机 `jie`。

**Architecture:** 三个单一职责的 Python 脚本（`initdb` 建库 → `import_sources` 导入 → `dedupe` 分组），共享 `common.py`（去重指纹逻辑，复用 `tools/subscription_audit.py` 原语）。代码进 git、可 review；运行数据（`data/ reports/ logs/`）经 `.gitignore` 排除，只存在于本地测试与 `jie`。用 TDD 在本地开发，最后 scp 同步到 `jie` 运行验收。

**Tech Stack:** Python 3.11（标准库 only：`sqlite3` / `hashlib` / `json` / `urllib.parse` / `argparse`）、pytest、scp/ssh。

## Global Constraints

- Python 版本：3.11+（`jie` 为 3.11.6，本地一致）— 仅用标准库 + pytest，不引第三方运行时依赖。
- 编码：所有文件读写显式 `encoding="utf-8"`。
- 无代理：脚本不发网络请求；开头断言 `http_proxy`/`https_proxy`/`HTTP_PROXY`/`HTTPS_PROXY` 为空，非空仅告警不中断。
- 去重原语复用 `tools/subscription_audit.py` 的 `strip_md5` / `item_required_urls` / `collect_urls` / `is_critical_asset` / `iri_to_uri`，通过 `common.py` 内联同名实现（不 import 跨目录，保持 `source-manager/` 自包含）。
- 数据物理不删：raw 永不覆盖，去重只分组标记 primary。
- 提交约定：不加 `Co-Authored-By`，作者保持 `_1at3ncy`。commit 用 `git -c commit.gpgsign=false`。
- 幂等：`initdb` 表存在则跳过（`--reset` 重建）；`import_sources` 以 `import_batch` 隔离；`dedupe` 每次全量重算。
- 时间戳：由脚本运行时经 `--batch` 参数或 `datetime.now()` 在 `jie` 上取（工作流脚本内不可用 `Date.now()`，此约束仅针对本计划文档编写，不针对被生成的 Python 代码）。

## 文件结构

```text
source-manager/
├─ common.py            去重指纹 + 分类 + 无代理断言（纯函数，无副作用）
├─ schema.sql           6 表 + 3 索引 DDL
├─ initdb.py            建库（读 schema.sql，幂等，--reset）
├─ import_sources.py    导入 ponyo.json + health-final + name-map → raw/norm/health/name_map/list_state
├─ dedupe.py            读 norm_source → 分组 → dedup_group + reports/dedupe-report.json
├─ config/
│  ├─ policy.json       分类关键词规则 + primary 选择优先级（可 review 的配置）
│  ├─ allowlist.json    空模板 []
│  └─ denylist.json     空模板 []
├─ tests/
│  ├─ conftest.py       fixture：8 条精选 site（含 2 组重复 + 各类分类）
│  ├─ test_common.py    指纹 + 分类单测
│  ├─ test_import.py    导入单测（内存/临时 DB）
│  └─ test_dedupe.py    去重分组单测
├─ data/     [gitignore] 本地测试产物
├─ reports/  [gitignore]
└─ logs/     [gitignore]
```

每个文件单一职责；`common.py` 是纯函数库，被 import 与三脚本和测试共享。

---

### Task 0: 脚手架与 .gitignore

**Files:**
- Create: `source-manager/config/allowlist.json`, `source-manager/config/denylist.json`, `source-manager/config/policy.json`
- Create: `source-manager/.gitignore`
- Create: `source-manager/tests/__init__.py` (empty)

**Interfaces:**
- Produces: `config/policy.json` 结构 `{"categories": {label: [keywords]}, "primary_priority": [...]}`，被 `common.py` 与 `dedupe.py` 读取。

- [ ] **Step 1: 建目录与空配置**

```bash
mkdir -p source-manager/config source-manager/tests source-manager/data source-manager/reports source-manager/logs
printf '[]\n' > source-manager/config/allowlist.json
printf '[]\n' > source-manager/config/denylist.json
: > source-manager/tests/__init__.py
```

- [ ] **Step 2: 写 policy.json**

`source-manager/config/policy.json`：
```json
{
  "categories": {
    "儿童": ["儿童", "少儿", "亲子", "宝宝", "幼儿", "kids"],
    "动漫": ["动漫", "动画", "番剧", "anime", "追番"],
    "纪录": ["纪录", "纪实", "documentary"],
    "综艺": ["综艺", "娱乐", "show"],
    "网盘": ["网盘", "云盘", "夸克", "阿里", "百度", "quark", "ali", "115", "uc"],
    "直播": ["直播", "live", "电视", "iptv"],
    "工具": ["设置", "配置", "推送", "本地", "扫码", "登录", "cookie", "测试", "工具"],
    "影视": ["影视", "电影", "电视剧", "剧场", "vip", "港剧", "美剧"]
  },
  "category_order": ["儿童", "动漫", "纪录", "综艺", "网盘", "直播", "工具", "影视"],
  "default_category": "未分类",
  "verdict_rank": {"verified": 0, "partial": 1, "builtin-or-conditional": 2}
}
```
分类判定按 `category_order` 顺序命中即止（儿童优先于动漫，避免"儿童动画"落入动漫）。

- [ ] **Step 3: 写 source-manager/.gitignore**

```gitignore
data/
reports/
logs/
cache/
*.db
__pycache__/
.pytest_cache/
```

- [ ] **Step 4: 提交**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox
git add source-manager/config source-manager/.gitignore source-manager/tests/__init__.py
git -c commit.gpgsign=false commit -m "feat(source-manager): scaffold config, gitignore, tests dir"
```
Expected: committed；`git status` 不显示 data/reports/logs。

---

### Task 1: common.py — 去重原语与指纹

**Files:**
- Create: `source-manager/common.py`
- Test: `source-manager/tests/conftest.py`, `source-manager/tests/test_common.py`

**Interfaces:**
- Produces:
  - `strip_md5(value: str) -> str`
  - `iri_to_uri(url: str) -> str`
  - `collect_urls(value, location="root", out=None) -> dict[str, set[str]]`
  - `is_critical_asset(url: str) -> bool`
  - `item_required_urls(item: dict) -> list[str]`
  - `compute_fingerprint(site: dict) -> tuple[str, dict]` — 返回 `(sha256_hex, meta)`，`meta` 含 `api_host/required_urls/jar_md5/spider_class`
  - `classify(name: str, policy: dict) -> str`
  - `assert_no_proxy() -> list[str]` — 返回检测到的代理变量名列表（空=干净）
- Consumes: `config/policy.json`（`classify` 的 `policy` 参数）。

- [ ] **Step 1: 写 conftest.py fixture**

`source-manager/tests/conftest.py`：
```python
import json
from pathlib import Path
import pytest

PROJECT = Path(__file__).resolve().parents[2]

@pytest.fixture
def policy():
    return json.loads((PROJECT / "source-manager" / "config" / "policy.json").read_text(encoding="utf-8"))

@pytest.fixture
def sites():
    # 8 条：s0/s1 同 api 不同 name(应同指纹)；s2 带 md5 尾巴与 s3 无尾巴(应同指纹)；其余分类样本
    return [
        {"key": "a1", "name": "星辰影视", "type": 3,
         "api": "https://cdn.jsdelivr.net/gh/x/y@main/js/star.js", "ext": ""},
        {"key": "a2", "name": "极速星辰", "type": 3,
         "api": "https://cdn.jsdelivr.net/gh/x/y@main/js/star.js", "ext": ""},
        {"key": "b1", "name": "次元动漫", "type": 3,
         "api": "https://host.tld/api.php/prov/vod",
         "ext": "https://cdn.jsdelivr.net/gh/x/y@main/jar/spider.jar;md5;ABC123"},
        {"key": "b2", "name": "次元番剧", "type": 3,
         "api": "https://host.tld/api.php/prov/vod",
         "ext": "https://cdn.jsdelivr.net/gh/x/y@main/jar/spider.jar"},
        {"key": "c1", "name": "宝宝巴士儿童", "type": 3, "api": "https://k.tld/kids", "ext": ""},
        {"key": "d1", "name": "自然纪录世界", "type": 3, "api": "https://d.tld/doc", "ext": ""},
        {"key": "e1", "name": "夸克网盘", "type": 3, "api": "https://q.tld/quark", "ext": ""},
        {"key": "f1", "name": "Ponyo 设置", "type": 3, "api": "https://s.tld/settings", "ext": ""},
    ]
```

- [ ] **Step 2: 写 test_common.py（失败测试）**

`source-manager/tests/test_common.py`：
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import compute_fingerprint, classify, strip_md5, assert_no_proxy


def test_strip_md5():
    assert strip_md5("http://x/a.jar;md5;ABC") == "http://x/a.jar"
    assert strip_md5("http://x/a.jar") == "http://x/a.jar"


def test_same_api_diff_name_same_fp(sites):
    fp1, _ = compute_fingerprint(sites[0])  # 星辰影视
    fp2, _ = compute_fingerprint(sites[1])  # 极速星辰
    assert fp1 == fp2


def test_md5_tail_does_not_change_fp(sites):
    fp1, _ = compute_fingerprint(sites[2])  # ext 带 ;md5;
    fp2, _ = compute_fingerprint(sites[3])  # ext 无尾巴
    assert fp1 == fp2


def test_diff_api_diff_fp(sites):
    fp1, _ = compute_fingerprint(sites[0])
    fp3, _ = compute_fingerprint(sites[4])
    assert fp1 != fp3


def test_api_host_extracted(sites):
    _, meta = compute_fingerprint(sites[2])
    assert meta["api_host"] == "host.tld"


def test_classify_kids_before_anime(policy):
    assert classify("宝宝巴士儿童动画", policy) == "儿童"


def test_classify_categories(policy):
    assert classify("次元动漫", policy) == "动漫"
    assert classify("夸克网盘", policy) == "网盘"
    assert classify("自然纪录世界", policy) == "纪录"
    assert classify("Ponyo 设置", policy) == "工具"
    assert classify("无关键词xyz", policy) == "未分类"


def test_assert_no_proxy_returns_list():
    assert isinstance(assert_no_proxy(), list)
```

- [ ] **Step 3: 运行确认失败**

Run: `cd source-manager && python -m pytest tests/test_common.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'common'`）

- [ ] **Step 4: 写 common.py**

`source-manager/common.py`：
```python
#!/usr/bin/env python3
"""Ponyo 源管理 - 去重指纹、分类与无代理断言（纯函数，标准库 only）。

去重原语内联自 tools/subscription_audit.py，保持 source-manager/ 自包含。
"""
from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import quote, urlsplit, urlunsplit

URL_RE = re.compile(r"^https?://", re.I)
URL_FIND_RE = re.compile(r"https?://[^,\s\"']+", re.I)
ASSET_EXTENSIONS = (".json", ".js", ".py", ".txt", ".jar", ".m3u", ".m3u8")
SPIDER_RE = re.compile(r"csp_[A-Za-z0-9_]+")


def strip_md5(value: str) -> str:
    return value.split(";md5;", 1)[0]


def iri_to_uri(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit(
        (parts.scheme, host, quote(parts.path, safe="/%:@+~!$&'()*;,=-._"),
         quote(parts.query, safe="=&?/:@+~!$'()*;,%-._{}"), "")
    )


def collect_urls(value, location="root", out=None):
    if out is None:
        out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            collect_urls(item, f"{location}.{key}", out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            collect_urls(item, f"{location}[{index}]", out)
    elif isinstance(value, str):
        for candidate in URL_FIND_RE.findall(strip_md5(value.strip())):
            out.setdefault(candidate, set()).add(location)
    return out


def is_critical_asset(url: str) -> bool:
    path = urlsplit(strip_md5(url)).path.lower()
    return path.endswith(ASSET_EXTENSIONS) or "raw.githubusercontent.com" in url


def item_required_urls(item: dict) -> list[str]:
    required: list[str] = []
    for field in ("api", "jar"):
        value = item.get(field)
        if isinstance(value, str) and URL_RE.match(strip_md5(value)):
            required.append(strip_md5(value))
    for url in collect_urls(item.get("ext")):
        if is_critical_asset(url):
            required.append(url)
    return sorted(set(required))


def _jar_md5(ext) -> str:
    if isinstance(ext, str) and ";md5;" in ext:
        return ext.split(";md5;", 1)[1].strip().split(";")[0].split()[0]
    return ""


def _spider_class(item: dict) -> str:
    blob = " ".join(str(item.get(k, "")) for k in ("api", "ext"))
    m = SPIDER_RE.search(blob)
    return m.group(0) if m else ""


def compute_fingerprint(site: dict) -> tuple[str, dict]:
    api = site.get("api") or ""
    normalized_api = strip_md5(api) if isinstance(api, str) else ""
    api_host = urlsplit(normalized_api).netloc.lower() if normalized_api else ""
    required = item_required_urls(site)
    jar_md5 = _jar_md5(site.get("ext"))
    spider = _spider_class(site)
    material = "\n".join([normalized_api, api_host, "".join(required), jar_md5, spider])
    fp = hashlib.sha256(material.encode("utf-8")).hexdigest()
    meta = {"api_host": api_host, "required_urls": required,
            "jar_md5": jar_md5, "spider_class": spider}
    return fp, meta


def classify(name: str, policy: dict) -> str:
    text = (name or "").lower()
    cats = policy["categories"]
    for label in policy["category_order"]:
        for kw in cats.get(label, []):
            if kw.lower() in text:
                return label
    return policy["default_category"]


def assert_no_proxy() -> list[str]:
    return [v for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
            if os.environ.get(v)]
```

- [ ] **Step 5: 运行确认通过**

Run: `cd source-manager && python -m pytest tests/test_common.py -q`
Expected: PASS（8 passed）

- [ ] **Step 6: 提交**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox
git add source-manager/common.py source-manager/tests/conftest.py source-manager/tests/test_common.py
git -c commit.gpgsign=false commit -m "feat(source-manager): fingerprint, classify, no-proxy primitives"
```

---

### Task 2: schema.sql + initdb.py — 建库

**Files:**
- Create: `source-manager/schema.sql`
- Create: `source-manager/initdb.py`
- Test: `source-manager/tests/test_initdb.py`

**Interfaces:**
- Produces:
  - `schema.sql`：6 表 + 3 索引 DDL（表名 `raw_source/norm_source/dedup_group/health_snapshot/name_map/list_state`）。
  - `initdb.py` 函数 `init_db(db_path: str, reset: bool = False) -> None`，供 CLI 与测试调用。
  - CLI：`python3 initdb.py --db data/sources.db [--reset]`。
- Consumes: 无（首个建库步骤）。

- [ ] **Step 1: 写 schema.sql**

`source-manager/schema.sql`（与 spec 第二节逐字一致）：
```sql
CREATE TABLE IF NOT EXISTS raw_source (
  id            INTEGER PRIMARY KEY,
  import_batch  TEXT NOT NULL,
  origin        TEXT NOT NULL,
  site_key      TEXT NOT NULL,
  name          TEXT,
  type          INTEGER,
  api           TEXT,
  ext           TEXT,
  raw_json      TEXT NOT NULL,
  UNIQUE(import_batch, origin, site_key)
);
CREATE TABLE IF NOT EXISTS norm_source (
  id            INTEGER PRIMARY KEY,
  raw_id        INTEGER NOT NULL REFERENCES raw_source(id),
  fingerprint   TEXT NOT NULL,
  api_host      TEXT,
  required_urls TEXT,
  jar_md5       TEXT,
  spider_class  TEXT,
  category      TEXT,
  capabilities  TEXT
);
CREATE TABLE IF NOT EXISTS dedup_group (
  fingerprint    TEXT PRIMARY KEY,
  member_count   INTEGER NOT NULL,
  primary_raw_id INTEGER REFERENCES raw_source(id),
  member_ids     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_snapshot (
  id            INTEGER PRIMARY KEY,
  site_key      TEXT NOT NULL,
  verdict       TEXT,
  urls          TEXT,
  captured_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS name_map (
  site_key TEXT PRIMARY KEY,
  old_name TEXT,
  new_name TEXT,
  verdict  TEXT
);
CREATE TABLE IF NOT EXISTS list_state (
  fingerprint TEXT PRIMARY KEY,
  state       TEXT NOT NULL,
  reason      TEXT,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_norm_fp   ON norm_source(fingerprint);
CREATE INDEX IF NOT EXISTS idx_norm_cat  ON norm_source(category);
CREATE INDEX IF NOT EXISTS idx_raw_batch ON raw_source(import_batch);
```

- [ ] **Step 2: 写 test_initdb.py（失败测试）**

`source-manager/tests/test_initdb.py`：
```python
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initdb import init_db

EXPECTED_TABLES = {"raw_source", "norm_source", "dedup_group",
                   "health_snapshot", "name_map", "list_state"}


def _tables(db):
    con = sqlite3.connect(db)
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    con.close()
    return {r[0] for r in rows}


def test_init_creates_six_tables(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    assert EXPECTED_TABLES <= _tables(str(db))


def test_init_idempotent(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    init_db(str(db))  # 第二次不报错
    assert EXPECTED_TABLES <= _tables(str(db))


def test_reset_recreates(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO name_map(site_key) VALUES('x')")
    con.commit(); con.close()
    init_db(str(db), reset=True)
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT count(*) FROM name_map").fetchone()[0]
    con.close()
    assert n == 0
```

- [ ] **Step 3: 运行确认失败**

Run: `cd source-manager && python -m pytest tests/test_initdb.py -q`
Expected: FAIL（`No module named 'initdb'`）

- [ ] **Step 4: 写 initdb.py**

`source-manager/initdb.py`：
```python
#!/usr/bin/env python3
"""建库：读取 schema.sql 建表（幂等；--reset 重建）。"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "schema.sql"


def init_db(db_path: str, reset: bool = False) -> None:
    path = Path(db_path)
    if reset and path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    ddl = SCHEMA.read_text(encoding="utf-8")
    con = sqlite3.connect(str(path))
    try:
        con.executescript(ddl)
        con.commit()
    finally:
        con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    init_db(args.db, reset=args.reset)
    print(f"initialized {args.db}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行确认通过**

Run: `cd source-manager && python -m pytest tests/test_initdb.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: 提交**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox
git add source-manager/schema.sql source-manager/initdb.py source-manager/tests/test_initdb.py
git -c commit.gpgsign=false commit -m "feat(source-manager): schema.sql and idempotent initdb"
```

---

### Task 3: import_sources.py — 导入 175 源 + health + name-map

**Files:**
- Create: `source-manager/import_sources.py`
- Test: `source-manager/tests/test_import.py`

**Interfaces:**
- Consumes: `common.compute_fingerprint`, `common.classify`, `common.assert_no_proxy`；`initdb.init_db`；`config/policy.json`。
- Produces:
  - `import_all(db_path, ponyo_path, health_path, namemap_path, policy_path, batch, origin="ponyo.json") -> dict`（返回计数字典 `{"raw","norm","health","name_map","list_state"}`）。
  - CLI：`python3 import_sources.py --db data/sources.db --ponyo ../subscription/ponyo.json --health ../subscription/source-health-final.json --namemap ../subscription/source-name-map.json --batch 20260725-001`。
- 写入表：`raw_source`（每 site 一行，`raw_json` 存原样）、`norm_source`（指纹+分类）、`health_snapshot`、`name_map`、`list_state`（每指纹一行，state='candidate'）。

- [ ] **Step 1: 写 test_import.py（失败测试）**

`source-manager/tests/test_import.py`：
```python
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initdb import init_db
from import_sources import import_all

PROJECT = Path(__file__).resolve().parents[2]
POLICY = PROJECT / "source-manager" / "config" / "policy.json"


def _mk_inputs(tmp_path, sites):
    ponyo = tmp_path / "ponyo.json"
    ponyo.write_text(json.dumps({"sites": sites}, ensure_ascii=False), encoding="utf-8")
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"sites": [
        {"index": i, "key": s["key"], "name": s["name"],
         "verdict": "verified", "urls": []} for i, s in enumerate(sites)]},
        ensure_ascii=False), encoding="utf-8")
    namemap = tmp_path / "namemap.json"
    namemap.write_text(json.dumps([
        {"key": s["key"], "old": s["name"], "new": s["name"], "verdict": "verified"}
        for s in sites], ensure_ascii=False), encoding="utf-8")
    return ponyo, health, namemap


def test_import_counts(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    counts = import_all(str(db), str(ponyo), str(health), str(namemap),
                        str(POLICY), batch="B1")
    assert counts["raw"] == len(sites)
    assert counts["health"] == len(sites)
    assert counts["name_map"] == len(sites)
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == len(sites)
    assert con.execute("SELECT count(*) FROM norm_source").fetchone()[0] == len(sites)
    con.close()


def test_import_idempotent_same_batch(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    # 同 batch 重跑 raw 不翻倍（INSERT OR IGNORE + UNIQUE 约束）
    assert con.execute("SELECT count(*) FROM raw_source").fetchone()[0] == len(sites)
    con.close()


def test_list_state_all_candidate(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    total = con.execute("SELECT count(*) FROM list_state").fetchone()[0]
    cand = con.execute("SELECT count(*) FROM list_state WHERE state='candidate'").fetchone()[0]
    con.close()
    assert total == cand and total > 0


def test_category_assigned(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    con = sqlite3.connect(str(db))
    cats = dict(con.execute(
        "SELECT r.name, n.category FROM norm_source n JOIN raw_source r ON n.raw_id=r.id"))
    con.close()
    assert cats["夸克网盘"] == "网盘"
    assert cats["宝宝巴士儿童"] == "儿童"


def test_empty_sites_raises(tmp_path):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, [])
    import pytest
    with pytest.raises(ValueError):
        import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd source-manager && python -m pytest tests/test_import.py -q`
Expected: FAIL（`No module named 'import_sources'`）

- [ ] **Step 3: 写 import_sources.py**

`source-manager/import_sources.py`：
```python
#!/usr/bin/env python3
"""导入 ponyo.json + health + name-map 到 SQLite（幂等；单事务）。"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from common import assert_no_proxy, classify, compute_fingerprint

HERE = Path(__file__).resolve().parent


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def import_all(db_path, ponyo_path, health_path, namemap_path, policy_path,
               batch, origin="ponyo.json") -> dict:
    proxies = assert_no_proxy()
    if proxies:
        print(f"[warn] proxy env set: {proxies}")

    policy = _load(policy_path)
    ponyo = _load(ponyo_path)
    sites = ponyo.get("sites") or []
    if not sites:
        raise ValueError("ponyo.json has no sites")

    health_doc = _load(health_path)
    health_sites = health_doc.get("sites") if isinstance(health_doc, dict) else health_doc
    namemap = _load(namemap_path)
    now = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(str(db_path))
    counts = {"raw": 0, "norm": 0, "health": 0, "name_map": 0, "list_state": 0}
    try:
        con.execute("BEGIN")
        for site in sites:
            cur = con.execute(
                "INSERT OR IGNORE INTO raw_source"
                "(import_batch,origin,site_key,name,type,api,ext,raw_json)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (batch, origin, str(site.get("key", "")), site.get("name"),
                 site.get("type"), _asstr(site.get("api")), _asstr(site.get("ext")),
                 json.dumps(site, ensure_ascii=False)))
            if cur.rowcount == 0:
                continue  # 同 batch 已存在，跳过（幂等）
            raw_id = cur.lastrowid
            counts["raw"] += 1
            fp, meta = compute_fingerprint(site)
            con.execute(
                "INSERT INTO norm_source"
                "(raw_id,fingerprint,api_host,required_urls,jar_md5,spider_class,category,capabilities)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (raw_id, fp, meta["api_host"], json.dumps(meta["required_urls"], ensure_ascii=False),
                 meta["jar_md5"], meta["spider_class"], classify(site.get("name", ""), policy),
                 json.dumps([], ensure_ascii=False)))
            counts["norm"] += 1
            con.execute(
                "INSERT OR IGNORE INTO list_state(fingerprint,state,reason,updated_at)"
                " VALUES(?,?,?,?)", (fp, "candidate", "", now))

        for h in (health_sites or []):
            con.execute(
                "INSERT INTO health_snapshot(site_key,verdict,urls,captured_at)"
                " VALUES(?,?,?,?)",
                (str(h.get("key", "")), h.get("verdict"),
                 json.dumps(h.get("urls", []), ensure_ascii=False), now))
            counts["health"] += 1

        for m in namemap:
            con.execute(
                "INSERT OR REPLACE INTO name_map(site_key,old_name,new_name,verdict)"
                " VALUES(?,?,?,?)",
                (str(m.get("key", "")), m.get("old"), m.get("new"), m.get("verdict")))
            counts["name_map"] += 1

        counts["list_state"] = con.execute("SELECT count(*) FROM list_state").fetchone()[0]
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return counts


def _asstr(v):
    return v if isinstance(v, str) else (json.dumps(v, ensure_ascii=False) if v is not None else None)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--ponyo", required=True)
    p.add_argument("--health", required=True)
    p.add_argument("--namemap", required=True)
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--batch", required=True)
    args = p.parse_args()
    counts = import_all(args.db, args.ponyo, args.health, args.namemap, args.policy, args.batch)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd source-manager && python -m pytest tests/test_import.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox
git add source-manager/import_sources.py source-manager/tests/test_import.py
git -c commit.gpgsign=false commit -m "feat(source-manager): import ponyo/health/namemap into sqlite"
```

---

### Task 4: dedupe.py — 指纹分组与 primary 选择

**Files:**
- Create: `source-manager/dedupe.py`
- Test: `source-manager/tests/test_dedupe.py`

**Interfaces:**
- Consumes: `norm_source`/`raw_source`/`health_snapshot`/`name_map` 表；`config/policy.json` 的 `verdict_rank`。
- Produces:
  - `run_dedupe(db_path, policy_path, report_path) -> dict`（返回 `{"groups","duplicates","total"}`）。
  - 写 `dedup_group` 表（每指纹一行）。
  - 写 `report_path`（`reports/dedupe-report.json`）：`{"generated_at","total","groups","duplicates","details":[{fingerprint,member_count,primary_raw_id,primary_name,members:[names],reason}]}`。
  - CLI：`python3 dedupe.py --db data/sources.db --report reports/dedupe-report.json`。
- primary 选择优先级：① health verdict rank 小者优先 ② required_urls 少者 ③ name_map.new_name 非空者 ④ raw_source.id 小者。

- [ ] **Step 1: 写 test_dedupe.py（失败测试）**

`source-manager/tests/test_dedupe.py`：
```python
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from initdb import init_db
from import_sources import import_all
from dedupe import run_dedupe

PROJECT = Path(__file__).resolve().parents[2]
POLICY = PROJECT / "source-manager" / "config" / "policy.json"


def _mk_inputs(tmp_path, sites):
    ponyo = tmp_path / "ponyo.json"
    ponyo.write_text(json.dumps({"sites": sites}, ensure_ascii=False), encoding="utf-8")
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"sites": [
        {"index": i, "key": s["key"], "name": s["name"],
         "verdict": "verified", "urls": []} for i, s in enumerate(sites)]},
        ensure_ascii=False), encoding="utf-8")
    namemap = tmp_path / "namemap.json"
    namemap.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    return ponyo, health, namemap


def _prepare(tmp_path, sites):
    db = tmp_path / "t.db"
    init_db(str(db))
    ponyo, health, namemap = _mk_inputs(tmp_path, sites)
    import_all(str(db), str(ponyo), str(health), str(namemap), str(POLICY), batch="B1")
    report = tmp_path / "rep.json"
    result = run_dedupe(str(db), str(POLICY), str(report))
    return db, report, result


def test_groups_merge_known_duplicates(tmp_path, sites):
    # sites 中 s0/s1 同指纹、s2/s3 同指纹 → 8 条 → 6 组
    _, _, result = _prepare(tmp_path, sites)
    assert result["total"] == 8
    assert result["groups"] == 6
    assert result["duplicates"] == 2


def test_dedup_group_rows(tmp_path, sites):
    db, _, _ = _prepare(tmp_path, sites)
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT member_count FROM dedup_group ORDER BY member_count DESC").fetchall()
    con.close()
    assert rows[0][0] == 2  # 最大组含 2 成员


def test_report_written(tmp_path, sites):
    _, report, _ = _prepare(tmp_path, sites)
    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["total"] == 8 and doc["groups"] == 6
    assert len(doc["details"]) == 6
    dup = [d for d in doc["details"] if d["member_count"] == 2]
    assert len(dup) == 2
    # primary 必须是本组成员之一（norm_id 层面）
    assert all(len(d["members_ids"]) == 2 for d in dup)


def test_dedupe_idempotent(tmp_path, sites):
    db, report, _ = _prepare(tmp_path, sites)
    r2 = run_dedupe(str(db), str(POLICY), str(report))
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT count(*) FROM dedup_group").fetchone()[0]
    con.close()
    assert n == 6 and r2["groups"] == 6
```

- [ ] **Step 2: 运行确认失败**

Run: `cd source-manager && python -m pytest tests/test_dedupe.py -q`
Expected: FAIL（`No module named 'dedupe'`）

- [ ] **Step 3: 写 dedupe.py**

`source-manager/dedupe.py`：
```python
#!/usr/bin/env python3
"""指纹分组去重：每组选 primary，写 dedup_group + reports/dedupe-report.json。"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_dedupe(db_path, policy_path, report_path) -> dict:
    policy = _load(policy_path)
    vrank = policy.get("verdict_rank", {})
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        # 拉取每条 norm + 对应 raw + health verdict + name_map.new
        rows = con.execute("""
            SELECT n.id AS norm_id, n.fingerprint AS fp, n.required_urls AS req,
                   r.id AS raw_id, r.name AS name, r.site_key AS site_key,
                   h.verdict AS verdict, nm.new_name AS new_name
            FROM norm_source n
            JOIN raw_source r ON n.raw_id = r.id
            LEFT JOIN health_snapshot h ON h.site_key = r.site_key
            LEFT JOIN name_map nm ON nm.site_key = r.site_key
        """).fetchall()

        groups = defaultdict(list)
        for row in rows:
            groups[row["fp"]].append(row)

        def sort_key(row):
            rank = vrank.get(row["verdict"], 99)
            try:
                req_len = len(json.loads(row["req"] or "[]"))
            except json.JSONDecodeError:
                req_len = 999
            has_new = 0 if (row["new_name"]) else 1
            return (rank, req_len, has_new, row["raw_id"])

        con.execute("DELETE FROM dedup_group")
        details = []
        for fp, members in groups.items():
            ordered = sorted(members, key=sort_key)
            primary = ordered[0]
            member_ids = [m["norm_id"] for m in members]
            con.execute(
                "INSERT INTO dedup_group(fingerprint,member_count,primary_raw_id,member_ids)"
                " VALUES(?,?,?,?)",
                (fp, len(members), primary["raw_id"], json.dumps(member_ids)))
            details.append({
                "fingerprint": fp,
                "member_count": len(members),
                "primary_raw_id": primary["raw_id"],
                "primary_name": primary["name"],
                "members": [m["name"] for m in members],
                "members_ids": member_ids,
                "reason": f"verdict={primary['verdict']} req={sort_key(primary)[1]}",
            })
        con.commit()
    finally:
        con.close()

    details.sort(key=lambda d: (-d["member_count"], d["primary_name"] or ""))
    total = len(rows)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "groups": len(groups),
        "duplicates": total - len(groups),
        "details": details,
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"total": total, "groups": len(groups), "duplicates": total - len(groups)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--report", default=str(HERE / "reports" / "dedupe-report.json"))
    args = p.parse_args()
    result = run_dedupe(args.db, args.policy, args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd source-manager && python -m pytest tests/test_dedupe.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量单测**

Run: `cd source-manager && python -m pytest -q`
Expected: PASS（全部：common 8 + initdb 3 + import 5 + dedupe 4 = 20 passed）

- [ ] **Step 6: 提交**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox
git add source-manager/dedupe.py source-manager/tests/test_dedupe.py
git -c commit.gpgsign=false commit -m "feat(source-manager): fingerprint dedupe grouping and report"
```

---

### Task 5: 本地全量验收 + 部署到 jie

本任务无新代码，是端到端验收。它需要 Task 0–4 全部完成。

**Files:**
- 使用：`source-manager/*`（同步）、`subscription/ponyo.json`、`subscription/source-health-final.json`、`subscription/source-name-map.json`（作为导入输入）。
- 在 `jie` 产生（不进 git）：`~/ponyo-source-manager/data/sources.db`、`reports/dedupe-report.json`、`logs/`。

**Interfaces:**
- Consumes: 前四个任务的全部脚本与 CLI。
- Produces: `jie` 上可查询的 `sources.db` 与去重报告；本地一次真实 175 源的验收记录。

- [ ] **Step 1: 本地对真实 175 源跑一遍（冒烟）**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox/source-manager
python initdb.py --db data/sources.db --reset
python import_sources.py --db data/sources.db \
  --ponyo ../subscription/ponyo.json \
  --health ../subscription/source-health-final.json \
  --namemap ../subscription/source-name-map.json \
  --batch 20260725-001
python dedupe.py --db data/sources.db --report reports/dedupe-report.json
```
Expected: import 打印 `"raw": 175`；dedupe 打印 `"total": 175, "groups": <N<175>, "duplicates": >0`。

- [ ] **Step 2: 本地验收查询**

```bash
cd /c/Users/Jie/Projects/lat3ncy-tvbox/source-manager
python -c "import sqlite3;c=sqlite3.connect('data/sources.db');\
print('raw',c.execute('SELECT count(*) FROM raw_source').fetchone()[0]);\
print('norm',c.execute('SELECT count(*) FROM norm_source').fetchone()[0]);\
print('health',c.execute('SELECT count(*) FROM health_snapshot').fetchone()[0]);\
print('namemap',c.execute('SELECT count(*) FROM name_map').fetchone()[0]);\
print('candidate',c.execute(\"SELECT count(*) FROM list_state WHERE state='candidate'\").fetchone()[0]);\
print('groups',c.execute('SELECT count(*) FROM dedup_group').fetchone()[0]);\
print('cats',c.execute('SELECT category,count(*) FROM norm_source GROUP BY category ORDER BY 2 DESC').fetchall())"
```
Expected: raw=175, norm=175, health=175, namemap=175, candidate=groups 数, cats 打印各分类计数。

- [ ] **Step 3: 部署脚本到 jie（scp）**

```bash
ssh jie 'mkdir -p ~/ponyo-source-manager/{config,data,scripts,reports,logs}'
scp /c/Users/Jie/Projects/lat3ncy-tvbox/source-manager/*.py \
    /c/Users/Jie/Projects/lat3ncy-tvbox/source-manager/*.sql \
    jie:~/ponyo-source-manager/scripts/
scp /c/Users/Jie/Projects/lat3ncy-tvbox/source-manager/config/*.json \
    jie:~/ponyo-source-manager/config/
scp /c/Users/Jie/Projects/lat3ncy-tvbox/subscription/ponyo.json \
    /c/Users/Jie/Projects/lat3ncy-tvbox/subscription/source-health-final.json \
    /c/Users/Jie/Projects/lat3ncy-tvbox/subscription/source-name-map.json \
    jie:~/ponyo-source-manager/data/
```
Expected: 传输完成无错误。注意 scripts 与 config 分开放，`initdb.py` 默认 `--db data/sources.db` 与 `--policy config/policy.json` 是相对脚本所在目录 `scripts/`，因此在 jie 上运行时须用显式路径（见 Step 4）。

- [ ] **Step 4: 在 jie 上运行（无代理，root）**

```bash
ssh jie 'cd ~/ponyo-source-manager && \
  python3 scripts/initdb.py --db data/sources.db --reset && \
  python3 scripts/import_sources.py --db data/sources.db \
    --ponyo data/ponyo.json --health data/source-health-final.json \
    --namemap data/source-name-map.json \
    --policy config/policy.json --batch 20260725-001 && \
  python3 scripts/dedupe.py --db data/sources.db \
    --policy config/policy.json --report reports/dedupe-report.json'
```
Expected: 与 Step 1 相同的计数输出。

- [ ] **Step 5: 在 jie 上验收（8 项验收标准）**

```bash
ssh jie 'cd ~/ponyo-source-manager && ls config data scripts reports logs && \
  sqlite3 data/sources.db ".tables" && \
  sqlite3 data/sources.db "SELECT count(*) FROM raw_source;" && \
  sqlite3 data/sources.db "SELECT count(*) FROM health_snapshot;" && \
  sqlite3 data/sources.db "SELECT count(*) FROM name_map;" && \
  sqlite3 data/sources.db "SELECT count(*) FROM dedup_group;" && \
  sqlite3 data/sources.db "SELECT count(*) FROM list_state WHERE state='"'"'candidate'"'"';" && \
  head -c 300 reports/dedupe-report.json'
```
Expected（对齐 spec 五节验收表）：
1. 目录 config/data/scripts/reports/logs 均存在 ✅
2. `.tables` 列出 6 表 ✅
3. raw_source = 175 ✅
4. health_snapshot = 175，name_map = 175 ✅
5. dedup_group 组数 < 175 ✅
6. list_state candidate 数 = 组数且 > 0 ✅
7. 本地 `pytest -q` 全绿（Task 4 Step 5 已验）✅
8. import 日志无 `[warn] proxy env set`（无代理）✅

- [ ] **Step 6: 记录验收结果（可选提交）**

将 Step 5 的实际输出粘贴回 `docs/superpowers/plans/2026-07-25-source-manager-phase1-2.md` 末尾的「验收记录」小节（人工补），或仅在对话中确认。本步不强制提交（数据文件本就 gitignore）。

---

## 自检记录（Self-Review，写作者留）

- **Spec 覆盖**：架构边界→Task 0/1；6 表→Task 2；指纹+分类→Task 1；导入+list_state=candidate→Task 3；分组+report→Task 4；执行流程+幂等+无代理断言→Task 3/4/5；测试+8 项验收→Task 1–5。全部覆盖。
- **占位符扫描**：无 TBD/TODO；每个代码步骤含完整代码。已修正 Task 3 测试中多余的 `import __main__` 行、Task 4 测试中恒真断言 `... or True`。
- **类型一致性**：`compute_fingerprint` 返回 `(fp, meta)` 在 Task 1 定义、Task 3 消费一致；`run_dedupe`/`import_all`/`init_db` 签名跨任务一致。
- **报告字段**：`dedupe-report.json` 的 `details[].members_ids` 命名在 Task 4 代码与测试一致（注意不是 `member_ids`；数据库列名才是 `member_ids`）。
