# Source Manager 复审报告与硬性验收标准

复审时间：2026-07-26（Asia/Shanghai）  
正式部署主机：`jie`  
正式部署目录：`/opt/ponyo-source-manager`

## 1. 结论

本轮已完成真实 DRPY2 接入、真实 HLS/媒体检测和受控回滚演练。

当前结论仍为：**有条件通过工程与运行链验收，但禁止正式发布最终精选订阅。**

唯一剩余的硬阻断项是 A22：尚未完成生产阈值下连续 7 天、每天四时段的自然观察。不得降低 `MIN_OBSERVATION_DAYS = 7` 或 `MIN_TIMESLOTS_PASSED = 3`，不得伪造 `hard_pass`，不得用本轮单次成功替代 A22。

## 2. 远程服务器上的三套 Source Manager 资产

服务器上不是三套同时运行的生产系统，而是“一套生产目录、一套旧开发副本、一份历史归档”：

| 路径 | 角色 | 当前要求 |
|---|---|---|
| `/opt/ponyo-source-manager` | 唯一正式部署和运行目录 | 唯一允许注册 Cron、启动 Source Manager 容器、读写正式数据库和发布订阅的目录 |
| `/root/lat3ncy-tvbox/source-manager` | 旧开发/迁移核对副本 | 禁止注册 Cron、启动容器或参与正式发布；只能用于人工比对 |
| `/root/ponyo-source-manager-legacy.tar.gz` | 已归档的更早脚本式版本 | 只读留档；原 `/root/ponyo-source-manager` 目录已经移除，不得解压后恢复调度 |

另外，`/opt/ponyo-drpy-node-src/2f68bb00452685dcc57c3015995c178ccaac54fb` 是独立许可证边界内的上游 DRPYS 运行时源码快照，不是第四套 Source Manager。它只用于构建固定 revision 的独立容器镜像。

硬性要求：`crontab -l` 中只能有一个 `# BEGIN PONYO MANAGED` / `# END PONYO MANAGED` 区块，且所有命令必须指向 `/opt/ponyo-source-manager`。

## 3. 本轮真实验收证据

### 3.1 DRPYS 运行时与适配器

- 上游：`zourjke/drpy-node`。
- 固定提交：`2f68bb00452685dcc57c3015995c178ccaac54fb`。
- 独立镜像：`ponyo-drpy-node:2f68bb004526`。
- 镜像 revision 标签与上述提交一致。
- 服务只绑定 `127.0.0.1:5757`，配置接口携带本地回环口令。
- `/config/1` 实测返回 252 个站点，其中 216 个是可信本机 type=4 T4 API。
- 可信连接器只导入这 216 个本机 `/api/` 站点，拒绝其他私网、云元数据、重定向和非 T4 条目。
- 连续执行连接器两次均为 `added=0, updated=0, skipped=216`，证明规范化哈希幂等。
- Node 本地 HTTP 集成测试真实覆盖 search、detail、episode、play、线路/播放参数还原、请求头保留和占位地址拒绝。

### 3.2 真实搜索、详情、选集和播放

已在远程正式环境完成以下真实链路：

```text
源：3Q影视[优](DS)
API：http://127.0.0.1:5757/api/3Q影视[优]
关键词：庆余年
搜索结果：15
详情：庆余年 第二季（vod_id=6105）
选集：468
验收集：第36集
线路：站外-ikun [站外]
播放解析：parse=0
播放地址：https://bfikuncdn.com/20240530/p2zz2JeN/index.m3u8
```

生产适配器已硬拒绝 `example.com`、`mock.m3u8`、placeholder、空地址、非绝对 URL 和非 HTTP(S) 内部 token。适配器缺失、超时、畸形 JSON 或上游错误均返回非零退出码。

### 3.3 真实 HLS 与 FFprobe

同一真实播放地址的深度结果：

```text
m3u8_ok：1
HLS 分片总数：1464
深测分片：3
成功分片：3
ffprobe_valid：1
首帧：约 3.37 秒
视频：1920x1080 / H.264 / 25 fps
音频：AAC
时长：2958.42 秒
```

播放响应中的 User-Agent 已同时传给 HLS 下载和 FFprobe；不得在播放阶段丢失真实请求头。

### 3.4 同指纹数据连续性

验收指纹：

```text
7f4f2d5d70a8af60cb2c461609882b38183ffd1457c8157bb6af1e0c11897ee8
```

同一指纹实测存在：

```text
conn_probe：至少 1 条 ok=1，HTTP 200
drpy_test_result：至少 10 条 success=1
media_probe：至少 2 条 success=1
```

真实 Python runner 的六阶段结果全部成功：search、detail、episode、playurl、playback、ffprobe。

### 3.5 受控回滚演练

首次部署因 `/config/1` 默认密码导致健康检查 403，Compose 正确阻断依赖服务启动。随后使用部署前备份执行了真实回滚：

- `scheduler.py`、`docker-compose.yml`、`drpy2/index.js` 三项 SHA-256 与部署前基线完全一致。
- Crontab SHA-256 恢复一致，托管区块数量仍为 1。
- 数据库保持 `raw_source=227`、`norm_source=227`、`conn_probe=60`、`drpy_test_result=6810`、`media_probe=0`，无数据回退或清空。
- 儿童 API 回滚后恢复 `healthy`。
- 演练发现并修复了 Compose 孤儿容器问题；回滚脚本现在必须使用 `--remove-orphans`。
- 修正本地回环口令后已重新部署最新版，`ponyo-drpy-node` 与 `ponyo-children-api` 均健康。

## 4. P0/P1/P2 问题状态

| 编号 | 问题 | 状态 | 硬性证据 |
|---|---|---|---|
| P0-01 | 容器绑定目录不可写 | 通过 | 部署脚本创建并修正 UID/GID，容器写测试成功 |
| P0-02 | Cron 使用系统 Python | 通过 | 全部使用 `/opt/ponyo-source-manager/.venv/bin/python` |
| P1-01 | 新旧 Cron 并存 | 通过 | 唯一托管区块，旧目录不得调度 |
| P1-02 | 订阅挂载到 `/opt/subscription` | 通过 | 使用 `./subscription:/app/subscription` |
| P1-03 | 正式精选订阅不满足生产门槛 | 阻断中 | 门禁正确拒绝；必须等待 A22 后再生成 29+1 |
| P2-01 | 逐文件发布造成混合版本 | 通过 | 时间戳版本目录 + 单次 `current` 链接切换 |
| P2-02 | 损坏评分标记可绕过门禁 | 通过 | 时区、24 小时、run_id、db_version 全部 fail-closed |
| P2-03 | 只测不验真实部署 | 通过 | 已完成远程真实 DRPYS/HLS/FFprobe/回滚演练 |

## 5. A01-A24 硬性验收标准

以下标准均为阻断标准。状态为“待观察”的项目未通过前，不得宣称正式发布完成。

| 编号 | 硬性要求 | 当前状态 |
|---|---|---|
| A01 | 唯一正式部署目录为 `/opt/ponyo-source-manager`；其他副本不得运行 | 通过 |
| A02 | Crontab 只有一个 Ponyo 托管区块和四条阶段任务 | 通过 |
| A03 | Cron 使用 `.venv/bin/python` 绝对路径，不能依赖激活环境 | 通过 |
| A04 | quick、deep、scoring、publish 四阶段完整且顺序明确 | 通过 |
| A05 | 容器用户可写 data、reports、logs、subscription | 通过 |
| A06 | 常驻 API 和 DRPYS 服务必须 healthy；一次性调度退出码必须为 0 | 通过 |
| A07 | 所有持久化挂载都位于正式项目目录，订阅不得写到 `/opt/subscription` | 通过 |
| A08 | 数据库迁移幂等，schema_version 正确且 `hard_pass` 存在 | 通过 |
| A09 | discover/import/normalize/dedupe/probe 必须产生真实且非零数据 | 通过 |
| A10 | 五个核心 CLI 从项目外执行 `--help` 必须返回 0 | 通过 |
| A11 | 自动测试必须全绿，不能用跳过真实验收掩盖失败 | 通过；82 passed，1 条非阻断弃用警告 |
| A12 | 儿童 API `/healthz` 返回成功且数据库可写 | 通过 |
| A13 | 普通精选必须精确为 29，分类配额必须为 21/4/2/2 | 门禁通过；生产产物待 A22 |
| A14 | 直播必须精确为 1 且真实可用 | 门禁通过；生产产物待 A22 |
| A15 | 儿童聚合必须精确为 1 且内容、缓存和回退有效 | 门禁通过；生产产物待 A22 |
| A16 | 发布前必须校验数量、分类、重复 key、禁用类别、manifest 哈希、秘密泄露 | 通过 |
| A17 | 整组发布必须单次原子切换，失败不得改变正式版本 | 通过 |
| A18 | scoring marker 必须校验 timezone、年龄、run_id、db_version，成功后核销 | 通过 |
| A19 | 回滚必须恢复代码、Cron、容器和版本指针，保留数据库且移除孤儿 | 通过，已实演 |
| A20 | 连续部署不得重复 Cron、数据库迁移或容器副本 | 通过 |
| A21 | 真实链路必须贯通 discover→probe→DRPY2→HLS→FFprobe→score→发布门禁 | 技术链通过；正式发布受 A22 阻断 |
| A22 | 生产阈值下连续 7 天、每天四时段自然观察，至少 3 个时段通过 | **待观察，唯一最终阻断项** |
| A23 | 生产解析器必须是真实适配器；mock、placeholder、固定播放结果一律禁止 | 通过 |
| A24 | conn、DRPY2、media、score 必须以同一 `norm_source.fingerprint` 连续入库 | 通过 |

## 6. 发布前最终硬门禁

只有同时满足以下条件，才允许把结论改成“正式发布通过”：

1. A22 的 7 天四时段证据完整，不允许临时降低阈值。
2. 生产数据库中候选源达到真实 `hard_pass`，不得手工改分或复制历史成绩。
3. 29 个普通点播精确满足 21/4/2/2，另有 1 个直播和 1 个儿童聚合。
4. 本轮 scoring marker 与数据库版本、run_id 一致且未超过 24 小时。
5. staging 全量校验通过后才允许单次切换 `subscription/current`。
6. 发布后重新执行真实 API、HLS、FFprobe、文件哈希和并发读取检查。
7. 任一项失败必须保持旧 `current` 不变，并返回非零退出码。

在上述条件完成前，允许系统继续采集、探测、评分和积累观察数据；**禁止绕过门禁发布不满足配额或未经 7 天观察的订阅。**
