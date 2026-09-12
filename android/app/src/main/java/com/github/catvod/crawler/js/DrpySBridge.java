package com.github.catvod.crawler.js;

import android.util.Base64;
import android.util.Log;

import androidx.annotation.Keep;

import com.github.tvbox.osc.util.MD5;
import com.github.tvbox.osc.util.OkGoHelper;
import com.whl.quickjs.wrapper.ContextSetter;
import com.whl.quickjs.wrapper.Function;
import com.whl.quickjs.wrapper.JSArray;
import com.whl.quickjs.wrapper.JSCallFunction;
import com.whl.quickjs.wrapper.JSObject;
import com.whl.quickjs.wrapper.JSUtils;
import com.whl.quickjs.wrapper.QuickJSContext;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import okhttp3.Headers;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * drpyS 规则运行时所需的最小 JS 全局桥。
 * 对应 drpy-node（libs/drpyS.js / libs_drpy/drpyCustom.js）暴露给规则的 Node.js 全局，
 * App 端用 QuickJS 等价实现其中的常用子集。
 */
public class DrpySBridge {

    private static final String TAG = "DrpySBridge";
    private static final String DEFAULT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36";
    private static final String MOBILE_UA =
            "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36";
    private QuickJSContext runtime;

    /** 规则里的 PC_UA/MOBILE_UA 等占位符替换为真实 UA（对齐 drpy-node）。 */
    private static String uaOf(String v) {
        if (v == null) return null;
        if ("PC_UA".equals(v)) return DEFAULT_UA;
        if ("MOBILE_UA".equals(v) || "UC_UA".equals(v) || "IOS_UA".equals(v)) return MOBILE_UA;
        return v;
    }

    @ContextSetter
    public void setJSContext(QuickJSContext runtime) {
        this.runtime = runtime;
    }

    private static final class HttpResp {
        int code;
        String body;
        Headers headers;

        HttpResp(int code, String body, Headers headers) {
            this.code = code;
            this.body = body;
            this.headers = headers;
        }
    }

    // ---- 网络核心：阻塞执行一次 HTTP，返回状态码/响应头/响应体 ----

    private HttpResp doHttp(String url, JSObject options) {
        try {
            String method = "GET";
            Headers.Builder hb = new Headers.Builder();
            RequestBody body = null;
            if (options != null) {
                Object m = options.getProperty("method");
                if (m != null) method = String.valueOf(m).toUpperCase();
                Object h = options.getProperty("headers");
                if (h instanceof JSObject) {
                    JSONObject headers = JSUtils.toJsonObject((JSObject) h);
                    Iterator<String> keys = headers.keys();
                    while (keys.hasNext()) {
                        String k = keys.next();
                        hb.add(k, uaOf(String.valueOf(headers.get(k))));
                    }
                }
                Object data = options.getProperty("data");
                Object b = options.getProperty("body");
                String contentType = hb.build().get("Content-Type");
                if ("POST".equals(method)) {
                    if (data != null) {
                        String payload = (data instanceof JSObject)
                                ? JSUtils.toJsonObject((JSObject) data).toString() : String.valueOf(data);
                        body = RequestBody.create(
                                MediaType.get(contentType != null ? contentType : "application/json"),
                                payload);
                    } else if (b != null) {
                        body = RequestBody.create(
                                MediaType.get(contentType != null ? contentType : "text/plain"),
                                String.valueOf(b));
                    } else {
                        body = RequestBody.create(null, "");
                    }
                }
            }
            // 默认浏览器 UA，避免源站把 okhttp/3.x 当成爬虫返回 403（如 aituitu/su.haotv）
            if (hb.build().get("User-Agent") == null) {
                hb.add("User-Agent", DEFAULT_UA);
            }
            OkHttpClient client = OkGoHelper.getDefaultClient();
            Request.Builder rb = new Request.Builder().url(url).headers(hb.build());
            if ("POST".equals(method)) {
                rb.post(body);
            } else {
                rb.get();
            }
            Log.i(TAG, "request-start " + url);
            try (Response res = client.newCall(rb.build()).execute()) {
                Log.i(TAG, "request-code " + res.code() + " " + url);
                if (res.body() == null) return new HttpResp(res.code(), "", res.headers());
                String respBody = res.body().string();
                Log.i(TAG, "request-body-len " + respBody.length() + " hasTagCates=" + respBody.contains("tag_categories") + " hasTagItems=" + respBody.contains("tag_items"));
                return new HttpResp(res.code(), respBody, res.headers());
            }
        } catch (Throwable e) {
            Log.e(TAG, "request failed: " + url + " " + e.getMessage());
            return new HttpResp(0, "", new Headers.Builder().build());
        }
    }

    // ---- 网络：request(url, options) -> 响应体字符串（阻塞，规则内 await 时直接得到字符串） ----

    @Keep
    @Function
    public String request(String url, JSObject options) {
        return doHttp(url, options).body;
    }

    // ---- 网络：_fetch/fetch(url, options) -> 响应对象 {status, headers, text(), json(), content} ----

    @Keep
    @Function
    public JSObject _fetch(String url, JSObject options) {
        HttpResp resp = doHttp(url, options);
        try {
            final String body = resp.body == null ? "" : resp.body;
            JSObject js = runtime.createNewJSObject();
            runtime.setProperty(js, "status", resp.code);
            runtime.setProperty(js, "statusText", resp.code == 200 ? "OK" : String.valueOf(resp.code));
            runtime.setProperty(js, "content", body);
            JSObject jsHeader = runtime.createNewJSObject();
            if (resp.headers != null) {
                for (Map.Entry<String, List<String>> e : resp.headers.toMultimap().entrySet()) {
                    if (e.getValue().size() == 1) {
                        runtime.setProperty(jsHeader, e.getKey(), e.getValue().get(0));
                    } else if (e.getValue().size() > 1) {
                        runtime.setProperty(jsHeader, e.getKey(), new JSUtils<String>().toArray(runtime, e.getValue()));
                    }
                }
            }
            runtime.setProperty(js, "headers", jsHeader);
            runtime.setProperty(js, "text", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    return body;
                }
            });
            runtime.setProperty(js, "json", new JSCallFunction() {
                @Override
                public Object call(Object... args) {
                    try {
                        return runtime.parse(body);
                    } catch (Throwable e) {
                        return body;
                    }
                }
            });
            return js;
        } catch (Throwable e) {
            Log.e(TAG, "_fetch build response failed: " + e.getMessage());
            return runtime.createNewJSObject();
        }
    }

    @Keep
    @Function
    public String fetch(String url, JSObject options) {
        // drpyS 约定：fetch = request，返回响应体字符串（规则做 JSON.parse/eval）。
        // 浏览器式 fetch 对象在 _fetch 提供。
        return request(url, options);
    }

    @Keep
    @Function
    public String md5(String str) {
        try {
            return MD5.encode(str == null ? "" : str);
        } catch (Throwable e) {
            return "";
        }
    }

    // ---- Base64（btoa/atob 为二进制字符串语义，字符码 0-255） ----

    @Keep
    @Function
    public String btoa(String binaryStr) {
        try {
            byte[] bytes = new byte[binaryStr == null ? 0 : binaryStr.length()];
            for (int i = 0; i < bytes.length; i++) {
                bytes[i] = (byte) (binaryStr.charAt(i) & 0xff);
            }
            return Base64.encodeToString(bytes, Base64.NO_WRAP);
        } catch (Throwable e) {
            return "";
        }
    }

    @Keep
    @Function
    public String atob(String base64) {
        try {
            byte[] bytes = Base64.decode(base64, Base64.NO_WRAP);
            StringBuilder sb = new StringBuilder(bytes.length);
            for (byte b : bytes) sb.append((char) (b & 0xff));
            return sb.toString();
        } catch (Throwable e) {
            return "";
        }
    }

    // ---- 标准 JS escape/unescape（Annex B，drpyS 规则与 crypto-js 依赖） ----

    @Keep
    @Function
    public String unescape(String str) {
        if (str == null) return "";
        StringBuilder sb = new StringBuilder(str.length());
        int i = 0;
        while (i < str.length()) {
            char c = str.charAt(i);
            if (c == '%' && i + 5 < str.length() && str.charAt(i + 1) == 'u') {
                try {
                    int v = Integer.parseInt(str.substring(i + 2, i + 6), 16);
                    sb.append((char) v);
                    i += 6;
                    continue;
                } catch (Throwable ignored) {
                }
            } else if (c == '%' && i + 2 < str.length()) {
                try {
                    int v = Integer.parseInt(str.substring(i + 1, i + 3), 16);
                    sb.append((char) v);
                    i += 3;
                    continue;
                } catch (Throwable ignored) {
                }
            }
            sb.append(c);
            i++;
        }
        return sb.toString();
    }

    @Keep
    @Function
    public String escape(String str) {
        if (str == null) return "";
        StringBuilder sb = new StringBuilder(str.length());
        for (int i = 0; i < str.length(); i++) {
            char c = str.charAt(i);
            if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
                    || c == '@' || c == '*' || c == '_' || c == '+' || c == '-' || c == '.' || c == '/') {
                sb.append(c);
            } else if (c < 256) {
                sb.append('%').append(String.format("%02X", (int) c));
            } else {
                sb.append("%u").append(String.format("%04X", (int) c));
            }
        }
        return sb.toString();
    }

    // ---- 日志 ----

    @Keep
    @Function
    public void log(Object... args) {
        StringBuilder sb = new StringBuilder();
        if (args != null) {
            for (Object a : args) sb.append(a == null ? "null" : a.toString()).append(' ');
        }
        Log.i(TAG, sb.toString().trim());
    }

    @Keep
    @Function
    public void print(Object... args) {
        if (args == null) return;
        StringBuilder sb = new StringBuilder();
        for (Object a : args) sb.append(a == null ? "null" : a.toString()).append(' ');
        Log.i(TAG, sb.toString().trim());
    }

    // ---- req(url, options) -> {content, status}（_lib.request 等依赖的 drpyS 请求全局） ----

    @Keep
    @Function
    public JSObject req(String url, JSObject options) {
        HttpResp resp = doHttp(url, options);
        JSObject js = runtime.createNewJSObject();
        runtime.setProperty(js, "content", resp.body == null ? "" : resp.body);
        runtime.setProperty(js, "status", resp.code);
        return js;
    }

    // ---- 提供 fetch 别名（部分规则直接调用 fetch(url, opts) 期望 {status, text()}） ----

    @Keep
    @Function
    public String fetchText(String url, JSObject options) {
        return request(url, options);
    }

    @Keep
    @Function
    public String base64Encode(String str) {
        try {
            return Base64.encodeToString((str == null ? "" : str).getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        } catch (Throwable e) {
            return "";
        }
    }

    @Keep
    @Function
    public String base64Decode(String str) {
        try {
            return new String(Base64.decode(str, Base64.NO_WRAP), StandardCharsets.UTF_8);
        } catch (Throwable e) {
            return "";
        }
    }

    // ---- drpyS HTML 解析（对齐 drpy-node 的 jsoup pdfa/pdfh/pd，复用 catvod HtmlParser） ----

    @Keep
    @Function
    public JSArray pdfa(String html, String rule) {
        try {
            if (html == null || html.isEmpty()) return runtime.createNewJSArray();
            return new JSUtils<String>().toArray(runtime, HtmlParser.parseDomForArray(html, rule));
        } catch (Throwable e) {
            return runtime.createNewJSArray();
        }
    }

    @Keep
    @Function
    public String pdfh(String html, String rule) {
        try {
            if (html == null || html.isEmpty()) return "";
            return HtmlParser.parseDomForUrl(html, rule, "");
        } catch (Throwable e) {
            return "";
        }
    }

    @Keep
    @Function
    public String pd(String html, String rule, String addUrl) {
        try {
            if (html == null || html.isEmpty()) return "";
            return HtmlParser.parseDomForUrl(html, rule, addUrl);
        } catch (Throwable e) {
            return "";
        }
    }

    // ---- URL 工具 ----

    @Keep
    @Function
    public String joinUrl(String parent, String child) {
        return HtmlParser.joinUrl(parent, child);
    }

    @Keep
    @Function
    public String urljoin(String parent, String child) {
        return HtmlParser.joinUrl(parent, child);
    }

    @Keep
    @Function
    public String buildUrl(String url, JSObject params) {
        StringBuilder sb = new StringBuilder(url == null ? "" : url);
        if (sb.indexOf("?") < 0) sb.append('?');
        List<String> pairs = new ArrayList<>();
        if (params != null) {
            try {
                JSONObject jo = JSUtils.toJsonObject(params);
                Iterator<String> keys = jo.keys();
                while (keys.hasNext()) {
                    String k = keys.next();
                    Object v = jo.opt(k);
                    pairs.add(k + "=" + (v == null ? "" : String.valueOf(v)));
                }
            } catch (Throwable ignored) {
            }
        }
        if (!pairs.isEmpty() && !sb.toString().endsWith("?")) sb.append('&');
        for (int i = 0; i < pairs.size(); i++) {
            if (i > 0) sb.append('&');
            sb.append(pairs.get(i));
        }
        return sb.toString();
    }

    @Keep
    @Function
    public String buildQueryString(JSObject params) {
        List<String> pairs = new ArrayList<>();
        if (params != null) {
            try {
                JSONObject jo = JSUtils.toJsonObject(params);
                Iterator<String> keys = jo.keys();
                while (keys.hasNext()) {
                    String k = keys.next();
                    Object v = jo.opt(k);
                    pairs.add(java.net.URLEncoder.encode(k, "UTF-8") + "="
                            + java.net.URLEncoder.encode(v == null ? "" : String.valueOf(v), "UTF-8"));
                }
            } catch (Throwable ignored) {
            }
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < pairs.size(); i++) {
            if (i > 0) sb.append('&');
            sb.append(pairs.get(i));
        }
        return sb.toString();
    }

    @Keep
    @Function
    public JSObject parseQueryString(String query) {
        JSObject result = runtime.createNewJSObject();
        if (query == null || query.isEmpty()) return result;
        String[] pairs = query.split("&");
        for (String pair : pairs) {
            int idx = pair.indexOf('=');
            String k = idx < 0 ? pair : pair.substring(0, idx);
            String v = idx < 0 ? "" : pair.substring(idx + 1);
            if (!k.isEmpty()) {
                try {
                    runtime.setProperty(result,
                            java.net.URLDecoder.decode(k, "UTF-8"),
                            v.isEmpty() ? "" : java.net.URLDecoder.decode(v, "UTF-8"));
                } catch (Throwable ignored) {
                }
            }
        }
        return result;
    }
}
