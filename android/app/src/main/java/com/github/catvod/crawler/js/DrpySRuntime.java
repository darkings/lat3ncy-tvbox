package com.github.catvod.crawler.js;

import android.util.Base64;
import android.util.Log;

import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.LOG;
import com.whl.quickjs.wrapper.JSCallFunction;
import com.whl.quickjs.wrapper.JSFunction;
import com.whl.quickjs.wrapper.JSObject;
import com.whl.quickjs.wrapper.JSUtils;
import com.whl.quickjs.wrapper.QuickJSContext;

import java.io.File;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * drpyS 规则运行时（App 内嵌）：用 QuickJS 执行 drpy-node 的 drpyS 规则。
 *
 * 注意：QuickJSContext 必须在同一线程创建与使用，因此所有 ctx 操作都在
 * 本类的单线程 executor 上执行（与 JsSpider 相同的线程模型）。
 *
 * 调用约定（对应 drpy-node libs/drpyS.js）：
 * - 首页(filter=true) -> rule.class_parse
 * - 分类(ac=detail&t=) -> rule['一级']，this={MY_CATE, MY_PAGE}
 * - 详情(ac=detail&ids=) -> rule['二级']，this={orId}
 * - 搜索(wd=) -> rule['搜索']，this={KEY, MY_PAGE}
 * - 播放(play=) -> rule['lazy']，this={input}
 */
public class DrpySRuntime {

    private static final String TAG = "DrpySRuntime";
    private static final long CALL_TIMEOUT_SECONDS = 20;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean destroyed = new AtomicBoolean(false);
    private QuickJSContext ctx;
    private JSObject ruleObj;
    private DrpySBridge bridge;
    private volatile String classNames;
    private volatile String classUrls;
    private volatile String ruleUrl;
    private volatile String ruleHost;
    private volatile String ruleSearchUrl;
    private volatile String ruleDetailUrl;
    private volatile String ruleHomeUrl;
    private volatile String ruleFilterUrl;
    private volatile String ruleYiji;
    private volatile String ruleSearch;
    private volatile String ruleErji;
    private volatile String ruleClassParse;
    private volatile String ruleCateExclude;
    private volatile boolean cryptoJsLoaded = false;

    /** 空 JS 对象占位：在 executor 线程内替换为 ctx.createNewJSObject()，避免跨线程建 QuickJS 对象。 */
    private static final String EMPTY_OBJ_MARKER = "\u0000empty\u0000";

    private static final String PREAMBLE =
            "globalThis.setResult = function(d) {\n" +
            "    if (!Array.isArray(d)) return [];\n" +
            "    return d.map(function(it) {\n" +
            "        var obj = { vod_id: it.url || '', vod_name: it.title || '', vod_remarks: it.desc || '', vod_content: it.content || '', vod_pic: it.pic_url || it.img || '' };\n" +
            "        if (it.tname) obj.type_name = it.tname;\n" +
            "        if (it.tid) obj.type_id = it.tid;\n" +
            "        if (it.year) obj.vod_year = it.year;\n" +
            "        if (it.actor) obj.vod_actor = it.actor;\n" +
            "        if (it.director) obj.vod_director = it.director;\n" +
            "        if (it.area) obj.vod_area = it.area;\n" +
            "        return obj;\n" +
            "    });\n" +
            "};\n" +
            "globalThis.getRule = function(name) { return {}; };\n" +
            "globalThis.env = {};\n" +
            "globalThis.G = {};\n" +
            "globalThis.VOD = {};\n" +
            "globalThis.urljoin2 = function(from, to) {\n" +
            "    try {\n" +
            "        if (to == null) return '';\n" +
            "        to = String(to);\n" +
            "        if (!to) return '';\n" +
            "        if (/^https?:\\/\\//i.test(to)) return to;\n" +
            "        if (to.indexOf('//') === 0) { var m = String(from || '').match(/^(https?:)/i); return (m ? m[1] : 'https:') + to; }\n" +
            "        var base = String(from || '');\n" +
            "        var scheme = base.match(/^(https?:\\/\\/[^\\/]+)/i);\n" +
            "        var origin = scheme ? scheme[1] : '';\n" +
            "        if (to.charAt(0) === '/') return origin ? origin + to : to;\n" +
            "        var path = base.replace(/\\?.*$/, '').replace(/[^\\/]*$/, '');\n" +
            "        return origin ? origin + path + to : (path + to);\n" +
            "    } catch (e) { return to == null ? '' : String(to); }\n" +
            "};\n" +
            "globalThis.input = '';\n" +
            "globalThis.axios = { request: function(config) { try { var url = typeof config === 'string' ? config : (config && config.url); var opts = (config && typeof config === 'object') ? config : {}; var res = req(url, opts); var body = (res && res.content) ? res.content : ''; var parsed = body; try { parsed = JSON.parse(body); } catch(e) {} return { data: parsed, status: (res && res.status) ? res.status : 0, headers: {}, content: body }; } catch (e) { return { data: undefined, status: 0, content: '' }; } } };\n" +
            "globalThis.stringify = function(o) { try { return JSON.stringify(o); } catch(e) { return ''; } };\n" +
            "globalThis.encodeUrl = function(s) { try { return encodeURIComponent(s); } catch(e) { return ''; } };\n" +
            "globalThis.urlencode = function(s) { try { return encodeURIComponent(s); } catch(e) { return ''; } };\n" +
            "globalThis.batchFetch = function(list) { if (!Array.isArray(list)) return []; var out = []; for (var i = 0; i < list.length; i++) { var item = list[i]; var url = (item && item.url) ? item.url : (typeof item === 'string' ? item : ''); var opts = (item && item.options) ? item.options : {}; try { out.push(request(url, opts)); } catch (e) { out.push(null); } } return out; };\n" +
            "globalThis.pq = function(html) { var s = String(html == null ? '' : html); return function(sel) { var m = /^([a-zA-Z0-9]+):contains\\((.+)\\)$/.exec(sel); var tag = m ? m[1].toLowerCase() : 'script'; var needle = m ? m[2] : ''; var re = new RegExp('<(' + tag + ')[^>]*>([\\\\s\\\\S]*?)<\\\\/\\\\1>', 'gi'); var match, inner = ''; while ((match = re.exec(s)) !== null) { if (!needle || match[2].indexOf(needle) >= 0) { inner = match[2]; break; } } return { html: function() { return inner; }, text: function() { return inner; }, length: inner ? 1 : 0 }; }; };\n" +
            "globalThis._store = {};\n" +
            "globalThis.getItem = function(k, d) { var v = globalThis._store[k]; return (v === undefined || v === null) ? (d === undefined ? '' : d) : v; };\n" +
            "globalThis.setItem = function(k, v) { globalThis._store[k] = v; };\n" +
            "globalThis.JSON5 = {\n" +
            "    parse: function(s) {\n" +
            "        if (s == null) return null;\n" +
            "        try { return JSON.parse(s); } catch(e) {}\n" +
            "        try {\n" +
            "            var t = String(s);\n" +
            "            t = t.replace(/\\/\\*[\\s\\S]*?\\*\\//g, '').replace(/\\/\\/[^\\n]*/g, '');\n" +
            "            t = t.replace(/,([\\s\\n]*[}\\]])/g, '$1');\n" +
            "            t = t.replace(/\\b(undefined|NaN|Infinity)\\b/g, 'null');\n" +
            "            t = t.replace(/'([^'\\\\]*(\\\\.[^'\\\\]*)*)'/g, function(m, inner) { return '\"' + inner.replace(/\"/g, '\\\\\"') + '\"'; });\n" +
            "            t = t.replace(/([\\{\\[,]\\s*)([A-Za-z_$][A-Za-z0-9_$]*)(\\s*:)/g, '$1\"$2\"$3');\n" +
            "            return JSON.parse(t);\n" +
            "        } catch(e2) { return null; }\n" +
            "    },\n" +
            "    stringify: function(o) { try { return JSON.stringify(o); } catch(e) { return ''; } }\n" +
            "};\n" +
            "globalThis.encodeIfContainsSpecialChars = function(v) { v = v == null ? '' : String(v); return /[&=?#]/.test(v) ? encodeURIComponent(v) : v; };\n" +
            "globalThis.objectToQueryString = function(obj) {\n" +
            "    if (obj == null) return '';\n" +
            "    var parts = [];\n" +
            "    for (var k in obj) { if (Object.prototype.hasOwnProperty.call(obj, k)) { var v = obj[k] == null ? '' : String(obj[k]); parts.push(encodeIfContainsSpecialChars(k) + '=' + encodeIfContainsSpecialChars(v)); } }\n" +
            "    return parts.join('&');\n" +
            "};\n" +
            "try { Object.defineProperty(String.prototype, 'parseX', { get: function() { try { return JSON5.parse(this); } catch(e) { return null; } }, configurable: true }); } catch(e) {}\n";

    // drpyS es6-extend 的 Python 风格扩展（String.join / Array.append / removeHtml 等）
    private static final String ES6_EXTEND =
            "try { if (typeof String.prototype.join !== 'function') { Object.defineProperty(String.prototype, 'join', { value: function(arr) { return Array.isArray(arr) ? arr.join(String(this)) : ''; }, configurable: true }); } } catch(e) {}\n" +
            "try { Object.defineProperty(Array.prototype, 'append', { value: Array.prototype.push, configurable: true }); } catch(e) {}\n" +
            "try { if (typeof String.prototype.strip !== 'function') { Object.defineProperty(String.prototype, 'strip', { value: String.prototype.trim, configurable: true }); } } catch(e) {}\n" +
            "try { if (typeof String.prototype.replaceX !== 'function') { Object.defineProperty(String.prototype, 'replaceX', { value: function(re, rep) { if (typeof re === 'string') re = new RegExp(re, 'g'); else if (re && !re.global) re = new RegExp(re.source, 'g'); return this.replace(re, rep); }, configurable: true }); } } catch(e) {}\n" +
            "globalThis.removeHtml = function(s) { if (s == null) return ''; return String(s).replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '\"').replace(/&#39;/g, \"'\").trim(); };\n" +
            "globalThis.matchesAll = function(str, pattern, flatten) { try { if (typeof pattern === 'string') pattern = new RegExp(pattern, 'g'); var out = []; var m; while ((m = pattern.exec(str)) !== null) { out.push(flatten ? m[0] : m); if (!pattern.global) break; } return out; } catch(e) { return []; } };\n" +
            "globalThis.URLSearchParams = function(init) {\n" +
            "    this._pairs = [];\n" +
            "    if (init && typeof init === 'object') {\n" +
            "        for (var k in init) { if (Object.prototype.hasOwnProperty.call(init, k)) this._pairs.push([k, init[k] == null ? '' : String(init[k])]); }\n" +
            "    } else if (typeof init === 'string') {\n" +
            "        var ps = init.replace(/^\\?/, '').split('&');\n" +
            "        for (var i = 0; i < ps.length; i++) { if (!ps[i]) continue; var eq = ps[i].indexOf('='); var kk = eq < 0 ? ps[i] : ps[i].substring(0, eq); var vv = eq < 0 ? '' : ps[i].substring(eq + 1); this._pairs.push([decodeURIComponent(kk.replace(/\\+/g, ' ')), decodeURIComponent(vv.replace(/\\+/g, ' '))]); }\n" +
            "    }\n" +
            "};\n" +
            "URLSearchParams.prototype.toString = function() { var a = []; for (var i = 0; i < this._pairs.length; i++) a.push(encodeURIComponent(this._pairs[i][0]) + '=' + encodeURIComponent(this._pairs[i][1])); return a.join('&'); };\n" +
            "URLSearchParams.prototype.append = function(k, v) { this._pairs.push([String(k), String(v == null ? '' : v)]); };\n" +
            "URLSearchParams.prototype.get = function(k) { for (var i = 0; i < this._pairs.length; i++) if (this._pairs[i][0] === k) return this._pairs[i][1]; return null; };\n";

    public DrpySRuntime() {
    }

    private void ensureCtx() {
        if (ctx != null) return;
        ctx = QuickJSContext.create();
        ctx.setConsole(new QuickJSContext.Console() {
            @Override public void log(String s) { LOG.i("echo-drpys " + s); }
            @Override public void info(String s) { LOG.i("echo-drpys " + s); }
            @Override public void warn(String s) { LOG.i("echo-drpys " + s); }
            @Override public void error(String s) { LOG.i("echo-drpys " + s); }
        });
        ensureBridge();
        bind(ctx.getGlobalObject(), bridge);
        ctx.evaluate(PREAMBLE);
        ctx.evaluate(ES6_EXTEND);
        setupLibSupport();
    }

    private void ensureBridge() {
        if (bridge != null) return;
        bridge = new DrpySBridge();
        try {
            bridge.setJSContext(ctx);
        } catch (Throwable ignored) {}
    }

    /** 直接发起 HTTP 请求返回 body（复用 DrpySBridge 的 okhttp 实现）。 */
    private String fetchHtml(String url) {
        ensureBridge();
        return bridge.request(url, null);
    }

    /** 读 ruleObj 上的字符串属性（在 executor 线程调用）。 */
    private String readStrProp(JSObject obj, String name) {
        try {
            Object v = ctx.getProperty(obj, name);
            return (v instanceof String) ? (String) v : null;
        } catch (Throwable e) {
            return null;
        }
    }

    /** 规则引用 CryptoJS 时，注入内置 crypto-js.js（assets/js/lib）。 */
    private void ensureCryptoJS() {
        if (cryptoJsLoaded) return;
        try {
            String cjs = FileUtils.loadModule("crypto-js.js");
            if (cjs != null && !cjs.trim().isEmpty() && !cjs.trim().startsWith("{")) {
                ctx.evaluate(cjs);
                Object check = ctx.getProperty(ctx.getGlobalObject(), "CryptoJS");
                if (check != null) {
                    cryptoJsLoaded = true;
                    LOG.i("echo-drpys-cryptojs loaded");
                } else {
                    Log.e(TAG, "crypto-js evaluate did not define CryptoJS");
                }
            }
        } catch (Throwable e) {
            Log.e(TAG, "crypto-js load failed: " + e.getMessage());
        }
    }

    /** 注入 this 上下文上的 pdfh/pdfa/pd 解析助手（对齐 drpy-node createParserContext）。 */
    private void injectCommonContext() {
        if (ruleObj == null) return;
        if (ruleHost != null) {
            try { ctx.setProperty(ruleObj, "HOST", ruleHost); } catch (Throwable ignored) {}
        }
        try {
            // fetch_params = { headers: rule.headers }，供规则 request(input, fetch_params) 携带 UA/Referer/Cookie
            Object headers = ruleObj.getProperty("headers");
            if (headers instanceof JSObject) {
                JSObject fp = ctx.createNewJSObject();
                ctx.setProperty(fp, "headers", headers);
                ctx.setProperty(ruleObj, "fetch_params", fp);
            }
            // getProxyUrl：drpyS 代理/弹幕地址占位（App 端未实现弹幕代理，返回基础代理地址避免规则报 not a function）
            ctx.setProperty(ruleObj, "getProxyUrl", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    return "http://127.0.0.1:5757/proxy?do=ds&extend=";
                }
            });
        } catch (Throwable ignored) {}
        try {
            ctx.setProperty(ruleObj, "pdfh", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    String html = args.length > 0 ? String.valueOf(args[0]) : "";
                    String rule = args.length > 1 ? String.valueOf(args[1]) : "";
                    if (html == null || html.isEmpty()) return "";
                    return HtmlParser.parseDomForUrl(html, rule, "");
                }
            });
            ctx.setProperty(ruleObj, "pdfa", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    String html = args.length > 0 ? String.valueOf(args[0]) : "";
                    String rule = args.length > 1 ? String.valueOf(args[1]) : "";
                    if (html == null || html.isEmpty()) return new JSUtils<String>().toArray(ctx, new java.util.ArrayList<String>());
                    List<String> list = HtmlParser.parseDomForArray(html, rule);
                    return new JSUtils<String>().toArray(ctx, list);
                }
            });
            ctx.setProperty(ruleObj, "pd", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    String html = args.length > 0 ? String.valueOf(args[0]) : "";
                    String rule = args.length > 1 ? String.valueOf(args[1]) : "";
                    String addUrl = args.length > 2 ? String.valueOf(args[2]) : "";
                    if (html == null || html.isEmpty()) return "";
                    return HtmlParser.parseDomForUrl(html, rule, addUrl);
                }
            });
        } catch (Throwable e) {
            Log.e(TAG, "injectCommonContext failed: " + e.getMessage());
        }
    }

    // ---- _lib 模块支持（$.require / require，对齐 drpy-node moduleLoader.js） ----

    private void setupLibSupport() {
        JSObject g = ctx.getGlobalObject();
        try {
            ctx.setProperty(g, "PC_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36");
            ctx.setProperty(g, "MOBILE_UA", "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36");
            JSObject iconv = ctx.createNewJSObject();
            ctx.setProperty(iconv, "decode", new JSCallFunction() {
                @Override public Object call(Object... args) {
                    return args.length > 0 ? String.valueOf(args[0]) : "";
                }
            });
            ctx.setProperty(iconv, "encode", new JSCallFunction() {
                @Override public Object call(Object... args) {
                    return args.length > 0 ? String.valueOf(args[0]) : "";
                }
            });
            ctx.setProperty(g, "iconv", iconv);

            final JSObject dollar = ctx.createNewJSObject();
            ctx.setProperty(g, "$", dollar);
            ctx.setProperty(dollar, "exports", ctx.createNewJSObject());
            ctx.setProperty(dollar, "require", new JSCallFunction() {
                @Override public Object call(Object... args) {
                    String name = args.length > 0 ? String.valueOf(args[0]) : "";
                    return requireLib(name);
                }
            });
            ctx.setProperty(g, "require", new JSCallFunction() {
                @Override public Object call(Object... args) {
                    String name = args.length > 0 ? String.valueOf(args[0]) : "";
                    return requireGlobal(name);
                }
            });
            // drpyS 文本截取工具 cut(text, start, end[, method, All])
            ctx.setProperty(g, "cut", new JSCallFunction() {
                @Override public Object call(Object... args) {
                    String text = args.length > 0 ? String.valueOf(args[0]) : "";
                    String start = args.length > 1 ? String.valueOf(args[1]) : "";
                    String end = args.length > 2 ? String.valueOf(args[2]) : "";
                    boolean all = args.length > 4 && Boolean.TRUE.equals(args[4]);
                    if (all) {
                        List<String> results = new java.util.ArrayList<>();
                        int idx = 0;
                        while (idx < text.length()) {
                            int s2 = start.isEmpty() ? idx : text.indexOf(start, idx);
                            if (s2 < 0) break;
                            int start2 = s2 + start.length();
                            int e2 = end.isEmpty() ? text.length() : text.indexOf(end, start2);
                            if (e2 < 0) break;
                            results.add(text.substring(start2, e2) + end);
                            idx = e2 + end.length();
                        }
                        return new JSUtils<String>().toArray(ctx, results);
                    }
                    int si = start.isEmpty() ? 0 : text.indexOf(start);
                    if (si < 0) return "";
                    int startIdx = si + start.length();
                    int ei = end.isEmpty() ? text.length() : text.indexOf(end, startIdx);
                    if (ei < 0) return "";
                    String result = text.substring(startIdx, ei) + end;
                    if (args.length > 3 && args[3] instanceof JSFunction) {
                        try {
                            Object r = ((JSFunction) args[3]).call(result);
                            if (r != null) return r;
                        } catch (Throwable ignored) {}
                    }
                    return result;
                }
            });
        } catch (Throwable e) {
            Log.e(TAG, "setupLibSupport failed: " + e.getMessage());
        }
    }

    private Object requireGlobal(String name) {
        try {
            if (name == null) return ctx.createNewJSObject();
            if ("iconv-lite".equals(name)) return ctx.getProperty(ctx.getGlobalObject(), "iconv");
            if ("crypto-js".equals(name)) {
                ensureCryptoJS();
                Object c = ctx.getProperty(ctx.getGlobalObject(), "CryptoJS");
                return c != null ? c : ctx.createNewJSObject();
            }
            if (name.startsWith("./") || name.startsWith("../") || name.startsWith("_lib")) {
                return requireLib(name);
            }
            // 其它内置模块（axios/cheerio/fs/path/crypto 等）返回空对象占位
            return ctx.createNewJSObject();
        } catch (Throwable e) {
            Log.e(TAG, "require failed: " + name + " " + e.getMessage());
            return ctx.createNewJSObject();
        }
    }

    private Object requireLib(String name) {
        String content = readLib(name);
        try {
            JSObject dollar = (JSObject) ctx.getProperty(ctx.getGlobalObject(), "$");
            ctx.setProperty(dollar, "exports", ctx.createNewJSObject());
            if (content == null) {
                Log.e(TAG, "lib not found: " + name);
                return ctx.getProperty(dollar, "exports");
            }
            // 用 IIFE 包裹，避免 _lib 里的 function 声明污染全局、与规则顶层 const 冲突
            ctx.evaluate("(function(){\n" + content + "\n})();");
            Log.i(TAG, "lib loaded: " + name);
            return ctx.getProperty(dollar, "exports");
        } catch (Throwable e) {
            Log.e(TAG, "lib eval failed: " + name + " " + e.getMessage());
            return ctx.createNewJSObject();
        }
    }

    private String readLib(String name) {
        if (name == null) return null;
        String n = name;
        if (n.startsWith("./")) n = n.substring(2);
        else if (n.startsWith("../")) n = n.substring(3);
        if (n.isEmpty()) return null;
        File f = new File(DrpySRuleManager.rulesDir(), n);
        if (!f.isFile()) return null;
        try {
            byte[] bytes = new byte[(int) f.length()];
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            try {
                int off = 0;
                while (off < bytes.length) {
                    int r = in.read(bytes, off, bytes.length - off);
                    if (r < 0) break;
                    off += r;
                }
            } finally {
                in.close();
            }
            return new String(bytes, "UTF-8");
        } catch (Throwable e) {
            return null;
        }
    }

    private void bind(JSObject target, Object receiver) {
        for (java.lang.reflect.Method method : receiver.getClass().getMethods()) {
            com.whl.quickjs.wrapper.ContextSetter setter = method.getAnnotation(com.whl.quickjs.wrapper.ContextSetter.class);
            if (setter != null) {
                try { method.invoke(receiver, ctx); } catch (Throwable ignored) {}
            }
        }
        for (java.lang.reflect.Method method : receiver.getClass().getMethods()) {
            com.whl.quickjs.wrapper.Function f = method.getAnnotation(com.whl.quickjs.wrapper.Function.class);
            if (f == null) continue;
            final String name = (f.name() != null && !f.name().isEmpty()) ? f.name() : method.getName();
            final java.lang.reflect.Method m = method;
            ctx.setProperty(target, name, new com.whl.quickjs.wrapper.JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    try {
                        return invokeMethod(m, receiver, args);
                    } catch (Throwable e) {
                        Log.e(TAG, "invoke " + name + " failed: " + e.getMessage());
                        return null;
                    }
                }
            });
        }
    }

    /** 反射调用 @Function 方法：支持 varargs，并对缺失参数补 null。 */
    private static Object invokeMethod(java.lang.reflect.Method m, Object receiver, Object[] args) throws Throwable {
        Class<?>[] types = m.getParameterTypes();
        if (m.isVarArgs()) {
            int fixedCount = types.length - 1;
            Object[] callArgs = new Object[fixedCount + 1];
            for (int i = 0; i < fixedCount; i++) {
                callArgs[i] = (args != null && i < args.length) ? args[i] : null;
            }
            int varLen = Math.max(0, (args == null ? 0 : args.length) - fixedCount);
            Object[] varargs = new Object[varLen];
            for (int i = 0; i < varLen; i++) varargs[i] = args[fixedCount + i];
            callArgs[fixedCount] = varargs;
            return m.invoke(receiver, callArgs);
        }
        Object[] callArgs = new Object[types.length];
        for (int i = 0; i < types.length; i++) {
            callArgs[i] = (args != null && i < args.length) ? args[i] : null;
        }
        return m.invoke(receiver, callArgs);
    }

    /** 加载规则 JS（在 executor 线程上创建 ctx 并加载）。 */
    /** 密文规则解码：明文直接返回；否则去 @header 注释后 base64 解码（对齐 drpy-node getOriginalJs）。 */
    private static String decodeRule(String js) {
        if (js == null) return js;
        String plainMarker = "(?s).*(var\\s+rule|function|let\\s+|var\\s+|const|class\\s+Rule|async|this\\.).*";
        if (js.matches(plainMarker)) return js;
        String body = js.replaceFirst("(?s)^\\s*/\\*.*?\\*/\\s*", "");
        String b64 = body.replaceAll("\\s+", "");
        if (!b64.isEmpty()) {
            try {
                byte[] bytes = Base64.decode(b64, Base64.DEFAULT);
                String decoded = new String(bytes, "UTF-8");
                if (decoded.matches("(?s).*(var\\s+rule|function|let\\s+|const|async).*")) {
                    return decoded;
                }
            } catch (Throwable ignored) {
            }
        }
        return js;
    }

    public boolean loadRule(String js) {
        if (js == null || js.trim().isEmpty()) return false;
        try {
            final String code = decodeRule(js);
            return executor.submit(() -> {
                try {
                    ensureCtx();
                    if (code.contains("CryptoJS")) ensureCryptoJS();
                    ctx.evaluate(code);
                    Object r = ctx.getProperty(ctx.getGlobalObject(), "rule");
                    if (r instanceof JSObject) {
                        ruleObj = (JSObject) r;
                        // 执行 预处理（对齐 drpy-node initParse）：动态设置 class_name/class_url/filter 等
                        try {
                            JSFunction pre = ruleObj.getJSFunction("预处理");
                            if (pre != null) {
                                try {
                                    Object pr = pre.call();
                                    if (pr instanceof JSObject) resolvePromise((JSObject) pr);
                                } finally {
                                    pre.release();
                                }
                            }
                        } catch (Throwable e) {
                            Log.e(TAG, "预处理 failed: " + e.getMessage());
                        }
                        try {
                            classNames = readStrProp(ruleObj, "class_name");
                            classUrls = readStrProp(ruleObj, "class_url");
                            ruleHost = readStrProp(ruleObj, "host");
                            // 对齐 drpy-node initParse：相对 URL 用 rule.host 拼成绝对地址
                            ruleUrl = absUrl(readStrProp(ruleObj, "url"), ruleHost);
                            ruleSearchUrl = absUrl(readStrProp(ruleObj, "searchUrl"), ruleHost);
                            ruleDetailUrl = absUrl(readStrProp(ruleObj, "detailUrl"), ruleHost);
                            // 对齐 drpy-node initParse：homeUrl 为空时回退 host
                            String homeUrlRaw = readStrProp(ruleObj, "homeUrl");
                            ruleHomeUrl = (homeUrlRaw == null || homeUrlRaw.isEmpty())
                                    ? ruleHost : absUrl(homeUrlRaw, ruleHost);
                            ruleFilterUrl = readStrProp(ruleObj, "filter_url");
                            ruleYiji = readStrProp(ruleObj, "一级");
                            ruleSearch = readStrProp(ruleObj, "搜索");
                            ruleErji = readStrProp(ruleObj, "二级");
                            ruleClassParse = readStrProp(ruleObj, "class_parse");
                            ruleCateExclude = readStrProp(ruleObj, "cate_exclude");
                        } catch (Throwable ignored) {}
                        injectCommonContext();
                        return true;
                    }
                    return false;
                } catch (Throwable e) {
                    LOG.i("echo-drpys-load-error " + e.getMessage());
                    return false;
                }
            }).get(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Throwable e) {
            LOG.i("echo-drpys-load-error " + e.getMessage());
            return false;
        }
    }

    private String callMethodJson(final String name, final Object[] args, final Map<String, Object> props) {
        if (destroyed.get() || ruleObj == null) return "{}";
        try {
            return executor.submit(() -> {
                try {
                    if (props != null) {
                        for (Map.Entry<String, Object> e : props.entrySet()) {
                            if (e.getValue() != null) {
                                Object v = e.getValue();
                                if (EMPTY_OBJ_MARKER.equals(v)) {
                                    v = ctx.createNewJSObject();
                                } else if (v instanceof Map) {
                                    // 筛选参数 Map → executor 线程内转 JSObject（QuickJS 单线程约束）
                                    JSObject flObj = ctx.createNewJSObject();
                                    for (Map.Entry<?, ?> en : ((Map<?, ?>) v).entrySet()) {
                                        if (en.getKey() != null && en.getValue() != null) {
                                            ctx.setProperty(flObj, String.valueOf(en.getKey()), String.valueOf(en.getValue()));
                                        }
                                    }
                                    v = flObj;
                                }
                                ctx.setProperty(ruleObj, e.getKey(), v);
                            }
                        }
                    }
                    JSFunction fn = ruleObj.getJSFunction(name);
                    if (fn == null) return "{}";
                    try {
                        Object result = fn.call(args);
                        Object value = (result instanceof JSObject) ? resolvePromise((JSObject) result) : result;
                        // toJson 必须在 executor 线程执行（QuickJSContext 单线程约束）
                        return toJson(value);
                    } catch (Throwable e) {
                        Log.e(TAG, "call " + name + " failed: " + e.getMessage());
                        return "{}";
                    } finally {
                        fn.release();
                    }
                } catch (Throwable e) {
                    return "{}";
                }
            }).get(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Throwable e) {
            LOG.i("echo-drpys-call-error " + name + " " + e.getMessage());
            return "{}";
        }
    }

    private Object resolvePromise(JSObject promise) {
        final Object[] value = {null};
        final CountDownLatch latch = new CountDownLatch(1);
        JSFunction then = promise.getJSFunction("then");
        if (then == null) return promise;
        then.call(new com.whl.quickjs.wrapper.JSCallFunction() {
            @Override
            public Object call(Object... args) {
                value[0] = (args != null && args.length > 0) ? args[0] : null;
                Log.i(TAG, "promise-then " + (value[0] == null ? "null" : value[0].getClass().getSimpleName()));
                latch.countDown();
                return null;
            }
        });
        JSFunction cat = promise.getJSFunction("catch");
        if (cat != null) {
            cat.call(new com.whl.quickjs.wrapper.JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    if (args != null && args.length > 0) {
                        Log.e(TAG, "promise-rejected " + String.valueOf(args[0]));
                    }
                    latch.countDown();
                    return null;
                }
            });
        }
        try {
            if (!latch.await(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)) return null;
        } catch (InterruptedException e) {
            return null;
        }
        return value[0];
    }

    private String toJson(Object obj) {
        if (obj == null) return "{}";
        if (obj instanceof JSObject) {
            try {
                // stringify() 同时处理 JSObject(对象) 与 JSArray(数组)，
                // JSUtils.toJsonObject 对数组会因 JSONException 静默返回 {}。
                String s = ((JSObject) obj).stringify();
                if (s == null || s.isEmpty() || "undefined".equals(s)) return "{}";
                return s;
            } catch (Throwable e) {
                Log.e(TAG, "toJson-error " + e.getClass().getSimpleName() + " " + e.getMessage());
                return "{}";
            }
        }
        Log.i(TAG, "toJson-nonobject " + obj.getClass().getSimpleName());
        return String.valueOf(obj);
    }

    // ---- 对齐 drpy-node drpysParser.js 的 URL 解析（homeParse/cateParse/detailParse/searchParse） ----

    /** 相对 URL 用 host 拼成绝对地址（对齐 drpy-node initParse 的 urljoin）。 */
    private static String absUrl(String url, String host) {
        if (url == null || url.isEmpty()) return url;
        if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("//")) return url;
        if (host == null || host.isEmpty()) return url;
        return HtmlParser.joinUrl(host, url);
    }

    private String resolveHomeUrl() {
        return ruleHomeUrl == null ? "" : ruleHomeUrl;
    }

    private String resolveCateUrl(String tid, int pg) {
        String url = ruleUrl == null ? "" : ruleUrl;
        url = url.replace("fyclass", tid);
        if (ruleFilterUrl != null && !ruleFilterUrl.isEmpty()) {
            String rendered = renderFilter(ruleFilterUrl, tid);
            if (url.contains("fyfilter")) {
                url = url.replace("fyfilter", rendered);
            } else {
                if (!url.endsWith("&") && !rendered.startsWith("&")) url += "&";
                url += rendered;
            }
        } else {
            url = url.replace("fyfilter", "");
        }
        url = resolveFypage(url, pg);
        return url;
    }

    /** 拆分 vod_id 的 MY_CATE$ 前缀与 @@ 附加数据，返回 [fyclass, vid]（对齐 drpy-node detailParse）。 */
    private String[] splitVodId(String id) {
        String vid = id == null ? "" : id;
        String fyclass = "";
        int dollar = vid.indexOf('$');
        if (dollar >= 0) {
            fyclass = vid.substring(0, dollar);
            vid = vid.substring(dollar + 1);
        }
        int atat = vid.indexOf("@@");
        if (atat >= 0) vid = vid.substring(0, atat);
        return new String[]{fyclass, vid};
    }

    private String resolveDetailUrl(String id) {
        if (ruleDetailUrl == null || ruleDetailUrl.isEmpty()) return id;
        String[] parts = splitVodId(id);
        String fyclass = parts[0];
        String vid = parts[1];
        if (!vid.startsWith("http") && !vid.contains("/")) {
            return ruleDetailUrl.replace("fyid", vid).replace("fyclass", fyclass);
        } else if (vid.contains("/")) {
            return HtmlParser.joinUrl(ruleHomeUrl == null ? "" : ruleHomeUrl, vid);
        } else {
            return vid;
        }
    }

    private String resolveSearchUrl(String wd, int pg) {
        String url = ruleSearchUrl == null ? "" : ruleSearchUrl;
        url = url.replace("**", wd);
        url = resolveFypage(url, pg);
        return url;
    }

    /** 简化 filter_url jinja 渲染（对齐 drpy-node 的 fl 渲染，空筛选时用默认值）：
     *  {{fl}} -> ''；{{fl.KEY or 'DEF'}}/{{fl.KEY or "DEF"}}/{{fl.KEY or DEF}} -> DEF；{{fl.KEY}} -> ''；{{fyclass}} -> tid。 */
    private String renderFilter(String template, String tid) {
        String out = template == null ? "" : template;
        out = out.replace("{{fyclass}}", tid);
        out = out.replaceAll("\\{\\{\\s*fl\\s*\\}\\}", "");                       // {{fl}} -> ''
        out = out.replaceAll("\\{\\{\\s*fl\\.[^\\s}]+\\s+or\\s+'([^']*)'\\s*\\}\\}", "$1");   // 'DEF'
        out = out.replaceAll("\\{\\{\\s*fl\\.[^\\s}]+\\s+or\\s+\"([^\"]*)\"\\s*\\}\\}", "$1"); // "DEF"
        out = out.replaceAll("\\{\\{\\s*fl\\.[^\\s}]+\\s+or\\s+([^\\s}]+)\\s*\\}\\}", "$1");   // DEF（无引号）
        out = out.replaceAll("\\{\\{\\s*fl\\.[^\\s}]+\\s*\\}\\}", "");           // {{fl.KEY}} -> ''
        return out;
    }

    /** 替换 fypage 并逐层求值括号内算术（对齐 drpy-node cateParse 的 fypage 处理）。 */
    private String resolveFypage(String url, int pg) {
        String u = url.replace("fypage", String.valueOf(pg));
        for (int guard = 0; guard < 10; guard++) {
            int close = u.indexOf(')');
            if (close < 0) break;
            int open = u.lastIndexOf('(', close);
            if (open < 0) break;
            String inner = u.substring(open + 1, close);
            long val;
            try {
                val = evalArith(inner);
            } catch (Throwable e) {
                u = u.substring(0, open) + inner + u.substring(close + 1);
                continue;
            }
            u = u.substring(0, open) + val + u.substring(close + 1);
        }
        return u;
    }

    /** 简单整数四则运算求值（+ - * / 与括号，供 fypage 表达式使用）。 */
    private static long evalArith(String expr) {
        return new Arith(expr).parseExpr();
    }

    private static final class Arith {
        final String s;
        int pos;

        Arith(String s) {
            this.s = s == null ? "" : s;
        }

        long parseExpr() {
            long v = parseTerm();
            while (pos < s.length()) {
                char c = s.charAt(pos);
                if (c == '+') { pos++; v += parseTerm(); }
                else if (c == '-') { pos++; v -= parseTerm(); }
                else break;
            }
            return v;
        }

        long parseTerm() {
            long v = parseFactor();
            while (pos < s.length()) {
                char c = s.charAt(pos);
                if (c == '*') { pos++; v *= parseFactor(); }
                else if (c == '/') { pos++; long d = parseFactor(); if (d != 0) v /= d; }
                else break;
            }
            return v;
        }

        long parseFactor() {
            skip();
            if (pos < s.length() && s.charAt(pos) == '(') {
                pos++;
                long v = parseExpr();
                skip();
                if (pos < s.length() && s.charAt(pos) == ')') pos++;
                return v;
            }
            int start = pos;
            if (pos < s.length() && (s.charAt(pos) == '-' || s.charAt(pos) == '+')) pos++;
            while (pos < s.length() && (Character.isDigit(s.charAt(pos)) || s.charAt(pos) == '.')) pos++;
            if (start == pos) throw new IllegalArgumentException("bad expr: " + s);
            return Long.parseLong(s.substring(start, pos).trim());
        }

        void skip() {
            while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) pos++;
        }
    }

    // ---- 字符串型 一级/搜索 选择器解析（对齐 drpy-node commonCategoryListParse/commonSearchListParse） ----

    /** 解析选择器字符串的 5 部分，`*` 部分回退到 一级 的对应部分。 */
    private String[] resolveParts(String selectorStr) {
        String[] p = (selectorStr == null ? "" : selectorStr).split(";");
        String[] yj = ruleYiji == null ? new String[0] : ruleYiji.split(";");
        String[] out = new String[p.length];
        for (int i = 0; i < p.length; i++) {
            String part = p[i];
            if ("*".equals(part) && i < yj.length) part = yj[i];
            out[i] = part;
        }
        return out;
    }

    private boolean isStringMethod(String s) {
        return s != null && !s.isEmpty() && !"*".equals(s.trim());
    }

    /** 字符串选择器通用列表解析：请求 url -> pdfa(p0) -> 逐项 pdfh/pd 提取。 */
    private String parseStringList(String url, String selectorStr) {
        String[] p = resolveParts(selectorStr);
        if (p.length < 5) return "[]";
        String p0 = p[0] == null ? "" : p[0].replaceAll("^(jsp:|json:|jq:)", "");
        String p1 = p[1], p2 = p[2], p3 = p[3], p4 = p[4];
        String p5 = p.length > 5 ? p[5] : "";
        String html = fetchHtml(url);
        if (html == null || html.isEmpty()) return "[]";
        List<String> items;
        try {
            items = HtmlParser.parseDomForArray(html, p0);
        } catch (Throwable e) {
            return "[]";
        }
        boolean detailUrlExists = ruleDetailUrl != null && !ruleDetailUrl.isEmpty();
        StringBuilder sb = new StringBuilder("[");
        boolean first = true;
        for (String it : items) {
            String name = clean(HtmlParser.parseDomForUrl(it, p1, ""));
            String pic = HtmlParser.parseDomForUrl(it, p2, url);
            String remarks = clean(HtmlParser.parseDomForUrl(it, p3, ""));
            StringBuilder linkSb = new StringBuilder();
            for (String p4part : (p4 == null ? "" : p4).split("\\+")) {
                if (p4part.isEmpty()) continue;
                String link = detailUrlExists
                        ? HtmlParser.parseDomForUrl(it, p4part, "")
                        : HtmlParser.parseDomForUrl(it, p4part, url);
                if (linkSb.length() > 0) linkSb.append('$');
                linkSb.append(link);
            }
            String vodId = linkSb.toString();
            if ("*".equals(ruleErji == null ? "" : ruleErji.trim())) {
                vodId = vodId + "@@" + name + "@@" + pic;
            }
            String content = (p5 == null || p5.isEmpty()) ? "" : clean(HtmlParser.parseDomForUrl(it, p5, ""));
            if (!first) sb.append(',');
            first = false;
            sb.append("{\"vod_id\":").append(jsonStr(vodId))
              .append(",\"vod_name\":").append(jsonStr(name))
              .append(",\"vod_pic\":").append(jsonStr(pic))
              .append(",\"vod_remarks\":").append(jsonStr(remarks))
              .append(",\"vod_content\":").append(jsonStr(content))
              .append('}');
        }
        sb.append(']');
        return sb.toString();
    }

    private static String clean(String s) {
        if (s == null) return "";
        return s.replaceAll("[\n\t]", "").trim();
    }

    public String homeContent(boolean filter) {
        java.util.HashMap<String, Object> props = new java.util.HashMap<>();
        String homeUrl = resolveHomeUrl();
        if (homeUrl != null && !homeUrl.isEmpty()) {
            props.put("input", homeUrl);
            props.put("MY_URL", homeUrl);
        }
        String json = callMethodJson("class_parse", new Object[]{filter}, props);
        // 回退 1：静态 class_name/class_url（规则未定义 class_parse 函数）
        if (json == null || json.equals("{}") || !json.contains("\"class\"")) {
            String fallback = buildClassFromStrings(classNames, classUrls);
            if (fallback != null) json = fallback;
        }
        // 回退 2：class_parse 内动态设置的 this.class_name/class_url（如 小苹果）
        if (json == null || json.equals("{}") || !json.contains("\"class\"")) {
            String dynamic = buildClassFromDynamic();
            if (dynamic != null) json = dynamic;
        }
        // 回退 3：字符串型 class_parse（选择器，如 爱推图，对齐 commonClassParse）
        if (json == null || json.equals("{}") || !json.contains("\"class\"")) {
            String sel = buildClassFromSelector();
            if (sel != null) json = sel;
        }
        // 主页内容：规则无推荐/列表时，用第一个分类的一级内容补 list，保证每个源主页显示自己的内容
        try {
            if (json != null && json.contains("\"class\"") && !json.contains("\"list\"")) {
                org.json.JSONObject obj = new org.json.JSONObject(json);
                org.json.JSONArray cls = obj.optJSONArray("class");
                if (cls != null && cls.length() > 0) {
                    Object tid = cls.optJSONObject(0).opt("type_id");
                    if (tid != null && !String.valueOf(tid).isEmpty()) {
                        String listJson = categoryContent(String.valueOf(tid), "1");
                        if (listJson != null) {
                            org.json.JSONObject listObj = new org.json.JSONObject(listJson);
                            org.json.JSONArray list = listObj.optJSONArray("list");
                            if (list != null && list.length() > 0) {
                                obj.put("list", list);
                                json = obj.toString();
                            }
                        }
                    }
                }
            }
        } catch (Throwable ignored) {}
        LOG.i("echo-drpys-home-result " + (json == null ? "null" : json.substring(0, Math.min(200, json.length()))));
        return json;
    }

    /** 字符串型 class_parse（选择器）：请求 homeUrl 后 pdfa/pdh/pd 提取分类（对齐 drpy-node commonClassParse）。 */
    private String buildClassFromSelector() {
        if (ruleClassParse == null || ruleClassParse.isEmpty()) return null;
        String[] p = ruleClassParse.split(";");
        if (p.length < 3) return null;
        String p0 = p[0].replaceFirst("^(jsp:|json:|jq:)", "");
        String p1 = p[1], p2 = p[2];
        String p3 = p.length > 3 ? p[3] : "";
        String homeUrl = resolveHomeUrl();
        if (homeUrl == null || homeUrl.isEmpty()) return null;
        String html = fetchHtml(homeUrl);
        if (html == null || html.isEmpty()) return null;
        List<String> items;
        try {
            items = HtmlParser.parseDomForArray(html, p0);
        } catch (Throwable e) {
            return null;
        }
        StringBuilder sb = new StringBuilder("{\"class\":[");
        boolean first = true;
        for (String it : items) {
            String name = clean(HtmlParser.parseDomForUrl(it, p1, ""));
            if (ruleCateExclude != null && !ruleCateExclude.isEmpty()) {
                try {
                    if (name.matches("(?s).*" + ruleCateExclude + ".*")) continue;
                } catch (Throwable ignored) {}
            }
            String url = HtmlParser.parseDomForUrl(it, p2, homeUrl);
            if (p3 != null && !p3.isEmpty()) {
                try {
                    java.util.regex.Matcher m = java.util.regex.Pattern.compile(p3).matcher(url);
                    if (m.find() && m.groupCount() >= 1 && m.group(1) != null) url = m.group(1);
                } catch (Throwable ignored) {}
            }
            if (name.isEmpty()) continue;
            if (!first) sb.append(',');
            first = false;
            sb.append("{\"type_id\":").append(jsonStr(url.trim()))
              .append(",\"type_name\":").append(jsonStr(name)).append('}');
        }
        sb.append("],\"filters\":{}}");
        return sb.toString();
    }

    /** 由 class_name/class_url 字符串构造分类列表（drpy-node homeParse 行为）。 */
    private String buildClassFromStrings(String classNames, String classUrls) {
        if (classNames == null || classUrls == null) return null;
        String[] names = classNames.split("&");
        String[] urls = classUrls.split("&");
        StringBuilder sb = new StringBuilder("{\"class\":[");
        int cnt = Math.min(names.length, urls.length);
        for (int i = 0; i < cnt; i++) {
            if (i > 0) sb.append(',');
            sb.append("{\"type_id\":").append(jsonStr(urls[i]))
              .append(",\"type_name\":").append(jsonStr(names[i])).append('}');
        }
        sb.append("],\"filters\":{}}");
        return sb.toString();
    }

    /** class_parse 可能在运行中动态设置 this.class_name/this.class_url，executor 线程重读。 */
    private String buildClassFromDynamic() {
        if (ruleObj == null || destroyed.get()) return null;
        try {
            return executor.submit(() -> {
                try {
                    String cn = readStrProp(ruleObj, "class_name");
                    String cu = readStrProp(ruleObj, "class_url");
                    return buildClassFromStrings(cn, cu);
                } catch (Throwable e) {
                    return null;
                }
            }).get(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Throwable e) {
            return null;
        }
    }

    private static String jsonStr(String s) {
        if (s == null) return "\"\"";
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"' || c == '\\') sb.append('\\');
            sb.append(c);
        }
        return sb.append('"').toString();
    }

    public String categoryContent(String tid, String pg) {
        return categoryContent(tid, pg, null);
    }

    /** 带筛选的一级：fl 非空时作为 MY_FL 传给规则（QuickJS 内转 JSObject）。 */
    public String categoryContent(String tid, String pg, java.util.Map<String, String> fl) {
        int p = 1;
        try { p = Integer.parseInt(pg); } catch (Throwable ignored) {}
        String url = resolveCateUrl(tid, p);
        if (url == null) url = "";
        // 字符串型 一级（选择器）→ commonCategoryListParse
        if (isStringMethod(ruleYiji)) {
            String list = parseStringList(url, ruleYiji);
            return "{\"list\":" + list + "}";
        }
        java.util.HashMap<String, Object> props = new java.util.HashMap<>();
        props.put("MY_CATE", tid);
        props.put("MY_PAGE", p);
        props.put("MY_FL", (fl == null || fl.isEmpty()) ? EMPTY_OBJ_MARKER : fl);
        if (!url.isEmpty()) {
            props.put("input", url);
            props.put("MY_URL", url);
        }
        String r = callMethodJson("一级", new Object[]{tid, pg, true, null}, props);
        return "{\"list\":" + (r == null || r.equals("{}") ? "[]" : r) + "}";
    }
    public String detailContent(String id) {
        // 二级 '*' 默认解析（对齐 commonDetailListParse p==='*'）
        if ("*".equals(ruleErji == null ? "" : ruleErji.trim())) {
            String[] extra = (id == null ? "" : id).split("@@");
            String url = extra.length > 0 ? extra[0] : (id == null ? "" : id);
            String name = extra.length > 1 ? extra[1] : "片名";
            String pic = extra.length > 2 ? extra[2] : "";
            return "{\"list\":[{\"vod_id\":" + jsonStr(id)
                    + ",\"vod_name\":" + jsonStr(name)
                    + ",\"vod_pic\":" + jsonStr(pic)
                    + ",\"vod_play_from\":\"道长在线\""
                    + ",\"vod_play_url\":" + jsonStr("嗅探播放$" + url)
                    + ",\"vod_content\":" + jsonStr(url)
                    + "}]}";
        }
        java.util.HashMap<String, Object> props = new java.util.HashMap<>();
        String[] vidParts = splitVodId(id);
        props.put("orId", id);
        props.put("vid", vidParts[1]);
        props.put("fyclass", vidParts[0]);
        props.put("detailUrl", vidParts[1]);
        String url = resolveDetailUrl(id);
        if (url != null && !url.isEmpty()) {
            props.put("input", url);
            props.put("MY_URL", url);
        }
        // 规则 二级 读取 this.orId/this.input，不接收位置参数（String[] 不被 QuickJS 支持）
        String r = callMethodJson("二级", new Object[]{}, props);
        if (r == null || r.equals("{}")) return "{}";
        // 对齐 drpy-node detailParseAfter：{list: [vod]}
        return "{\"list\":[" + r + "]}";
    }

    public String searchContent(String wd, String pg) {
        int p = 1;
        try { p = Integer.parseInt(pg); } catch (Throwable ignored) {}
        String url = resolveSearchUrl(wd, p);
        if (url == null) url = "";
        // 字符串型 搜索（选择器）→ commonSearchListParse
        if (isStringMethod(ruleSearch)) {
            String list = parseStringList(url, ruleSearch);
            return "{\"list\":" + list + "}";
        }
        java.util.HashMap<String, Object> props = new java.util.HashMap<>();
        props.put("KEY", wd);
        props.put("MY_PAGE", p);
        if (!url.isEmpty()) {
            props.put("input", url);
            props.put("MY_URL", url);
        }
        String r = callMethodJson("搜索", new Object[]{wd, false, p}, props);
        return "{\"list\":" + (r == null || r.equals("{}") ? "[]" : r) + "}";
    }

    public String playContent(String play, String flag) {
        java.util.HashMap<String, Object> props = new java.util.HashMap<>();
        props.put("input", play);
        props.put("flag", flag);
        props.put("MY_FLAG", flag);
        props.put("MY_URL", play);
        String r = callMethodJson("lazy", new Object[]{flag, play, null}, props);
        if (r == null || r.equals("{}")) return r == null ? "{}" : r;
        // lazy 返回字符串（直接播放地址）时，对齐 playParseAfter 包装为 {parse, url}
        if (!r.startsWith("{") && !r.startsWith("[")) {
            boolean direct = r.matches("(?s).*\\.(m3u8|mp4|m4a|mp3).*") || r.startsWith("push:");
            return "{\"parse\":" + (direct ? 0 : 1) + ",\"jx\":0,\"url\":" + jsonStr(r) + "}";
        }
        return r;
    }

    public void destroy() {
        if (!destroyed.compareAndSet(false, true)) return;
        executor.submit(() -> {
            try {
                ruleObj = null;
                if (ctx != null) ctx.destroy();
            } catch (Throwable ignored) {}
        });
        executor.shutdown();
    }
}
