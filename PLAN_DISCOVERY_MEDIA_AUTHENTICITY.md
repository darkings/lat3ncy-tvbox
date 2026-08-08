# Source Manager 媒体真实性与剩余采集计划

版本：2026-07-26  
适用项目：`source-manager`  
正式部署目录：`jie:/opt/ponyo-source-manager`

本文只保留尚未完成的工作。已经上线的配置驱动采集、仓库 URL 展开、候选去重和按内容类型进行时长判断，不再列为后续任务。

## 1. 已完成基线（非待办）

- 生产采集已使用 `watch-subscriptions.json`、`watch-repos.json` 和 `manual-seeds.json`。
- 当前启用 4 个已实测入口：LiuCN、`gaotianliuyun/gao` 的两份配置、`FongMi/CatVodSpider` 配置。
- GitHub、Gitee、GitLab、Agit 仓库地址展开能力已实现；当前生产配置只启用已验证可用的 GitHub 入口。
- 失效的 PanDown、Yoursmile Agit 入口已禁用并保留失败原因，不再被定时高频请求。
- 远程真实采集为 4/4 入口成功，扫描 621 个站点；生产 `raw_source=801`、`norm_source=801`。
- 相同内容连续采集两次均新增 0 个版本、跳过 621 个重复项，`candidate_version` 保持 1341。
- `media_probe` 已支持 `content_type`、`min_duration_s`、`duration_pass`、`duration_reason`、`ffprobe_success`，数据库为 schema 9。
- 已实现电影、剧集、短剧、动漫、纪录片、综艺、儿童和未知类型的独立最低时长门槛。
- 远程真实 HLS 验证：`庆余年`按 46 集判定为剧集，时长 2958.42 秒，超过 480 秒门槛并通过。
- 本地 91 项测试、Python 编译、部署与回滚脚本语法检查通过；远程 API 容器为 healthy。

## 2. 远程目录边界

服务器上与本系统容易混淆的三个目录必须明确区分：

- `/opt/ponyo-source-manager`：唯一生产应用、数据库、报告和订阅发布目录。
- `/opt/ponyo-drpy-node-src`：DRPY Node 运行依赖源码缓存，不是第二套 Source Manager，不得单独调度或发布。
- `/opt/subscription`：当前为空的旧目录，不得作为新订阅发布目标；正式订阅必须位于 `/opt/ponyo-source-manager/subscription/current`。

任何部署、Cron、数据库写入和回滚操作都不得把这三个目录当成三套可互换项目。

## 3. 剩余工作 A：进一步扩大高质量采集面

### A1. 从已验证配置递归发现

从高信誉配置继续提取嵌套订阅、T4 API、可审计的 T3/DRPY 规则、`ext` 规则文件、spider/JAR 依赖地址，以及同仓库其他 TVBox 配置。

递归只负责发现和入候选池，不执行来源不明的脚本、JAR、APK 或二进制插件。

硬性验收：

- RA01：只接受 HTTP(S)，私网、环回、链路本地、云元数据地址 100% 拒绝。
- RA02：递归深度不超过 3，并能识别循环依赖。
- RA03：单批 URL 数、响应体大小、重定向次数和请求超时均有硬上限。
- RA04：入口失败不能阻断其他入口，失败必须写入入口级报告。
- RA05：相同内容哈希、ETag 或 commit SHA 不得重复创建 `candidate_version`。
- RA06：至少新增 3 个连续 7 天可抓取的独立上游入口，且不能全部属于同一维护者。

### A2. 人工推荐入口

人工提交必须记录：

```text
submitted_by
submitted_at
source_url
category_hint
reason
authorization_note
review_state
```

硬性验收：

- RA07：人工推荐只能进入 candidate，不能直接 active 或 hard_pass。
- RA08：缺少提交者、理由或授权说明时拒绝入库，并返回明确拒绝码。
- RA09：同一 URL 重复提交不得生成重复候选版本。

### A3. 入口信誉和退避

为入口单独计算信誉，不与具体视频源分数混用：

```text
fetch_success_rate
new_unique_rate
duplicate_rate
schema_valid_rate
connectivity_pass_rate
authenticity_pass_rate
seven_day_hard_pass_rate
security_reject_rate
consecutive_failures
next_fetch_at
```

硬性验收：

- RA10：连续失败必须指数退避，禁止每个时段反复请求失效入口。
- RA11：信誉只影响抓取频率和深测优先级，不能代替真实播放验收。
- RA12：入口被禁用、恢复或调整频率都必须留下审计记录。

## 4. 剩余工作 B：提高候选验证吞吐

将已连通候选分批送入真实 DRPY2 搜索、详情、播放和媒体检测。建议每批 20～30 个源，每源至少验证 3 个关键词、2 个不同内容和每内容至少 1 个播放地址。

硬性验收：

- RB01：每次深测保存 `run_id`、fingerprint、内容 ID、集 ID、adapter 版本和失败阶段。
- RB02：搜索成功但未得到真实媒体 URL，必须判为播放失败。
- RB03：FFprobe 失败与时长门禁失败分开记录，但任一失败都不能计入媒体成功率。
- RB04：任务可中断续跑，不重复消耗仍在有效期内的结果。
- RB05：不得降低 `MIN_OBSERVATION_DAYS=7` 或 `MIN_TIMESLOTS_PASSED=3` 制造通过结果。

## 5. 剩余工作 C：二维码和提示短片识别

### C1. 视频抽帧

对 FFprobe 可读的 HLS/MP4 受控抽帧：

- 30～180 秒：至少 8 帧；
- 3～20 分钟：至少 20 帧；
- 20 分钟以上：至少 30 帧；
- 覆盖开头、中段、后段，不能只看第一帧。

限制单任务下载量、总耗时和并发数，失败时保存明确原因。

### C2. 二维码检测

优先使用 OpenCV `QRCodeDetector`；必要时比较 ZXing/ZBar，但不得执行二维码内容。保存：

```text
qr_detected
qr_frame_ratio
qr_first_seen_s
qr_last_seen_s
qr_payload_hash
qr_bbox
```

二维码在至少 3 帧出现，或覆盖采样帧 50% 以上，进入高风险判定。

### C3. OCR 风险文字

仅对抽样帧局部 OCR，匹配“扫码、二维码、关注公众号、授权、激活、次数不足、VIP、加群、购买”等提示词。

- 原始文本只存受控审计报告；数据库默认保存关键词、置信度和文本哈希。
- OCR 命中不能单独决定 hard deny，必须结合二维码、时长、静态程度或跨内容指纹。

### C4. 静态画面、循环和跨内容指纹

为每个播放结果生成前 15 秒视频感知哈希、音频指纹、首个媒体分片 SHA-256、时长桶、分辨率与编码组合、帧间差异率。

硬性验收：

- RC01：不同 `content_id/episode_id` 返回相同短媒体指纹时硬拒绝。
- RC02：同一源多数不同内容返回同一提示片时，整源进入 deny 或人工复核。
- RC03：相同正片的多线路重复不能仅凭指纹拒绝，必须结合内容 ID、集 ID 和时长。
- RC04：视觉检测失败时 fail-closed 为“真实性未通过”，不能默认为无二维码。

### C5. 区分片头广告与完整提示片

- 二维码只在开头 2～5 秒出现，后续进入长正片：记录风险但不直接硬拒绝。
- 二维码覆盖主体时间超过 30%，或全片都是提示页：硬拒绝。
- 广告后正片必须重新抽取中后段帧，并确认内容时长和跨内容指纹合理。

## 6. 剩余工作 D：IP、额度和授权绑定识别

同一 fingerprint、内容和集，在至少 2 个合规出口重复验证；条件允许时扩展到 3 个不同 ASN。不得伪造 `X-Forwarded-For`，不得规避第三方登录、付费、DRM、Cookie 或授权限制。

保存：

```text
egress_id
asn
http_status
content_type
duration_s
qr_detected
media_fingerprint
auth_required
quota_message_detected
```

硬性验收：

- RD01：不同出口分别返回正片和扫码/额度提示片时，标记 `ip_bound_parser=1`。
- RD02：依赖特定公共 IP、账号、Cookie 或次数额度的源，`public_usable=0`、`authenticity_pass=0`。
- RD03：不得反编译或执行未获授权的 JAR/APK；获授权文件只能在隔离环境静态分析。

## 7. 剩余数据库与评分改造

新增独立的 `media_authenticity_probe`：

```text
id, fingerprint, run_id, adapter_name, adapter_version
content_id, episode_id, play_url_hash, duration_s
sample_count, qr_detected, qr_frame_ratio, qr_payload_hash
ocr_risk, static_ratio, loop_score
video_phash, audio_fingerprint, first_segment_sha256
egress_id, authenticity_pass, reject_reason, probed_at
```

新增或扩展入口统计表，保存入口成功率、内容版本、退避时间和最终通过率。

评分硬要求：

- 时长、二维码/OCR、静态循环、跨内容指纹、出口一致性均通过后，才能计 `authenticity_pass=1`。
- 真实性失败、真实播放失败、依赖授权或缺少四时段数据时，hard_pass 必须为 0。
- 入口信誉和仓库活跃度只能排序，不能增加源的 hard_pass 分数。

## 8. 报告与可观测性

每轮输出：

- `discovery-entry-report.json`：入口成功、失败、退避、新增、重复和最终通过数量；
- `media-authenticity-report.json`：类型、时长、二维码、OCR、循环和媒体指纹结论；
- `egress-consistency-report.json`：不同出口结果差异；
- `candidate-funnel-report.json`：采集 → 连通 → 搜索 → 播放 → FFprobe → 真实性 → 7 天观察漏斗。

URL、Cookie、token、二维码 payload 和用户信息必须脱敏。

## 9. 剩余实施顺序

1. P0：新增 `media_authenticity_probe`、抽帧和二维码检测。
2. P0：加入 OCR、静态/循环、跨内容媒体指纹和 fail-closed 门禁。
3. P1：批量消化已连通候选并生成漏斗报告。
4. P1：递归发现、人工推荐元数据、入口信誉和指数退避。
5. P2：合规多出口一致性检测。
6. 持续执行真实 7 天四时段观察，不允许用临时降阈值替代。

## 10. 最终硬性验收

- RF01：所有新增迁移对旧库、部分库和重复部署幂等。
- RF02：本地完整测试、远程确定性测试和至少一条真实 HLS 验证全部通过。
- RF03：抽帧、二维码、OCR 或指纹组件异常时不能放行真实性结果。
- RF04：不同内容返回同一二维码短片的固定夹具必须 100% 拒绝。
- RF05：只有片头短广告、随后进入完整正片的固定夹具不能误判为整片提示视频。
- RF06：任何 authenticity 失败都不能产生 hard_pass 或进入发布配额。
- RF07：Cron、容器、数据库和订阅发布只能使用 `/opt/ponyo-source-manager`。
- RF08：部署后 API 必须 healthy，重复采集不得新增相同 candidate 版本。
- RF09：保留 7 天四时段自然运行证据后，才能对新来源做最终晋级判断。

