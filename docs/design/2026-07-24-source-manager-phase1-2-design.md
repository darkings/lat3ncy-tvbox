# Ponyo 源管理系统 — 阶段一+二设计（服务器地基：数据库与导入去重）

- 日期：2026-07-24
- 范围：PLAN.md 的**阶段一（环境确认收尾）+ 阶段二（部署数据库与导入去重）**
- 明确不含：drpy2、真实测速、ffprobe、精选 30 裁决、生成订阅、发布 GitHub、App Beauty 2.5
- 关联文档：仓库根 `PLAN.md`（第二、三、四、六章）

## 背景与目标

`PLAN.md` 描述的是一套长期运行的源管理平台（22 章、7 阶段、含 ≥7 天观察期），无法一次建成。本设计只交付其**服务器地基**：在 SSH 主机 `jie` 上建立目录骨架 + SQLite 数据库，把现有 175 个源及配套报告导入，并完成**静态指纹去重**与**粗分类打标**，为后续阶段（测速、精选、发布）准备好数据底座。

### 环境现状（已探明）

`jie` 主机：root + sudo NOPASSWD；无 http(s)_proxy（符合 PLAN 无代理要求）；磁盘 40G 余 24G；已装 `python3 3.11.6` / `sqlite3` / `docker 29.6.1` / Compose v5.3.1；缺 `node` / `ffprobe` / `gh`（均服务于后续阶段，本阶段不装）。Git 推送当前不通（`Host key verification failed`，无 `GITHUB_TOKEN`）——本阶段不涉及推送，留待发布阶段解决。

本地仓库 git 只跟踪 `releases/`、`subscription/`、`tools/` + 根 `README.md`/`LICENSE`；`app/` 等源码目录被 `.gitignore` 忽略（符合 PLAN「不提交 App 源码」）。

### 现有可复用资产

- `subscription/ponyo.json`：175 sites / 10 lives / 29 parses；site 字段 `key/name/type/api/ext/searchable/quickSearch/changeable`（type：165 个=3 即 drpy_js，9 个=1，1 个=0）。
- `subscription/source-health-final.json`：175 条 `{index,key,name,verdict,urls}`（verified 99 / builtin-or-conditional 74 / partial 2）。
- `subscription/source-name-map.json`：175 条 `{key,old,new,verdict}`。
- `tools/subscription_audit.py`：**已有**去重原语 `normalized_key` / `merge_unique` / `item_required_urls` / `strip_md5` / `is_critical_asset` / `iri_to_uri`，本设计复用而非重写。

## 一、总体架构与边界

```text
本地仓库 (git 版本管理)                          SSH 主机 jie (执行 + 数据)
──────────────────────────────────           ──────────────────────────────
source-manager/                                ~/ponyo-source-manager/
 ├ schema.sql         ┐                          ├ config/   allowlist/denylist/policy.json
 ├ initdb.py          │                          ├ data/     ← sources.db        [gitignore]
 ├ import_sources.py  ├─ 提交到 git ─ scp同步▶   ├ scripts/  ← 同步来的 .py/.sql
 ├ dedupe.py          │                          ├ reports/  ← 导入/去重报告 JSON  [gitignore]
 ├ common.py          ┘                          └ logs/                          [gitignore]
 ├ config/*.json      ← 也提交(可review)
 ├ data/    [gitignore]   本地跑测试时的产物
 ├ reports/ [gitignore]
 └ logs/    [gitignore]
subscription/ponyo.json  ── 作为导入输入(已在git) ──▶  (在 jie 上读入建库)
```

**边界原则：**

- **代码 + 配置模板**（`source-manager/*.py`、`schema.sql`、`config/*.json`）进 git，可 review、有版本管理。
- **运行数据**（`data/ reports/ logs/ cache/`）通过 `.gitignore` 排除，只存在于本地测试目录和 `jie`。
- **单一职责三脚本**：`initdb`（建库）→ `import_sources`（导入）→ `dedupe`（分组），互不耦合、可独立运行与测试。
- **复用而非重写**：去重指纹逻辑从 `tools/subscription_audit.py` 抽到 `common.py` 共享。
- **同步**：`scp` 推 `source-manager/` 到 `jie:~/ponyo-source-manager/scripts/`；`ponyo.json` 作为导入输入。
- **提交约定**：不加 `Co-Authored-By`，作者保持 `_1at3ncy`。

## 二、SQLite 表结构（`schema.sql`）

```sql
-- 1. 原始源快照：一次导入 = 一批 raw 记录，保留原样，永不覆盖
CREATE TABLE raw_source (
  id            INTEGER PRIMARY KEY,
  import_batch  TEXT NOT NULL,          -- 导入批次时间戳，如 20260724-001
  origin        TEXT NOT NULL,          -- 来源: 'ponyo.json' / 'jsm' / 'fty'
  site_key      TEXT NOT NULL,          -- 原 key
  name          TEXT,                   -- 原 name
  type          INTEGER,                -- 0/1/3
  api           TEXT,
  ext           TEXT,                   -- 原始 ext(JSON 字符串或 URL)
  raw_json      TEXT NOT NULL,          -- 整条 site 的原始 JSON
  UNIQUE(import_batch, origin, site_key)
);

-- 2. 规范化源：每条 raw 计算出指纹后的标准视图(去重的输入)
CREATE TABLE norm_source (
  id            INTEGER PRIMARY KEY,
  raw_id        INTEGER NOT NULL REFERENCES raw_source(id),
  fingerprint   TEXT NOT NULL,          -- api+ext+关键URL 归一化后的 SHA-256
  api_host      TEXT,                   -- api 主机名
  required_urls TEXT,                   -- item_required_urls() 结果, JSON 数组
  jar_md5       TEXT,                   -- ext 里的 ;md5; 摘要(若有)
  spider_class  TEXT,                   -- 爬虫类名(若可解析)
  category      TEXT,                   -- 分类标签: 影视/动漫/纪录/综艺/儿童/网盘/工具/直播/未分类
  capabilities  TEXT                    -- 能力标签 JSON: ["搜索","少儿分类",...]
);

-- 3. 去重分组：指纹相同的 norm_source 归为一组，组内选一个 primary
CREATE TABLE dedup_group (
  fingerprint    TEXT PRIMARY KEY,
  member_count   INTEGER NOT NULL,
  primary_raw_id INTEGER REFERENCES raw_source(id),  -- 组内保留的代表
  member_ids     TEXT NOT NULL          -- 组内所有 norm_source.id, JSON 数组
);

-- 4. 健康快照：导入 source-health-final.json 的 verdict/urls(本阶段只落库,不测速)
CREATE TABLE health_snapshot (
  id            INTEGER PRIMARY KEY,
  site_key      TEXT NOT NULL,
  verdict       TEXT,                   -- verified / builtin-or-conditional / partial
  urls          TEXT,                   -- JSON 数组
  captured_at   TEXT NOT NULL
);

-- 5. 名称映射：导入 source-name-map.json
CREATE TABLE name_map (
  site_key TEXT PRIMARY KEY,
  old_name TEXT,
  new_name TEXT,
  verdict  TEXT
);

-- 6. 列表状态：allowlist / denylist / candidate 三态(PLAN 第三、六章)
CREATE TABLE list_state (
  fingerprint TEXT PRIMARY KEY,
  state       TEXT NOT NULL,           -- 'candidate' | 'allow' | 'deny'
  reason      TEXT,                    -- 入 deny 的原因(如触发安全规则)
  updated_at  TEXT NOT NULL
);

CREATE INDEX idx_norm_fp   ON norm_source(fingerprint);
CREATE INDEX idx_norm_cat  ON norm_source(category);
CREATE INDEX idx_raw_batch ON raw_source(import_batch);
```

**设计要点：**

- **raw 永不覆盖**：每次导入是新 `import_batch`，历史保留，便于对比上游变化、支撑回滚。
- **norm 与 raw 分离**：raw 存原样，norm 存计算结果；指纹逻辑改进时重算 norm 不动 raw。
- **dedup_group 只分组不删除**：物理不删任何源，只标记「组内代表」，可追溯。
- **list_state 以 fingerprint 为键**：去重后同一指纹可能对应多个名字，状态绑在指纹上。
- health/name_map 本阶段**只落库不计算**（测速属阶段三）。

## 三、标准化与去重指纹算法（`common.py` + `dedupe.py`）

### 指纹构成 `compute_fingerprint`（复用 `subscription_audit.py` 原语）

```text
输入一条 site: {key, name, type, api, ext, ...}
  ├─ 1. normalized_api = strip_md5(api) 去 ";md5;xxx" 尾巴
  ├─ 2. api_host = urlsplit(api).netloc.lower()
  ├─ 3. required_urls = item_required_urls(site) 的每个 URL 归一化(去 md5、IRI→URI、查询串排序)
  ├─ 4. jar_md5 = ext 中 ";md5;" 后的摘要(若有)
  └─ 5. spider_class = ext 中 "csp_XXX" / api 中类名(正则提取, 无则空)

fingerprint = SHA-256( "\n".join([
    normalized_api, api_host, "".join(sorted(required_urls)), jar_md5, spider_class ]) )
```

### 去重分组 `dedupe.py`

```text
1. 读 norm_source 全部记录
2. 按 fingerprint 分组
3. 每组选 primary, 优先级:
     ① health verdict: verified > partial > builtin-or-conditional
     ② required_urls 更少(依赖更简单更稳)
     ③ name_map.new_name 非空者优先(已规范命名)
     ④ raw_source.id 最小(最早导入, 稳定 tie-breaker)
4. 写 dedup_group: fingerprint / member_count / primary_raw_id / member_ids
5. 输出 reports/dedupe-report.json:
     总组数、被合并掉的重复数、每组(指纹/成员名字/选中primary/选择理由)
```

### 本阶段取舍（已确认）

- **静态指纹去重**：只纳入配置本身可算的维度（api、api_host、ext 依赖 URL、JAR 哈希、爬虫类名）。PLAN 第四章的「搜索请求格式、返回内容相似度」需实际发请求，属阶段三，本阶段不做。
- **粗分类**：用关键词规则从 `name` 猜初始 `category`（动漫/动画/少儿/儿童→动漫或儿童；纪录→纪录；综艺→综艺；网盘/云/夸克/阿里→网盘；直播/live→直播；其余→影视/未分类），仅作候选标签，**不做精选 30 的最终裁决**（精选结合测速在后续阶段）。

## 四、执行流程、错误处理与幂等

### 运行顺序（在 `jie` 上，无代理）

```text
scp source-manager/* + subscription/ponyo.json ──▶ jie:~/ponyo-source-manager/
  ├─ python3 initdb.py         建库(幂等: 表不存在才建, --reset 可重建)
  ├─ python3 import_sources.py 导入 ponyo.json(175)+health-final+name-map
  │                            → raw_source/norm_source/health_snapshot/name_map
  │                            → list_state 全部初始化为 'candidate'(新源先隔离)
  └─ python3 dedupe.py         分组 → dedup_group → dedupe-report.json
```

### 错误处理原则

- **幂等**：`initdb` 表已存在则跳过（`--reset` 显式重建）；`import_sources` 以 `import_batch` 时间戳隔离批次，重复跑不污染旧批次；`dedupe` 每次 `DELETE FROM dedup_group` 后全量重算。
- **原子性**：每脚本单事务，失败 `ROLLBACK`，不留半截数据。
- **输入校验**：`ponyo.json` 解析失败或 `sites` 为空 → 立即报错退出，不建空库。
- **编码**：全程 `encoding='utf-8'`。
- **时间戳**：`import_batch`/`captured_at` 由脚本在 `jie` 运行时读取系统时间。
- **日志**：每步向 `logs/` 写一行摘要（条数、耗时、错误数）。
- **无代理断言**：脚本开头检查 `http_proxy`/`https_proxy` 为空，非空则警告（为阶段三铺路；本阶段脚本不发网络请求，纯读 JSON + 写 SQLite）。

## 五、测试与验收

### 测试策略（TDD，本地跑，不依赖 jie）

- 小型 fixture（从 `ponyo.json` 截取 ~8 条，含 2 组已知重复 + 各类分类样本）。
- `test_common.py`：相同 api/ext 不同 name → 同指纹；不同 api → 不同指纹；md5 尾巴不影响指纹。
- `test_dedupe.py`：已知 2 组重复正确合并；primary 选择遵守优先级；member_count 正确。
- `test_import.py`：175 条全部入库；重复跑不产生重复行；health/name_map 计数匹配。

### 验收标准（本阶段完成 = 全绿）

| # | 验收项 | 判定 |
|---|---|---|
| 1 | `jie:~/ponyo-source-manager/` 骨架建成 | `ls` 见 config/data/scripts/reports/logs |
| 2 | `sources.db` 建库成功，6 张表存在 | `sqlite3 .tables` |
| 3 | 175 条 raw_source 全部导入 | `SELECT count(*)` = 175 |
| 4 | health(175) + name_map(175) 导入 | 计数匹配 |
| 5 | dedupe 产出分组报告，重复被识别 | `dedupe-report.json` 组数 < 175 |
| 6 | list_state 全部初始化为 candidate | `count WHERE state='candidate'` |
| 7 | 本地单测全绿 | `pytest` |
| 8 | 无代理断言通过 | 脚本日志确认 |

### 本阶段明确不做（防范围蔓延）

drpy2、真实测速、ffprobe、精选 30 裁决、生成订阅、发布 GitHub、装 node/ffprobe/gh、App Beauty 2.5。
