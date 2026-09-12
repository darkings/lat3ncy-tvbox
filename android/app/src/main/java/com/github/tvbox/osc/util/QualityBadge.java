package com.github.tvbox.osc.util;

import android.text.TextUtils;
import android.view.View;
import android.widget.TextView;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.lzy.okgo.OkGo;
import com.lzy.okgo.callback.AbsCallback;
import com.lzy.okgo.model.Response;

import java.lang.ref.WeakReference;
import java.net.URLEncoder;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 搜索页海报右上角清晰度角标。
 *
 * <p>客户端搜索到的每张卡片带 sourceKey + vod_name，本工具据此异步查询服务器
 * {@code GET https://api.ponyo.fun/quality?src=<sourceKey>&title=<片名>}，
 * 命中返回 {"tier":"fhd","label":"1080P",...}，把 label 贴到右上角；未命中
 * （{"tier":null}）则保持隐藏。</p>
 *
 * <p>设计要点：</p>
 * <ul>
 *   <li>内存缓存（key=sourceKey+title），同次会话不重复请求；null 结果也缓存，
 *       避免对未探测影片反复打服务器。</li>
 *   <li>防错位：RecyclerView 复用 View 时，用 tag 比对当前绑定项，过期回调不写 UI。</li>
 *   <li>失败静默：网络/解析异常一律不显示角标，不影响列表。</li>
 * </ul>
 */
public final class QualityBadge {

    private static final String API = "https://api.ponyo.fun/quality";

    /** 结果缓存：key → label（空串表示已查过但无清晰度，不再重复请求）。 */
    private static final ConcurrentHashMap<String, String> CACHE = new ConcurrentHashMap<>();

    private QualityBadge() {
    }

    /**
     * 为搜索卡片绑定清晰度角标。
     *
     * @param view      右上角 tvQuality TextView
     * @param sourceKey 卡片所属源（客户端 sourceKey）
     * @param title     影片名（vod_name）
     */
    public static void bind(TextView view, String sourceKey, String title) {
        if (view == null) {
            return;
        }
        if (TextUtils.isEmpty(sourceKey) || TextUtils.isEmpty(title)) {
            view.setVisibility(View.GONE);
            return;
        }
        String key = sourceKey + "|" + title;
        // 记录当前绑定项，回调时比对防止 RecyclerView 复用错位
        view.setTag(key);

        String cached = CACHE.get(key);
        if (cached != null) {
            apply(view, key, cached);
            return;
        }

        // 默认先隐藏，避免复用时残留上一项的角标
        view.setVisibility(View.GONE);

        String url = API + "?src=" + enc(sourceKey) + "&title=" + enc(title);
        final WeakReference<TextView> ref = new WeakReference<>(view);
        OkGo.<String>get(url)
                .tag("quality_" + key)
                .execute(new AbsCallback<String>() {
                    @Override
                    public String convertResponse(okhttp3.Response response) throws Throwable {
                        if (response.body() != null) {
                            return response.body().string();
                        }
                        throw new IllegalStateException("quality empty body");
                    }

                    @Override
                    public void onSuccess(Response<String> response) {
                        String label = parseLabel(response.body());
                        CACHE.put(key, label); // 含空串：已查无数据，本会话不再查
                        TextView v = ref.get();
                        if (v != null) {
                            apply(v, key, label);
                        }
                    }

                    @Override
                    public void onError(Response<String> response) {
                        // 网络失败不缓存（允许下次重试），仅保持隐藏
                        TextView v = ref.get();
                        if (v != null) {
                            v.setVisibility(View.GONE);
                        }
                    }
                });
    }

    /** 解析服务器返回，命中返回 label（如 1080P），未命中/异常返回空串。 */
    private static String parseLabel(String body) {
        if (TextUtils.isEmpty(body)) {
            return "";
        }
        try {
            JsonObject obj = JsonParser.parseString(body).getAsJsonObject();
            if (obj.has("label") && !obj.get("label").isJsonNull()) {
                String label = obj.get("label").getAsString();
                return label == null ? "" : label.trim();
            }
        } catch (Throwable ignored) {
        }
        return "";
    }

    /** 把 label 写到角标（仅当 View 仍绑定同一项时），空串则隐藏。 */
    private static void apply(TextView view, String expectKey, String label) {
        Object tag = view.getTag();
        if (!(tag instanceof String) || !tag.equals(expectKey)) {
            return; // View 已被复用到别的卡片，丢弃过期回调
        }
        if (TextUtils.isEmpty(label)) {
            view.setVisibility(View.GONE);
        } else {
            view.setText(label);
            view.setVisibility(View.VISIBLE);
        }
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");
        } catch (Throwable th) {
            return s;
        }
    }
}
