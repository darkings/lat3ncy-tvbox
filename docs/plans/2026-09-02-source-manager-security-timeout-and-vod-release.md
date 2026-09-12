# Source Manager：scan_security 超时修复与点播精选发布闭环（2026-09-02）

版本：2026-09-02  
适用项目：`source-manager`  
生产主机：`jie`，正式部署目录 `/opt/ponyo-source-manager`  
数据库：`/opt/ponyo-source-manager/data/sources.db`

本文记录 2026-09-02 会话中完成的 `scan_security` 超时诊断、最小修复、测试与线上部署，以及点播精选发布闭环的当前阻断和下一步执行顺序。不覆盖 `docs/plans/2026-08-01-source-manager-session-log.md` 的历史日记。

约束（全程有效）：

- 最小改动
- 先测试后部署
- 不执行全量部署
- 不修改 `Hawk2.xml`
- 不绕过安全门槛
- 不批量把 `candidate` 改成 `allow`
- 不执行 `scheduler --phase full`

---

## 1. 事件背景与线上症状

点播精选发布闭环仍失败。优先问题是 `scan_security` 超时被杀，其次才是精选源数量不足。

此前全量任务：

| 项 | 值 |
| --- | --- |
| scheduler PID | `3487363` |
| `scan_security` | 旧代码跑到 2700 秒后被杀，`returncode=-9` |
| 当时后续阶段 | 已进入 `drpy_runner`（此前 PID `3541586`） |
| SQLite | `journal_mode=delete`，并发写入风险高，因此没有并行重跑安全扫描 |

发布门禁失败口径：

- 普通精选：9，不是 29
- 计入指标的 VOD：10，不是 30

---

## 2. 诊断数据

### 2.1 库存漏斗

| 指标 | 数值 |
| --- | ---: |
| `raw_source` | 7575 |
| `norm_source` | 7575 |
| 唯一 fingerprint | 7575 |
| candidate | 6916 |
| deny | 644 |
| allow | 15 |

补充：

- 当前 allow 全部为「未分类」
- 生成后同站点去重只剩 10 个
- 最终 staging 约 12 个站点：工具（豆瓣、本地）+ 儿童聚合 1 + 普通点播 9 + 正式直播 1

### 2.2 JAR 抓取估算（修复后）

| 指标 | 数值 |
| --- | ---: |
| JAR 行 | 8989 |
| 唯一 JAR URL | 226 |
| 最近冷却成功 URL | 87 |
| 最近冷却失败 URL | 68 |
| 本地缓存 URL | 3 |
| 预计需网络抓取的唯一 JAR URL | 68 |
| 最坏耗时 | 约 9–27 分钟，低于 2400 秒预算 |

### 2.3 晋级卡点

最近 `promote_demote` 结果：

```json
{"evaluated":7575,"promoted":0,"demoted":0}
```

有多个高分候选只缺连通性时段覆盖，例如：

| fingerprint 前缀 | 分数 |
| --- | ---: |
| `2dab46db77a8` | 97.87 |
| `3b33cbc48c59` | 97.76 |
| `e28b5d95e791` | 97.76 |
| `18e5af049de3` | 96.04 |

当前门槛仍要求：

- 观察至少 7 天
- 至少 3 个探测时段
- 最新 `hard_pass`
- allow 上限 30
- 每日最多变更 3 个

不能绕过这些门槛，也不能直接批量将 candidate 改为 allow。

---

## 3. `scan_security` 最小修复

本地文件：

```text
C:\Users\Jie\Projects\lat3ncy-tvbox\source-manager\src\ponyo_source_manager\probes\scan_security.py
```

线上文件：

```text
/opt/ponyo-source-manager/src/ponyo_source_manager/probes/scan_security.py
```

线上备份：

```text
/opt/ponyo-source-manager/src/ponyo_source_manager/probes/scan_security.py.bak-20260902
```

修复内容：

- `JAR_FETCH_TIMEOUT_SECONDS = 8.0`
- `SCAN_FETCH_DEADLINE_SECONDS = 2400.0`
- `FETCH_COOLDOWN_HOURS = 24.0`
- 同一 `effective_url` 跨 fingerprint 查询 24 小时内 `fetch_status in ('fetched', 'failed')`，避免重复网络请求
- 同一轮通过 `binary_cache` 复用 JAR
- 本地 approved JAR cache 仍优先
- 到达总预算后停止新网络请求，但继续写库并生成报告
- **未改变安全判定逻辑**

线上语法检查通过，常量验证为：

```text
8.0 2400.0 24.0
```

---

## 4. 测试结果

执行命令：

```powershell
$env:PYTHONPATH = "C:\Users\Jie\Projects\lat3ncy-tvbox\source-manager\src"
python -m pytest -q tests/test_scan_security.py tests/test_scorer.py tests/test_release_validation.py
```

结果：

```text
37 passed in 3.88s
```

新增测试覆盖：

- 跨 fingerprint 的最近失败 JAR 冷却
- 同一轮跨 fingerprint JAR 字节复用
- 总预算耗尽后不再发网络请求，但仍生成报告

---

## 5. 线上部署与 waiter

已上传修复后的 `scan_security.py`。未执行全量部署，未改 `Hawk2.xml`。

已挂起等待脚本：

| 项 | 值 |
| --- | --- |
| 线上脚本 | `/tmp/_tmp_wait_scan_security.sh` |
| waiter PID | `3547153` |
| 日志 | `/opt/ponyo-source-manager/logs/scan_security_manual_20260902.log` |

脚本设计：

1. 等 scheduler PID `3487363` 退出
2. 若没有新的 scheduler 或 `scan_security`，单独执行安全扫描
3. 不杀现有进程
4. 不执行 `scheduler --phase full`

需要后续确认 waiter、scheduler、`drpy_runner` 状态，以及 `security-report.json` 是否生成。

---

## 6. 精选配额与分类问题

发布硬编码要求位于：

```text
source-manager/src/ponyo_source_manager/publishing/release.py
```

要求：

- 普通精选恰好 29
- 儿童源恰好 1
- 普通 + 儿童 VOD 恰好 30
- 正式直播恰好 1
- 分类配额：影视 20、动漫 4、纪录 2、综艺 2、听书短剧 1

当前缺口：

- 普通精选 9 ≠ 29
- 计入指标的 VOD 10 ≠ 30
- 「纪录」分类为 0；即使数量问题解决，仍会触发分类配额失败

评分/晋级逻辑位于：

```text
source-manager/src/ponyo_source_manager/scoring/promote_demote.py
```

---

## 7. 下一步执行顺序

严格按顺序做，前一步未确认完成前不要跳到精选补量或发布。

### 第 1 步：确认 waiter / scheduler / drpy_runner 是否已结束

只读检查，不杀进程，不启动全量调度。

需要确认：

- waiter PID `3547153` 是否还在
- scheduler PID `3487363` 是否已退出
- 是否出现新的 scheduler
- `drpy_runner` 是否已结束
- 是否已有独立 `scan_security` 在跑

### 第 2 步：确认手动 `scan_security` 是否生成报告

目标文件：

```text
/opt/ponyo-source-manager/reports/security-report.json
```

同时核对：

```text
/opt/ponyo-source-manager/logs/scan_security_manual_20260902.log
```

### 第 3 步：检查报告关键字段

必须看：

- `jar_fetch_errors`
- `skipped_recent_failed_jar`
- `skipped_recent_fetched_jar`
- `skipped_fetch_deadline`
- `scanned_urls`

判断：

- 若扫描完整结束且报告生成：安全超时优先项关闭，进入第 4 步
- 若仍被杀、无报告、或 `skipped_fetch_deadline` 异常偏高：先修扫描稳定性，不进入精选补量
- 若只是冷却跳过较多但报告完整：视为预期，进入第 4 步

### 第 4 步：分析精选 15→9 的同站点去重与正式 29 配额

只分析，不改门槛，不手工 allow。

重点：

- 当前 allow=15，为何生成后同站点去重只剩 10，普通点播只剩 9
- `release.py` 硬编码「恰好 29」与库存现实是否匹配
- 发布层 `SITE_GROUPS` / 同站点去重是否把可用入口折叠过多

### 第 5 步：补齐「纪录」分类来源

数量问题解决后，分类配额仍会失败，因为当前「纪录」= 0。

要求：

- 找出可晋升或接近晋升的纪录源
- 不降低安全/播放门槛
- 不手工伪造分类

### 第 6 步：分析 hard-pass 缺失和时段覆盖

高分候选缺的是连通性时段覆盖，不是分数本身。

要求：

- 查这些高分 fingerprint 缺的具体时段
- 等自然探测补齐，或只做最小探测补证
- 不降低 7 天 / 3 时段 / `hard_pass` / 安全门槛

### 第 7 步：仅在门禁可满足时再谈正式发布

在普通精选 29、儿童 1、VOD 30、直播 1、分类 20/4/2/2/1 未同时满足前，不执行正式发布，不覆盖旧订阅。

---

## 8. 风险和明确禁止事项

- 不修改 `Hawk2.xml`
- 不执行全量部署
- 不执行 `scheduler --phase full`
- 不杀现有 scheduler / `drpy_runner` / waiter，除非确认僵尸且用户明确要求
- 不并行对 `sources.db` 做第二路写入（当前 `journal_mode=delete`）
- 不降低功能成功率、播放成功率、高清比例、时长检测、安全审计、7 天观察门槛
- 不手工把 candidate 设置为 allow
- 不手工伪造 `hard_pass`
- 不绕过 JAR 安全判定
- 不把未知/高危 JAR 标为通过

---

## 9. 一句话判断

手动 `scan_security` 已 `rc=0` 并写出 `security-report.json`；15→9 是发布层 `SITE_GROUPS` 折叠，不是 join 丢失。最新评分 `hard_pass=0`，无可晋级 candidate，纪录名称库存为 0。未满足 29/1/30/1 与分类 20/4/2/2/1 前不发布。

---

## 10. 2026-09-02 晚间只读检查（未完成第 1 步）

按第 7 节顺序，本轮只做第 1 步：确认 waiter / scheduler / `drpy_runner`。未杀进程，未部署，未改 `Hawk2.xml`，未跑 `scheduler --phase full`，未手工 allow。

SSH 配置：

```text
Host jie
HostName 116.196.98.184
User root
Port 22
IdentityFile ~/.ssh/id_rsa
ConfigFile C:\Users\Jie\iCloudDrive\Backups\ssh\config
```

实际命令与结果：

```text
ssh -F "...\ssh\config" -o BatchMode=yes -o ConnectTimeout=15 jie "..."
# ssh: connect to host 116.196.98.184 port 22: Connection timed out

ssh -F "...\ssh\config" -o BatchMode=yes -o ConnectTimeout=25 jie "..."
# banner exchange: Connection to UNKNOWN port -1: Connection timed out

ssh -F "...\ssh\config" -o BatchMode=yes -o ConnectTimeout=12 jie "echo connected"
# Connection timed out

ssh -F "...\ssh\config" -o BatchMode=yes -o ConnectTimeout=8 jie "..."
# Connection timed out

# 对照：dininghall 43.136.136.154:22 同样超时，不是单主机偶发
```

因此 **第 1 步未完成**：

| 检查项 | 状态 |
| --- | --- |
| waiter PID `3547153` | 未知 |
| scheduler PID `3487363` | 未知 |
| 是否出现新 scheduler | 未知 |
| `drpy_runner` | 未知 |
| 独立 `scan_security` | 未知 |
| `security-report.json` | 未读到 |
| `scan_security_manual_20260902.log` | 未读到 |

按约定：第 1 步未确认前，不进入第 2 步报告核对，更不进入精选 15→9、纪录分类、hard-pass、正式发布。

下一步仍是：SSH 恢复后只读检查上述 PID 和报告文件。

---

## 11. 2026-09-03 凌晨：SSH 恢复后的只读闭环（第 1–6 步）

本轮只读，未杀进程，未部署，未改 `Hawk2.xml`，未跑 `scheduler --phase full`，未手工 allow，未伪造 `hard_pass`。

### 11.1 SSH 与进程

旧备份配置 `116.196.98.184:22` 仍超时。当前本机 `ssh jie` 走 `ssh.ponyo.fun` → `124.222.190.214`，`id_ed25519`，已连通。

| 检查项 | 结果 |
| --- | --- |
| waiter PID `3547153` | 已退出 |
| scheduler PID `3487363` | 已退出 |
| 新 scheduler / `scan_security` / `drpy_runner` | 无 |
| SQLite `journal_mode` | `delete`（仍禁止并发写） |
| crontab full 流水线 | `0 8,13,20,5 * * *`（morning/noon/evening/night，**不是 23:00**） |
| 最近 full 轮 | `pipeline-run-20260902200001`，结束于 2026-09-02 23:24 CST |
| 下一 night 轮 | 2026-09-03 05:00 CST |

### 11.2 手动 `scan_security`（第 2–3 步）

waiter 在 20:00 轮结束后启动，约 40 分钟写完报告。

| 项 | 值 |
| --- | --- |
| 日志 | `/opt/ponyo-source-manager/logs/scan_security_manual_20260902.log` |
| 日志 mtime | 2026-09-03 00:05:03 CST |
| 返回码 | `rc=0` |
| 报告 | `/opt/ponyo-source-manager/reports/security-report.json` |
| `generated_at` | `2026-09-02T15:25:02.007685+00:00`（扫描开始/开始落库时刻） |
| `findings` | 4357 |

关键 summary：

| 字段 | 数值 |
| --- | ---: |
| `scanned_urls` | 2455 |
| `fetch_errors` | 579 |
| `jar_assets` | 8989 |
| `jar_verified` | 0 |
| `jar_unpinned` | 0 |
| `jar_review_required` | 2234 |
| `jar_invalid` | 6 |
| `jar_unresolved` | 0 |
| `jar_fetch_errors` | 14 |
| `skipped_recent_failed_jar` | 2667 |
| `skipped_recent_fetched_jar` | 2964 |
| `skipped_recent_text` | 7401 |
| `skipped_dynamic_urls` | 216 |
| `skipped_fetch_deadline` | 2645 |
| `retained_prior_jar_results` | 0 |
| high / medium / low | 14 / 3532 / 811 |
| `deny_fps` | 13 |

判断：

- 本次**手动扫描完整出报告且 `rc=0`**。旧 pipeline 里 `scan_security returncode=-9`、2700 秒超时属于 scheduler 阶段超时，不能代表本次手动扫描失败。
- crontab 的 full 流水线仍用 2700 秒杀进程；修复后的 2400 秒预算只在手动跑中完整走完。后续若要让 cron 也稳定出报告，需要单独评估阶段超时，**本轮不改调度、不重跑 full**。
- `skipped_fetch_deadline=2645` 是 2400 秒预算耗尽后剩余的 `(fingerprint, URL)` 对，不是唯一 URL 数。实现符合「到预算后停止新网络请求、继续落库出报告」。数量偏高，但**不能据此放松安全门槛或手工补 allow**。
- 安全超时优先项对「手动扫描能否出报告」已关闭；对「cron 2700 秒仍会杀扫描」仍未关闭。下一步仍不是发布。

### 11.3 数据库实际结构与库存

没有 `source` 表。状态在 `list_state`。

| 表 | 行数 |
| --- | ---: |
| `raw_source` | 7575 |
| `norm_source` | 7575 |
| `dedup_group` | 7575 |
| `score_snapshot` | 575449 |
| `security_finding` | 4357 |
| `conn_probe` | 235579 |
| `list_state.candidate` | 6907 |
| `list_state.deny` | 653 |
| `list_state.allow` | 15 |

`generate_subscription.py` 实际 join：`list_state` → `dedup_group` → `raw_source` → 最新 `score_snapshot`。15 个 allow **全部能 join**，`allow_in_dedup_group = 15/15`。15→9 **不是** dedup_group 丢失。

### 11.4 精选 15→9（第 4 步）

发布层顺序：评分降序 → `CATEGORY_QUOTAS`（听歌/短视频各 1）→ `SITE_GROUPS` 同站点去重 → 截断 29。

当前 15 个 allow（最新分，全部 `hard_pass=0`）：

| fp 前缀 | 分 | 名称 | host | 近 7 天成功时段 |
| --- | ---: | --- | --- | --- |
| `2dab46db77a8` | 97.87 | 暴风资源 | bfzyapi.com | noon |
| `3b33cbc48c59` | 97.76 | 40-橘猫采集 | zitv.cc | morning, night |
| `18e5af049de3` | 96.04 | 40-橘猫采集 | zitv.cc | morning, night |
| `5fd1ea137f11` | 84.17 | 21-爱胆 | lovedan.net | morning |
| `71311d02953f` | 83.95 | 飘零资源 | p2100.net | morning |
| `03bd4ff9ec34` | 83.86 | 25-最大 | zuidazy.co | morning |
| `2c503ccbbe6c` | 83.70 | 最大资源 | api.zuidapi.com | morning, night |
| `73d5ffc5ad98` | 82.87 | 最大 | zuidazy.me | morning |
| `e16188e7feef` | 82.78 | lovedan.net┃GH | lovedan.net | morning, night |
| `55bbea7b269d` | 81.75 | 无尽 | api.wujinapi.com | morning |
| `fcea026b607a` | 81.13 | 1-艾旦 | lovedan.net | noon |
| `00b93063027d` | 80.00 | DJ音乐[听] | 127.0.0.1:5757 | morning, night |
| `1c28515c3155` | 77.39 | 暴風┃采集 | bfzyapi.com | morning（evening 8 次全失败） |
| `0fde5020e770` | 73.59 | 49-无忧 | wyvod.com | evening, morning |
| `62f252f7b755` | 58.99 | 35-最大 | api.zuidapi.com | 无 |

`SITE_GROUPS` 折叠：

- `bfzyapi.com`：只留 97.87
- `lovedan.net`：只留 84.17
- `api.zuidapi.com` / `zuidazy.me` / `zuidazy.co`：只留 83.86
- `zitv.cc` **不在**当前 `SITE_GROUPS`，两个橘猫都保留

因此 `after_quota=15`、`after_site_dedup=9`。staging 约 12 个站点：工具 2 + 儿童 1 + 普通 VOD 9；正式直播在 `lives`，不计入 sites。旧 release 失败「普通精选 9≠29、VOD 10≠30」与此一致。

`release.py` 的 `validate_before_publish` 仍要求普通 29、儿童 1、VOD 30、直播 1，以及分类 影视 20 / 动漫 4 / 纪录 2 / 综艺 2 / 听书短剧 1。当前库存不满足，**不能发布**。

### 11.5 hard-pass 与时段覆盖（第 6 步）

最新评分报告：`generated_at=2026-09-02T14:45:47.337377+00:00`，`total_scored=6931`，`hard_pass=0`，`hard_fail=6931`。功能证据 801，播放证据 202。

生产 `scorer.py`（mtime 2026-08-27）时段规则：近 7 天至少 **3 个不同成功时段**（四时段齐全只作 `full_coverage` 诊断）。SQL 与线上一致：`conn_probe` 按 `timeslot,probed_at` 分组且 `MIN(ok)=1`。

近 7 天库级探测并不缺时段：

| timeslot | 行数 | ok | 覆盖 fp |
| --- | ---: | ---: | ---: |
| evening | 31148 | 6946 | 3777 |
| morning | 7155 | 6719 | 1579 |
| night | 4637 | 4525 | 790 |
| noon | 7285 | 6828 | 1272 |

但 **单源覆盖极不均匀**。15 个 allow 全部不足 3 个成功时段；`62f252f7b755` 为 0。2026-09-02 的 UTC 日历日没有 `timeslot=night` 行，是因为 night cron 在 **05:00 CST = 前一日 21:00 UTC**；最近 night 为 `2026-09-01T21:19:09+00:00`（即 09-02 05:00 CST 那一轮）。这是调度时刻问题，不是 night 管道消失。

根因仍是 probe_conn 的 24h 冷却 + hash 分片轮转：每个 URL 每 4 轮才在一个时段重测一次，再叠加部分 URL 失败，7 天窗口内大量高分源凑不齐 3 个成功时段。

allow 的 `hard_failures`（来自 scoring-report，不是推断）：

| fp 前缀 | 分 | 硬失败 |
| --- | ---: | --- |
| `2dab46db77a8` | 97.87 | 仅缺时段（noon） |
| `3b33cbc48c59` | 97.76 | 仅缺时段（morning/night） |
| `18e5af049de3` | 96.04 | 仅缺时段（morning/night） |
| `00b93063027d` | 80.00 | 仅缺时段（morning/night） |
| `5fd1ea137f11` | 84.17 | 高清 0% + 时段 |
| `71311d02953f` | 83.95 | 高清 0% + 时段 |
| `03bd4ff9ec34` | 83.86 | 高清 0% + 时段 |
| `2c503ccbbe6c` | 83.70 | 高清 0% + 时段 |
| `e16188e7feef` | 82.78 | 高清 0% + 时段 |
| `0fde5020e770` | 73.59 | 高清 0% + 时段 |
| `62f252f7b755` | 58.99 | 高清 0% + 0 时段 |
| `fcea026b607a` | 81.13 | 功能 66.7% + 高清 0% + 时段 |
| `73d5ffc5ad98` | 82.87 | 高清 0% + 时段 + JAR invalid / not_approved |
| `55bbea7b269d` | 81.75 | 高清 0% + 时段 + JAR invalid / not_approved |
| `1c28515c3155` | 77.39 | 时段 + JAR `not_approved=4` / `review_required=6` / `fetch_error=1` |

JAR 细节（只读）：

- `73d5ffc5ad98`、`55bbea7b269d`：`config.spider` → FongMi CatVodSpider，`validation_status=invalid`，md5 `913b706e0079071b9933d71ecf25070d`
- `1c28515c3155`：多条 gao/custom_spider 与 juhe.jar，`review_required` / `fetch_error`（juhe.jar HTTP 404）
- 其余 allow 无 jar evidence 行；allow 无高危 finding

最新 `hard_pass=1` 仅 4 个，**全是 deny**，不可晋级：

| fp 前缀 | 分 | 名称 | 状态 |
| --- | ---: | --- | --- |
| `c2f638574ccc` | 96.89 | 奶子资源 | deny |
| `04228f4770bd` | 95.33 | 爱坤资源 | deny |
| `eb6d2d001803` | 91.09 | 360ZZ┃GH | deny |
| `ab5260390e24` | 86.63 | 鸡坤资源 | deny |

高分 candidate 同样卡时段，例如爱奇艺/天堂/非凡系列 95–100 分，成功时段 1–2 个，`hard_pass=0`。**当前没有可晋级的 hard-pass candidate。** 不能手工改 allow，不能伪造 hard-pass。应等真实探测补时段；若做最小探测，也必须避开 `journal_mode=delete` 的并发写，且不得绕过 7 天 / 3 时段 / 安全 / 播放门槛。

旧 pipeline `promote_demote`：`evaluated=7575, promoted=0, demoted=0`。`release` 仍失败：`普通精选点播数量 9 不等于 29`、`计入指标的 VOD 源数量 10 不等于 30`。

### 11.6 分类库存（第 5 步）

`classify()` / 发布配额按**源名称**匹配 `policy.json`，不是按接口 `class`。

按源名粗分：

| 状态 | 未分类 | 影视 | 网盘 | 听书短剧 | 动漫 | 直播 | 儿童 | 工具 | 综艺 | 纪录 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| allow | 14 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| candidate | 3502 | 1877 | 461 | 401 | 328 | 169 | 91 | 75 | 3 | 0 |
| deny | 388 | 168 | 13 | 47 | 13 | 11 | 6 | 7 | 0 | 0 |

纪录：

- 源**名称**命中「纪录 / 记录片 / 纪录片 / documentary / 纪实」= **0**
- 但 candidate/allow 的 `raw_json.class/categories` 中约 **117** 个混合站带「纪录片/记录片」类目（索尼、淘片、非凡、四九、飞速、虎牙、火狐、飘零等）
- 发布层不会把「接口里有纪录片分类的综合站」算作纪录源；未分类默认归影视
- **没有可直接补齐纪录配额的命名候选**。不能改名、不能伪造分类。需要真实发现或内容探测找出名称/主类型为纪录的源

综艺名称命中仅 3 个 candidate：`点点娱乐`、`分享综艺`、`公众号:刺桐娱乐`。配额要 2，但都未 hard-pass，不能手工 allow。

动漫名称 candidate 很多，最高分仍未过门槛，例如：

| fp 前缀 | 分 | 名称 | 备注 |
| --- | ---: | --- | --- |
| `e503dad727eb` | 83.93 | 稀饭动漫(DS) | 本地 5757，非 maccms |
| `bb53a9b952fe` | 73.78 | 集百动漫[漫](DS) | 本地 5757 |
| `b8c341c6ae2e` | 73.35 | 魔都┃动漫 | maccms |
| `c818b4c48b6a` | 71.94 | 魔都动漫 | maccms |
| `c89f06f269ba` | 68.44 | 动漫豆[漫](DS) | 本地 5757 |

这些只是候选，不代表满足全部门槛。

capability 报告同期：`综艺=3`，`动漫=335`，无独立「纪录」能力桶。

### 11.7 本轮结论与下一步

一句话：手动安全扫描已成功出报告；15→9 是发布层 `SITE_GROUPS` 折叠；最新评分 hard-pass 全灭，4 个 hard-pass 全在 deny；纪录名称库存为 0；未满足 29/1/30/1 与 20/4/2/2/1，不发布。

下一步（仍禁止发布 / 手工 allow / full scheduler）：

1. 等 05:00 / 08:00 / 13:00 / 20:00 自然探测给高分源补满 3 个成功时段；不要为凑时段并发写库。
2. 若评估 cron 2700 秒仍杀 `scan_security`，单独做最小调度修复，不夹带发布。
3. 纪录缺口只能靠真实发现或内容探测，不能靠综合站的「纪录片」类目充数。
4. JAR `invalid` / `review_required` 维持 fail-closed，不把未知/高危标通过。
5. 门禁可满足前不覆盖旧订阅、不改 `Hawk2.xml`。
