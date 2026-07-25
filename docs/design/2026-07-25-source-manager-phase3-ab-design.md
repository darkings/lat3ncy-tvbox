# Ponyo 源管理系统 — 阶段三 A+B 设计（源健康引擎 v1：安全扫描 + 无代理连通性）

- 日期：2026-07-25
- 范围：PLAN.md 六层验证的**第 2 层（静态安全扫描）+ 第 3 层（无代理连通性）**
- 明确不含：第 4/5 层 drpy2 业务功能（Block C）、第 6 层 ffprobe 媒体质量（Block D）、精选 30 裁决、生成订阅、发布 GitHub。C、D 后续阶段再做。
- 关联文档：仓库根 `PLAN.md`；`docs/superpowers/specs/2026-07-24-source-manager-phase1-2-design.md`（本阶段直接建在其 DB 与 common.py 之上）
- 决策（已与用户确认）：扫描深度采用 **②**（下载远程文本 grep + jar 仅校验 md5，不反编译）；命中 high **自动 deny + 报告留证**；在 `jie` 上**真跑**网络扫描（CVAT 暂闲，风险更低，仍礼貌限流）。

## 背景与目标

阶段一+二已在 `jie` 建库并把 175 源导入、静态去重为 **148 指纹**、粗分类打标。本阶段在其上加**运行期证据采集层**：对每个指纹的唯一远程资产做静态安全扫描与无代理连通性探测，把结果沉淀到数据库与脱敏报告，并对命中高危的指纹做 `list_state=deny` 降级。本阶段**不把任何源升到 allow**（升级需 Block C+D 与多时段观察，留到 phase8）。

### 关键前提（已探明 / 已承前）

- 扫描对象是 **148 个指纹**而非 175 条原始：同指纹的远程文件字节一致，只需扫一次。去重后唯一远程文件约数十个（大量 site 共用同一 `drpy.js` / `spider.jar`）。
- `jie` 无任何代理环境变量（`assert_no_proxy()` 通过）；`raw.githubusercontent.com` 被墙但订阅已改写为 CDN（jsdelivr/ghfast/gcore 均 200）。
- ponyo.json 资产画像：全局 `spider`(jar, 带 md5)；ext 为远程 URL 43、内联 58、空 74；带 site 级 jar 字段 41；远程文件引用 `.js:62 .txt:52 .json:6 .py:5 .jar:1`。
- `common.py` 已有可复用原语：`compute_fingerprint` / `assert_no_proxy` / `strip_md5` / `iri_to_uri` / `collect_urls` / `is_critical_asset` / `item_required_urls`。

## 一、总体架构与边界

```text
norm_source ──指纹分组──▶ 每指纹唯一URL集合 ──┬─▶ [A] scan_security ─▶ security_finding
   (phase1-2 已建)                            └─▶ [B] probe_conn    ─▶ conn_probe
                                                        │
                                                  list_state 演进：
                                                  · 命中 high → deny（+留证）
                                                  · 连通性失败 → 记证据，状态不变
                                                  · 本阶段不升 allow
```

做 / 不做：
- **做**：远程 `.js/.py/.txt/.json` 下载后按规则集 grep 危险模式；jar 仅算 md5 与配置 `;md5;` 声明比对；DNS/TCP/TLS/首页/API 可达性与响应时延。
- **不做**：不反编译 jar、不执行任何规则、不跑 drpy2/node、不测媒体流、本阶段不升 allow。
- **网络纪律**：启动先 `assert_no_proxy()`，有代理直接 abort；并发 ≤8，同 host 串行 + 200ms 间隔；GET `Range: bytes=0-0`，超时 8s，最多 1 次重试。

## 二、数据库变更（新增两表，沿用 IF NOT EXISTS，不动旧表）

新增 `source-manager/schema_phase3.sql`，由 `initdb.py` 追加执行（与 phase1-2 schema 幂等叠加）。

```sql
CREATE TABLE IF NOT EXISTS security_finding (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  target_url  TEXT,
  asset_type  TEXT,            -- js|py|txt|json|jar
  rule_id     TEXT NOT NULL,   -- kill-process / cleartext-secret / jar-md5-mismatch ...
  severity    TEXT NOT NULL,   -- high|medium|low
  evidence    TEXT,            -- 脱敏片段：截断 + 敏感值打码，绝不落 token/密码明文
  scanned_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sf_fp ON security_finding(fingerprint, severity);

CREATE TABLE IF NOT EXISTS conn_probe (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  target_url  TEXT NOT NULL,
  timeslot    TEXT NOT NULL,   -- morning|noon|evening|night，为 phase8 多时段聚合铺路
  dns_ok INT, tcp_ok INT, tls_ok INT,
  http_status INT, latency_ms INT,
  ok  INT NOT NULL,            -- 综合可达（1/0）
  err TEXT,
  probed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_fp ON conn_probe(fingerprint, timeslot);
```

写入语义：
- `security_finding`：每轮重扫前按被扫指纹 **DELETE 旧行再插新行**（结果反映当前规则集与当前远程内容）。
- `conn_probe`：每时段 **追加**一行/URL（保留历史，供 phase8 跨时段稳定性聚合）。
- `list_state`：命中 high 的指纹置 `deny`，并在 `reason`/`updated_at` 记来源 finding。连通性失败**不**改状态（仅证据）。

## 三、安全规则集（config/security_rules.json，可调不改码）

文本类（对下载到的 `.js/.py/.txt/.json` 逐规则正则匹配，分级）：

| severity | rule_id 示例 | 模式（示意） |
|---|---|---|
| high | kill-process | `killProcess` / `System\.exit` |
| high | runtime-exec | `Runtime\.getRuntime\(\)\.exec` |
| high | apk-drop | 下载 `\.apk` 并触发安装 |
| high | cleartext-secret | 硬编码 `token=`/`password=`/`Authorization:\s*Basic` **且** 疑似私有域上传 |
| medium | package-guard | `getPackageName` + 条件退出组合 |
| medium | intranet-dep | `127\.0\.0\.1` / `192\.168\.` / `10\.\d` / `localhost` |
| medium | remote-eval | `eval\(` 大段远程代码 |
| low | cleartext-http | 非本地 `http://` |
| low | suspicious-redirect | 可疑短链跳转 |

JAR（不反编译）：算文件 md5 与配置 `;md5;` 声明比对——
- 声明存在且**不符** → high `jar-md5-mismatch`（篡改嫌疑）；
- **无**声明且非白名单域 → medium `jar-unverified`；
- 白名单域无声明 → low `jar-unpinned`。

规则集为纯数据文件，`allowlist.json` 提供 jar 白名单域。命中任一 **high** → 该指纹 `list_state=deny`。证据入库前统一脱敏：截断到 ~160 字符，对疑似密钥/token 值做 `****` 打码。

## 四、连通性探测（无代理，礼貌并发）

- 每 URL 分层：DNS 解析 → TCP 连接 → TLS 握手 → HTTP GET(`Range: bytes=0-0`)。逐层记 `*_ok`，任一层失败即短路，`err` 记失败层。
- 跳过含 `{...}` 模板占位的 URL（无法确定实参）；`localhost`/内网 URL 归安全侧（intranet-dep），连通性侧标记 skip。
- `latency_ms` 记完成到首字节耗时。综合 `ok = tls_ok AND http_status<400`（媒体资源允许 200/206）。
- 并发 ≤8，**同 host 串行 + 200ms 间隔**；超时 8s，失败重试 ≤1。
- I/O 全部藏在可注入的 `net.fetch(url)->resp` / `net.probe(url)->dict` 后：本地测试注入 fixture/mock，`jie` 上注入真实实现。

## 五、文件、命令与产物

新增文件（均在 `source-manager/`，代码入 git，data/reports/logs 仍 gitignore）：

```
net.py                 # fetch / probe / URL 归一，网络 I/O 唯一出口（可注入）
scan_security.py       # run_scan(db, rules_path, report_path, fetch=...) -> dict
probe_conn.py          # run_probe(db, timeslot, report_path, probe=...) -> dict
schema_phase3.sql      # security_finding + conn_probe
config/security_rules.json
tests/test_net.py / test_scan_security.py / test_probe_conn.py   # 全 mock 网络
```

命令（在 jie `~/ponyo-source-manager/scripts`）：
- `python initdb.py --db data/sources.db`（幂等追加 phase3 两表）
- `python scan_security.py --db ... --rules config/security_rules.json --report reports/security-report.json`
- `python probe_conn.py --db ... --timeslot evening --report reports/connectivity-report.json`

产物（脱敏 JSON）：
- `reports/security-report.json`：按 severity 分组，`{summary:{high,medium,low,deny_fps}, findings:[...]}`，证据已打码。
- `reports/connectivity-report.json`：按指纹分组，`{summary:{total,ok,fail,skipped,timeslot}, probes:[...]}`。

## 六、测试与验收

TDD 同 phase1-2：先写失败测试 → 跑红 → 实现 → 跑绿 → 提交（`git -c commit.gpgsign=false`，author `_1at3ncy`，**无 Co-Authored-By**）。网络全程 mock，不在单测里发真请求。

验收（本地 mock 全绿后，在 jie 真跑）：
1. `initdb` 幂等：重复执行不报错，两新表存在。
2. 安全扫描：注入含 `System.exit` 的 mock 文件 → 产出 high finding 且对应指纹 `list_state=deny`；证据字段无明文密钥。
3. jar 校验：篡改 md5 的 mock → high `jar-md5-mismatch`。
4. 连通性：mock 一个 TLS 失败 + 一个 200 → `conn_probe` 各记一行，`ok` 正确；含 `{}` 模板的 URL 被 skip。
5. `assert_no_proxy`：设了代理环境变量时两脚本都 abort。
6. jie 真跑：扫描 148 指纹的唯一资产，输出两份报告；记录 high 数、deny 指纹数、连通失败指纹数；确认 CVAT 无异常、无代理告警。
7. 报告脱敏抽查：grep 报告确认无 token/password/完整播放临时 URL 明文。

## 七、明确留待后续（不在本阶段）

- Block C（drpy2 业务功能，第 4/5 层）：需部署 node + drpy2，与 CVAT 共存的方式（Docker vs 裸机）另行决策。
- Block D（ffprobe 媒体质量，第 6 层）：需装 ffmpeg（EPOL 可装）。
- 多时段调度（phase8）：`probe_conn.py` 已带 `--timeslot` 参数与历史留存，cron 四时段编排留到 phase8。
- allow 升级与精选 30 裁决：需 C+D+≥7 天多时段证据齐备后进行。
