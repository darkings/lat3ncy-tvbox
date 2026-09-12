package com.github.catvod.crawler.js;

import android.text.TextUtils;
import android.util.Log;

import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.App;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.OkGoHelper;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.URLEncoder;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * drpyS 规则拉取与缓存：订阅刷新后，遍历 type-4 源得到 module 名，
 * 从 children-api 的 /drpys/manifest + /drpys/rule 增量更新本地 files/drpys/。
 */
public class DrpySRuleManager {

    private static final String TAG = "DrpySRuleManager";
    private static final String DEFAULT_BASE = "https://api.ponyo.fun/drpys/";
    private static final ExecutorService executor = Executors.newSingleThreadExecutor();
    private static final Set<String> syncing = new HashSet<>();

    public static File rulesDir() {
        File dir = new File(App.getInstance().getFilesDir(), "drpys");
        if (!dir.exists()) dir.mkdirs();
        return dir;
    }

    public static void syncAsync() {
        synchronized (syncing) {
            if (!syncing.isEmpty()) return;
            syncing.add("busy");
        }
        executor.execute(() -> {
            try {
                sync();
            } catch (Throwable e) {
                Log.e(TAG, "sync error: " + e.getMessage());
            } finally {
                synchronized (syncing) {
                    syncing.clear();
                }
            }
        });
    }

    private static void sync() throws IOException {
        List<String> modules = type4Modules();
        if (modules.isEmpty()) return;
        String base = drpysBase();
        Map<String, String> manifest = fetchManifest(base);
        if (manifest == null || manifest.isEmpty()) {
            Log.w(TAG, "sync abort: manifest empty, base=" + base);
            return;
        }
        Log.i(TAG, "sync: " + modules.size() + " modules, manifest " + manifest.size() + " entries");

        File dir = rulesDir();
        Set<String> libs = new HashSet<>();
        for (String module : modules) {
            String sha = manifest.get(module);
            if (sha == null) continue;
            File f = new File(dir, module + ".js");
            String js;
            if (f.isFile() && sha.equals(sha256(f))) {
                js = readFile(f); // 未变，读现有内容以扫描 _lib 依赖
            } else {
                js = fetchRule(base, module);
                if (js == null || js.trim().isEmpty() || js.trim().startsWith("{\"error\"")) continue;
                writeFile(f, js);
                LOG.i("echo-drpys-rule-updated " + module);
            }
            libs.addAll(libDeps(js));
        }
        // 拉取 _lib 依赖（仅 .js；.cjs 需服务器端扩展后再支持）
        for (String lib : libs) {
            if (!lib.endsWith(".js")) continue;
            String libModule = lib.substring(0, lib.length() - 3); // 去掉 .js
            String sha = manifest.get(libModule);
            if (sha == null) continue;
            File f = new File(dir, lib);
            if (f.isFile() && sha.equals(sha256(f))) continue;
            String js = fetchRule(base, libModule);
            if (js == null || js.trim().isEmpty() || js.trim().startsWith("{\"error\"")) continue;
            writeFile(f, js);
            LOG.i("echo-drpys-lib-updated " + lib);
        }
    }

    private static final java.util.regex.Pattern LIB_REQ =
            java.util.regex.Pattern.compile("require\\(['\"](\\./)?(_lib[\\w.\\-]+)['\"]\\)");

    /** 扫描规则 JS 里 require('./_lib.xxx.js') / $.require(...) 引用的本地依赖名。 */
    private static Set<String> libDeps(String js) {
        Set<String> set = new HashSet<>();
        if (js == null || js.isEmpty()) return set;
        java.util.regex.Matcher m = LIB_REQ.matcher(js);
        while (m.find()) {
            String lib = m.group(2);
            if (lib != null && !lib.isEmpty()) set.add(lib);
        }
        return set;
    }

    private static String readFile(File f) {
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
            return "";
        }
    }

    private static List<String> type4Modules() {
        List<String> modules = new ArrayList<>();
        try {
            List<SourceBean> list = ApiConfig.get().getSourceBeanList();
            for (SourceBean sb : list) {
                if (sb == null || sb.getType() != 4) continue;
                String api = sb.getApi();
                if (api == null) continue;
                String module = moduleOf(api);
                if (module != null) modules.add(module);
            }
        } catch (Throwable e) {
            Log.e(TAG, "type4Modules error: " + e.getMessage());
        }
        return modules;
    }

    private static String moduleOf(String api) {
        try {
            java.net.URL u = new java.net.URL(api);
            String p = u.getPath();
            int idx = p.indexOf("/api/");
            if (idx < 0) return null;
            String module = p.substring(idx + 5);
            if (module.endsWith("/")) module = module.substring(0, module.length() - 1);
            return module.isEmpty() ? null : module;
        } catch (Throwable e) {
            return null;
        }
    }

    private static String drpysBase() {
        // drpy 规则服务器是 App 固定后端，与订阅地址无关。
        // 原实现跟随订阅主机（API_URL），当订阅托管在 CDN（如 cdn.jsdelivr.net）时
        // 会拼出 https://cdn.jsdelivr.net/drpys/ 这种无效地址，导致 manifest 为空、
        // 规则永远不同步。这里固定使用 DEFAULT_BASE，仅允许订阅主机本身就是
        // api.ponyo.fun 时保持等价行为。
        return DEFAULT_BASE;
    }

    private static Map<String, String> fetchManifest(String base) {
        String json = httpGet(base + "manifest");
        if (json == null || json.trim().isEmpty() || !json.trim().startsWith("{")) return null;
        try {
            JSONObject obj = new JSONObject(json);
            java.util.HashMap<String, String> map = new java.util.HashMap<>();
            java.util.Iterator<String> keys = obj.keys();
            while (keys.hasNext()) {
                String k = keys.next();
                map.put(k, obj.getString(k));
            }
            return map;
        } catch (Throwable e) {
            return null;
        }
    }

    private static String fetchRule(String base, String module) {
        try {
            return httpGet(base + "rule?name=" + URLEncoder.encode(module, "UTF-8"));
        } catch (Throwable e) {
            return null;
        }
    }

    private static String httpGet(String url) {
        try {
            OkHttpClient client = OkGoHelper.getDefaultClient();
            Request request = new Request.Builder().url(url)
                    .header("User-Agent", "Mozilla/5.0").get().build();
            try (Response res = client.newCall(request).execute()) {
                if (res.body() == null) return null;
                return res.body().string();
            }
        } catch (Throwable e) {
            Log.e(TAG, "httpGet error " + url + " " + e.getMessage());
            return null;
        }
    }

    private static String sha256(File f) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) >= 0) md.update(buf, 0, n);
            in.close();
            byte[] d = md.digest();
            StringBuilder sb = new StringBuilder();
            for (byte b : d) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Throwable e) {
            return "";
        }
    }

    private static void writeFile(File f, String content) {
        try (FileOutputStream out = new FileOutputStream(f)) {
            out.write(content.getBytes("UTF-8"));
        } catch (Throwable e) {
            Log.e(TAG, "writeFile error: " + e.getMessage());
        }
    }
}
