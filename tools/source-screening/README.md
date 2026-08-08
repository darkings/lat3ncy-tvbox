# Source Screening 工具归档

2026-08-07 外部源筛选（TVBox-Suite / awesome-zhuiju-free / 用户配置列表）中使用的分析脚本。
后续筛选新订阅时可复用。**服务器路径约定**：脚本内引用的 `/tmp/tv.json` 等需先 scp 上传，Python 运行一律在服务器 `jie` 上（`/opt/ponyo-source-manager/.venv/bin/python`）。

## 订阅解析（TVBox 配置 → maccms 源）

| 脚本 | 用途 |
|---|---|
| `tmp_parse_tvjson.py` | 解析 tv.json（sites 数组），列出 maccms 类型源及分类标记（纪录片/综艺/动漫） |
| `tmp_dedupe_tvjson.py` | 与数据库 raw_source 按 host 归一化去重，输出未入库新源 |
| `tmp_probe_tvjson.py` | 批量连通性探测（16 并发/10s），输出可用/不可用清单 |

## 配置批量下载（多仓/多配置）

| 脚本 | 用途 |
|---|---|
| `tmp_fetch_configs.py` | 批量下载 TVBox 配置 URL 列表，解析 sites 提取 maccms（v2：BOM/注释处理） |
| `tmp_fetch_configs2.py` | v3：BOM + 多仓 urls 展开 |
| `tmp_fetch_v4.py` | v4：60+ 配置批量（含中文域名 IDN 编码） |
| `tmp_ck_multi.py` | 展开拾光 ck 多仓（56 子配置） |
| `tmp_shenmi.py` | 展开神秘哥哥多仓（23 子配置，专题频道） |
| `tmp_deep3.py` | 正则提取坏 JSON 配置（heroaku 715 sites/89 maccms + spider/jar 引用） |
| `tmp_scan_4k.py` | 正则扫描 JSON 损坏配置中的 maccms URL |

## 导入与直播

| 脚本 | 用途 |
|---|---|
| `tmp_gen_import.py` | 构造 ponyo.json/health.json/namemap.json 三件套，走 `import_sources.py` 正式导入 |
| `tmp_make_m3u.py` | 从直播多仓 txt 提取可用 IP 的频道生成干净 M3U |
| `tmp_add_live.py` | 将新直播候选追加到服务器 `live_candidates.json` |
| `tmp_live_sctv.py` | 单候选直播评估（复用 live.py 内部函数，跳过全量评估卡顿） |
| `tmp_xml_jwt.py` | 验证 XML-only 源（at=json 无效）与 JWT 跳转源 |

## 经验教训（写入脚本时注意）

- 中文域名必须 IDN 编码（`hostname.encode("idna")`）；中文路径需 `quote(path)`
- TVBox 配置常见 `//` 行注释、BOM、坏 JSON（控制字符）——先剥注释/BOM，坏 JSON 用正则兜底
- maccms 响应 `list` 可能在顶层也可能在 `data.list`，两种都要解析
- 多仓格式：`{"urls":[...]}` JSON 或每行一个 URL 的 txt；`dc.txt` 常带 JSON 尾部附加文本
- 服务器（上海腾讯云）访问 GitHub raw 慢/超时；jsdelivr 对配置文件可用（.jar 403）
- 探测统一在服务器跑（与生产网络一致）；本地仅做下载/解析
