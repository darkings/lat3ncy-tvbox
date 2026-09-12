# App 内嵌 drpyS 运行时 —— 实施计划与进度

> 目标：让 type-4 drpyS 源（七猫短剧/央视大全/DJ音乐等，api=`127.0.0.1:5757/api/<module>`）
> 在 Android 设备本地可用。用户确认架构：订阅刷新时 App 先检查订阅里的源及规则，再从服务器更新规则。

## 架构

```
drpy-node(docker, 服务器)  --规则源-->  /opt/ponyo-source-manager/drpys/js/*.js
                                        │ (docker cp 同步)
                                        ▼
children-api(docker)  --挂载 ./drpys-->  /drpys/manifest + /drpys/rule?name=<module>
                                        │ (HTTPS api.ponyo.fun)
                                        ▼
Android App  --订阅刷新时拉规则-->  本地缓存 files/drpys/<module>.js
                                        │
                        本地 drpyS 运行时(QuickJS + NanoHTTPD 127.0.0.1:5757)
                                        │
                        type-4 源 getSort/getList/getDetail 命中本地 /api/<module>
```

## 已完成（服务器侧，2026-08-14）

1. 规则从 drpy-node 容器导出到 `/opt/ponyo-source-manager/drpys/js/`（198 文件，含 `_lib.*.js` 共享库）。
2. `children.py` 新增两个公开接口（已部署、已实测）：
   - `GET /drpys/manifest` → `{module: sha256}`（190 条，供 App diff 增量更新）。
   - `GET /drpys/rule?name=<module>` → 规则 JS 源（带路径穿越防护、ETag）。
3. `docker-compose.yml` 给 `ponyo-children-api` 挂载 `./drpys:/app/drpys:ro`。

## 已完成（Android 侧，2026-08-14）

### 阶段 A：规则拉取与缓存 ✅
- `DrpySRuleManager`：订阅刷新（`ApiConfig.parseJson` 末尾）后遍历 type-4 源，取 api 的 module 名，
  请求 `<base>/drpys/manifest`，与本地 `files/drpys/` sha256 diff，只拉变化的规则写入 `files/drpys/<module>.js`。
- 已实测：46 条规则成功落地（`run-as ... ls files/drpys/`），`echo-drpys-rule-updated` 正常。

### 阶段 B：本地 drpyS 运行时 ✅
- `DrpySBridge`：JS 全局 `request(url,opts)`（okhttp 阻塞 GET/POST，返回 body 字符串）、`md5`、
  `btoa`/`atob`、`unescape`/`escape`、`log`/`print`、`fetchText`、`base64Encode`/`base64Decode`。
- `DrpySRuntime`：单线程 executor 上创建/使用 QuickJSContext（规避 "Must be call same thread"），
  注入 `setResult/getRule/env/G/input`，`loadRule` 加载规则，`homeContent/categoryContent/detailContent/
  searchContent/playContent` 分发 class_parse/一级/二级/搜索/lazy，Promise 解析 + `stringify()` 序列化。
- `DrpySServer`：NanoHTTPD 监听 `127.0.0.1:5757`，`/api/<module>` 路由（filter/ac=detail&t/wd/ids/play&flag），
  按 module 缓存 `DrpySRuntime`，App.onCreate 时 `startQuietly()`。

### 阶段 C：drpyS 规则 JS API 桥 ✅（已覆盖函数型规则 + HTML 解析 + 加密）
- 已覆盖基础全局：`request/md5/btoa/atob/unescape/escape/console/setResult`。
- **P0 补齐（2026-08-14 晚）**：
  - `_fetch`/`fetch`（返回 `{status, headers, text(), json(), content}` 响应对象）、`pdfa/pdfh/pd`（复用 catvod `HtmlParser`/jsoup）、
    `buildUrl/buildQueryString/parseQueryString`、`joinUrl/urljoin`。
  - `CryptoJS`：规则引用时注入内置 `assets/js/lib/crypto-js.js`（198KB UMD）。
  - 修正 `escape/unescape` 为标准 Annex B 语义（此前 `escape` 对 <256 字节未百分号编码，导致 crypto-js `Utf8.stringify` 中文乱码）。
  - URL 解析：对齐 drpy-node `initParse`（相对 URL 用 `rule.host` 拼绝对）+ `cateParse`（fyclass/fyfilter/fypage + filter_url jinja 简化渲染）。
  - 上下文注入：`this.input/MY_URL/HOST` + `this.pdfh/pdfa/pd`（对齐 `createParserContext`）。
  - 详情结果对齐 `detailParseAfter`：`{list:[vod]}`。
- 详情/播放/分类/搜索参数注入对齐 drpy-node `drpysParser.js` injectVars 语义：
  - `一级` → `this={MY_CATE, MY_PAGE, input, MY_URL, HOST, pdfh, pdfa, pd}`
  - `二级` → `this={orId, input, MY_URL, HOST, pdfh, pdfa, pd}`
  - `搜索` → `this={KEY, MY_PAGE, input, MY_URL, HOST, pdfh, pdfa, pd}`
  - `lazy` → `this={input(=play 参数), flag, MY_FLAG, MY_URL}`
  - 无 `class_parse` 函数时回退 `class_name`/`class_url` 字符串构造分类（对齐 `homeParse`）。

### 阶段 D：验证 ✅
在 emulator-5554 实测（本地 5757 HTTP 端点 = App 实际请求路径）：

**七猫短剧（基础函数型规则）**：

| 端点 | 结果 |
|------|------|
| `?filter=true`（class_parse） | 60+ 分类 |
| `?ac=detail&t=1273&pg=1`（一级） | 短剧列表 |
| `?wd=总裁`（搜索） | 搜索结果 |
| `?ac=detail&ids=3793`（二级） | `{list:[{vod_play_from, vod_play_url(m3u8)}]}` |
| `?play=<m3u8>&flag=2`（lazy） | `{"parse":0,"url":"...m3u8"}` |

**七猫小说（CryptoJS/_fetch/HTML 解析函数型规则）**：

| 端点 | 结果 |
|------|------|
| `?filter=true` | 分类：全部/女生原创/男生原创/出版图书（class_name 回退） |
| `?ac=detail&t=1&pg=1`（一级） | 小说列表（pdfa 解析 qimao.com HTML） |
| `?wd=前夫`（搜索） | 搜索结果（buildUrl + md5 sign） |
| `?ac=detail&ids=...`（二级） | 详情 + 章节列表（pdfh/pd + buildUrl） |
| `?play=book@@chapter@@title`（lazy） | `{"parse":0,"url":"novel://{title,content}"}`（CryptoJS AES 解密，UTF-8 正常） |

**UI 实测**：站点切换对话框选中「七猫短剧」，分类栏与内容网格正常渲染（见上一轮记录）。

## 已修复的关键 bug

1. `JSUtils.toJsonObject` 对 JSArray 静默返回 `{}` → 改用 `((JSObject)obj).stringify()`。
2. `toJson` 必须在 executor 线程执行（QuickJS 单线程约束）。
3. `二级` 传 `String[]` 触发 "Unsupported Java type" → 空参数 + `this.orId` 注入。
4. `lazy` 的 `this.input` 应为 `play` 参数，原实现误用 `flag`。
5. 相对 URL 未拼 host（`/shuku/...` 被 okhttp 拒绝）→ loadRule 时用 `rule.host` 绝对化。
6. `HtmlParser` 对空 html 首次调用 `pdfa_doc` 为 null 触发 NPE → pdfa/pdfh/pd 增加空 html 守卫。
7. `escape` 语义错误导致 crypto-js `Utf8.stringify` 中文乱码 → 改为标准 Annex B 语义。

## 已知限制（后续迭代）

- **`.cjs` CommonJS + WASM/Buffer/crypto（央视大全）**：央视大全等规则 `require('./_lib.xxx.cjs')`（Node CommonJS `module.exports`），
  且 `_lib.cntv*.cjs` 依赖 WebAssembly、`Buffer`、`crypto`、`axios`、`fetch` 等大额 Node API。需：服务器端下发 `.cjs`（当前 `/drpys/manifest` 只列 `*.js`）、
  CommonJS 模块包装（`module.exports`）、以及 WASM/Buffer 等运行时（QuickJS wrapper 未暴露 WebAssembly，属独立攻坚）。

## 已支持规则覆盖（43 条 type-4 概览）

- ✅ **全链路 hard pass（3 个具名源，覆盖 4 类规则型）**：
  - 七猫短剧（短剧，函数型 + 基础全局）
  - 小说（七猫小说 CryptoJS 型 / 番茄小说 require·`_lib` 型，二者任取其一；两种规则型均已各自全链路验证）
  - DJ音乐（音乐，字符串选择器型）
- ⚠️ **央视大全（CCTV 直播）分类/内容/搜索**：通过 3/5 端点；详情/播放缺 WebAssembly，**暂不收录进订阅源**。
- ✅ 字符串型分类（`class_name`/`class_url`）回退、字符串型 `一级`/`搜索`、`二级='*'`、`lazy` 字符串包装、JSON5 宽松解析。
- ❌ **央视大全 详情/播放未通过**：`require('./_lib.cntv*.cjs')` + `$.require('./_lib.cntv.js')` 依赖 WebAssembly（`new WebAssembly.Module/Instance/Memory`），QuickJS wrapper 未暴露 WebAssembly。

## 关键风险（沿用）

- drpyS 运行时 API 面很广（Node.js：zlib/ws/forge/pako 等），App 只能覆盖规则实际用到的子集；逐个规则按需补。
- 规则含硬编码凭证/签名算法，服务器公开下发会暴露这些值（与 drpyS 生态公开规则现状一致，接受）。
- 规则文件名含 `[短]` 等字符，App 本地缓存与请求需统一 URL 编码（已处理：module 名 URL 编码 + `URLDecoder`）。
