package com.github.catvod.crawler.js;

import android.content.Context;
import android.text.TextUtils;
import android.util.Log;

import com.github.tvbox.osc.util.LOG;

import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import fi.iki.elonen.NanoHTTPD;

/**
 * 本地 drpyS 服务：监听 127.0.0.1:5757，把 type-4 源的 /api/:module 请求
 * 路由到 DrpySRuntime（QuickJS 执行本地缓存的 drpyS 规则）。
 *
 * 请求协议与 drpy-node 一致：
 * - filter=true            -> 首页 class_parse
 * - ac=detail&t=&pg=       -> 分类 一级
 * - ac=detail&ids=         -> 详情 二级
 * - wd=                    -> 搜索 搜索
 * - play=&flag=            -> 播放 lazy
 */
public class DrpySServer extends NanoHTTPD {

    private static final String TAG = "DrpySServer";
    private final File rulesDir;
    // 规则热更新支持：记录每个 runtime 加载时的文件 sha256，
    // getRuntime 时 sha 变化（DrpySRuleManager.sync 已覆盖文件）则销毁旧 runtime 重建。
    // 修复：App 启动时首页请求先于 sync 完成 -> 旧规则被 putIfAbsent 缓存 -> 
    //       sync 后文件已新但缓存仍是旧版（实测哔哩影视线路顺序 39ms 竞态）。
    private final java.util.Map<String, String> runtimeShas = new java.util.concurrent.ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, DrpySRuntime> runtimes = new ConcurrentHashMap<>();

    public DrpySServer(Context context, File rulesDir) {
        super(5757);
        this.rulesDir = rulesDir;
    }

    public void startQuietly() {
        try {
            start(10000, false);
            LOG.i("echo-drpys-server-started 5757");
        } catch (IOException e) {
            LOG.i("echo-drpys-server-start-error " + e.getMessage());
        }
    }

    @Override
    public Response serve(IHTTPSession session) {
        try {
            String uri = session.getUri();
            if (uri == null) return notFound();
            String path = uri;
            int q = path.indexOf('?');
            if (q >= 0) path = path.substring(0, q);
            // /api/:module
            if (!path.startsWith("/api/")) return notFound();
            String module = path.substring(5);
            if (TextUtils.isEmpty(module)) return notFound();
            module = decodeModule(module);

            Map<String, String> params = session.getParms();
            String ac = params.get("ac");
            String wd = params.get("wd");
            String play = params.get("play");
            String t = params.get("t");
            String pg = params.get("pg");
            String ids = params.get("ids");
            String flag = params.get("flag");
            String filter = params.get("filter");

            DrpySRuntime runtime = getRuntime(module);
            if (runtime == null) return jsonError("rule not found: " + module);

            String result;
            if (!TextUtils.isEmpty(play)) {
                // drpy-node: play(flag, id) -> lazy 的 this.input = id(=play 参数)，this.flag = flag
                result = runtime.playContent(play, flag);
            } else if (!TextUtils.isEmpty(wd)) {
                result = runtime.searchContent(wd, pg == null ? "1" : pg);
            } else if (!TextUtils.isEmpty(ids)) {
                result = runtime.detailContent(ids);
            } else if ("detail".equals(ac) && !TextUtils.isEmpty(t)) {
                // ext = base64(JSON) 筛选参数（TVBox type=4 协议），解析后传给规则一级 MY_FL
                result = runtime.categoryContent(t, pg == null ? "1" : pg, decodeExtFilters(params.get("ext")));
            } else {
                // filter=true 或缺省 -> 首页
                result = runtime.homeContent("true".equals(filter) || "1".equals(filter));
            }
            if (result == null) result = "{}";
            return json(result);
        } catch (Throwable e) {
            Log.e(TAG, "serve error: " + e.getMessage());
            return jsonError("internal error");
        }
    }

    private DrpySRuntime getRuntime(String module) {
        File f = new File(rulesDir, module + ".js");
        if (!f.isFile()) return null;
        String js = readFile(f);
        if (js == null || js.trim().isEmpty()) return null;
        // 当前文件内容指纹（sha256 前 16 位足够检测变化，避免全量 hex 浪费）
        String sha = sha16(js);
        DrpySRuntime r = runtimes.get(module);
        if (r != null && sha.equals(runtimeShas.get(module))) {
            return r;  // 缓存命中且文件未变
        }
        if (r != null) {
            // 文件已变（sync 热更新）：销毁旧 runtime，加载新版
            try { r.destroy(); } catch (Throwable ignored) {}
            runtimes.remove(module);
        }
        DrpySRuntime rt = new DrpySRuntime();
        if (!rt.loadRule(js)) {
            rt.destroy();
            return null;
        }
        runtimeShas.put(module, sha);
        DrpySRuntime prev = runtimes.putIfAbsent(module, rt);
        return prev != null ? prev : rt;
    }

    /** 内容指纹：sha256 前 16 个 hex 字符（快速变化检测）。 */
    private static String sha16(String s) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 8; i++) sb.append(String.format("%02x", d[i]));
            return sb.toString();
        } catch (Throwable e) {
            return String.valueOf(s.hashCode());  // 兜底：退化用 hashCode
        }
    }

    /**
     * 解析 TVBox type=4 协议的 ext 筛选参数：base64({"key":"value",...})。
     * 值为空字符串的键（"全部"等占位）跳过，不传给规则。
     */
    private java.util.Map<String, String> decodeExtFilters(String ext) {
        if (ext == null || ext.trim().isEmpty()) return null;
        try {
            byte[] decoded = android.util.Base64.decode(ext, android.util.Base64.DEFAULT);
            String json = new String(decoded, "UTF-8");
            org.json.JSONObject obj = new org.json.JSONObject(json);
            java.util.Map<String, String> fl = new java.util.HashMap<>();
            java.util.Iterator<String> keys = obj.keys();
            while (keys.hasNext()) {
                String k = keys.next();
                String v = obj.optString(k, "");
                if (!v.isEmpty()) fl.put(k, v);
            }
            return fl.isEmpty() ? null : fl;
        } catch (Throwable e) {
            Log.w(TAG, "decode ext filters failed: " + e.getMessage());
            return null;
        }
    }

    private String decodeModule(String module) {
        try {
            if (module.contains("%")) {
                return java.net.URLDecoder.decode(module, "UTF-8");
            }
        } catch (Throwable ignored) {}
        return module;
    }

    private String readFile(File f) {
        try {
            byte[] bytes = new byte[(int) f.length()];
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            try {
                int off = 0, n;
                while (off < bytes.length && (n = in.read(bytes, off, bytes.length - off)) >= 0) {
                    off += n;
                }
            } finally {
                in.close();
            }
            return new String(bytes, "UTF-8");
        } catch (Throwable e) {
            return null;
        }
    }

    private Response json(String body) {
        return NanoHTTPD.newFixedLengthResponse(
                Response.Status.OK, "application/json; charset=utf-8", body);
    }

    private Response jsonError(String msg) {
        return NanoHTTPD.newFixedLengthResponse(
                Response.Status.OK, "application/json; charset=utf-8",
                "{\"error\":\"" + msg + "\"}");
    }

    private Response notFound() {
        return NanoHTTPD.newFixedLengthResponse(
                Response.Status.NOT_FOUND, NanoHTTPD.MIME_PLAINTEXT, "404");
    }

    public void destroyAll() {
        for (DrpySRuntime r : runtimes.values()) r.destroy();
        runtimes.clear();
    }
}
