package com.github.tvbox.osc.util;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.text.TextUtils;
import android.widget.ImageView;

import androidx.annotation.Nullable;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.DataSource;
import com.bumptech.glide.load.DecodeFormat;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.bumptech.glide.load.engine.GlideException;
import com.bumptech.glide.load.model.GlideUrl;
import com.bumptech.glide.load.model.LazyHeaders;
import com.bumptech.glide.load.resource.bitmap.CenterCrop;
import com.bumptech.glide.load.resource.bitmap.FitCenter;
import com.bumptech.glide.load.resource.bitmap.RoundedCorners;
import com.bumptech.glide.request.RequestListener;
import com.bumptech.glide.request.RequestOptions;
import com.bumptech.glide.request.target.Target;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.App;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

import me.jessyan.autosize.utils.AutoSizeUtils;

public class ImgUtil {
    private static final Map<String, Drawable> drawableCache = new HashMap<>();

    // ===== 域名级自动请求头规则 =====
    // key   : 域名后缀（小写，匹配 host 本身或其任意子域，如 "doubanio.com" 可命中 img2/img9.doubanio.com）
    // value : 需要自动注入的请求头集合
    // 背景：豆瓣 CDN 按 Referer 白名单反爬（实测无 Referer 返回 418，
    //       带任意 *.douban.com 的 Referer 返回 200），而 CMS 源返回的豆瓣海报 URL
    //       不带 @Referer= 内嵌指令，因此按域名自动补齐 Referer
    private static final Map<String, Map<String, String>> HOST_HEADER_RULES = new HashMap<>();

    static {
        // 豆瓣图片 CDN：自动注入豆瓣自家 Referer 即可通过反爬校验（实测 200）
        Map<String, String> doubanHeaders = new HashMap<>();
        doubanHeaders.put("Referer", "https://movie.douban.com/");
        HOST_HEADER_RULES.put("doubanio.com", doubanHeaders);
    }
    public static int defaultWidth = 244;
    public static int defaultHeight = 320;

    public static class Style {
        public float ratio;
        public String type;

        public Style(float ratio, String type) {
            this.ratio = ratio;
            this.type = type;
        }
    }

    public static boolean isBase64Image(String picUrl) {
        return picUrl != null && picUrl.startsWith("data:image");
    }

    public static Style initStyle() {
        String bStyle = ApiConfig.get().getHomeSourceBean().getStyle();
        if (!bStyle.isEmpty()) {
            try {
                JSONObject jsonObject = new JSONObject(bStyle);
                return new Style((float) jsonObject.getDouble("ratio"), jsonObject.getString("type"));
            } catch (JSONException ignored) {
            }
        }
        return null;
    }

    public static int spanCountByStyle(Style style, int defaultCount) {
        int spanCount = defaultCount;
        if ("rect".equals(style.type)) {
            if (style.ratio >= 1.7) {
                spanCount = 3;
            } else if (style.ratio >= 1.3) {
                spanCount = 4;
            }
        } else if ("list".equals(style.type)) {
            spanCount = 1;
        }
        return spanCount;
    }

    public static int getStyleDefaultWidth(Style style) {
        int styleDefaultWidth = 280;
        if (style.ratio < 1) styleDefaultWidth = 214;
        if (style.ratio > 1.7) styleDefaultWidth = 380;
        return styleDefaultWidth;
    }

    public static Bitmap decodeBase64ToBitmap(String base64Str) {
        String base64Data = base64Str.substring(base64Str.indexOf(",") + 1);
        byte[] decodedBytes = android.util.Base64.decode(base64Data, android.util.Base64.DEFAULT);
        return BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.length);
    }

    public static void load(String url, ImageView view, int roundingRadius) {
        load(url, view, roundingRadius, 0, 0, null);
    }

    public static void load(String url, ImageView view, int roundingRadius, int newWidth, int newHeight) {
        load(url, view, roundingRadius, newWidth, newHeight, null);
    }

    public static void load(String url, ImageView view, int roundingRadius, int newWidth, int newHeight, String label, ImageView.ScaleType scaleType) {
        view.setScaleType(scaleType);
        if (roundingRadius <= 0) roundingRadius = 1;
        Drawable placeholder = createImagePlaceholderDrawable(newWidth, newHeight, roundingRadius);
        Drawable fallback = placeholder;
        if (isInvalidImageUrl(url)) {
            view.setImageDrawable(fallback);
            return;
        }
        RequestOptions options = new RequestOptions()
                .format(DecodeFormat.PREFER_RGB_565)
                .diskCacheStrategy(DiskCacheStrategy.AUTOMATIC)
                .dontAnimate()
                .transform(new FitCenter(), new RoundedCorners(roundingRadius));
        if (newWidth > 0 && newHeight > 0) {
            options = options.override(newWidth, newHeight);
        }
        Glide.with(App.getInstance())
                .asBitmap()
                .load(getUrl(url))
                .placeholder(placeholder)
                .error(fallback)
                .listener(getListener(view, scaleType, fallback, url))
                .apply(options)
                .into(view);
    }

    public static void load(String url, ImageView view, int roundingRadius, int newWidth, int newHeight, String label) {
        view.setScaleType(ImageView.ScaleType.CENTER_CROP);
        if (roundingRadius <= 0) roundingRadius = 1;
        Drawable fallback = createImagePlaceholderDrawable(newWidth, newHeight, roundingRadius);
        Drawable placeholder = createImagePlaceholderDrawable(newWidth, newHeight, roundingRadius);
        if (isInvalidImageUrl(url)) {
            view.setImageDrawable(fallback);
            return;
        }
        RequestOptions options = new RequestOptions()
                .format(DecodeFormat.PREFER_RGB_565)
                .diskCacheStrategy(DiskCacheStrategy.AUTOMATIC)
                .dontAnimate()
                .transform(new CenterCrop(), new RoundedCorners(roundingRadius));
        if (newWidth > 0 && newHeight > 0) {
            options = options.override(newWidth, newHeight);
        }
        Glide.with(App.getInstance())
                .asBitmap()
                .load(getUrl(url))
                .placeholder(placeholder)
                .error(fallback)
                .listener(getListener(view, ImageView.ScaleType.CENTER_CROP, fallback, url))
                .apply(options)
                .into(view);
    }

    public static void loadUrl(String url, ImageView view) {
        load(url, view, 10);
    }

    public static void loadVideoScreenshot(String uri, ImageView imageView, long frameTimeMicros) {
        RequestOptions requestOptions = RequestOptions.frameOf(frameTimeMicros * 1000)
                .transform(new CenterCrop(), new RoundedCorners(10));
        Glide.with(App.getInstance())
                .load(uri)
                .skipMemoryCache(true)
                .apply(requestOptions)
                .into(imageView);
    }

    public static int getRandomColor() {
        Random random = new Random();
        return Color.argb(255, random.nextInt(256), random.nextInt(256), random.nextInt(256));
    }

    public static Drawable createTextDrawable(String text) {
        return createTextDrawable(text, 0, 0, AutoSizeUtils.mm2px(App.getInstance(), 10));
    }

    private static Drawable createTextDrawable(String text, int width, int height, float cornerRadius) {
        if (TextUtils.isEmpty(text)) text = "TVBox";
        if (width <= 0) width = 180;
        if (height <= 0) height = 240;
        if (cornerRadius <= 0) cornerRadius = 1;
        String key = text + "_" + width + "x" + height + "_" + (int) cornerRadius;
        text = text.substring(0, 1);
        if (drawableCache.containsKey(key)) return drawableCache.get(key);
        int randomColor = getRandomColor();
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(randomColor);
        paint.setStyle(Paint.Style.FILL);
        RectF rectF = new RectF(0, 0, width, height);
        canvas.drawRoundRect(rectF, cornerRadius, cornerRadius, paint);
        paint.setColor(Color.WHITE);
        paint.setTextSize(60);
        paint.setTextAlign(Paint.Align.CENTER);
        Paint.FontMetrics fontMetrics = paint.getFontMetrics();
        float x = width / 2f;
        float y = (height - fontMetrics.bottom - fontMetrics.top) / 2f;
        canvas.drawText(text, x, y, paint);
        Drawable drawable = new BitmapDrawable(App.getInstance().getResources(), bitmap);
        drawableCache.put(key, drawable);
        return drawable;
    }

    public static Drawable createImagePlaceholderDrawable(int width, int height, float cornerRadius) {
        if (width <= 0) width = 180;
        if (height <= 0) height = 240;
        if (cornerRadius <= 0) cornerRadius = 1;
        String key = "placeholder_" + width + "x" + height + "_" + (int) cornerRadius;
        if (drawableCache.containsKey(key)) return drawableCache.get(key);

        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);

        Drawable icon = App.getInstance().getResources().getDrawable(
                com.github.tvbox.osc.R.drawable.icon_img_placeholder);
        if (icon != null) {
            int iconWidth = icon.getIntrinsicWidth();
            int iconHeight = icon.getIntrinsicHeight();
            if (iconWidth <= 0) iconWidth = Math.min(width, height) / 4;
            if (iconHeight <= 0) iconHeight = Math.min(width, height) / 4;
            int maxIconSize = Math.max(1, Math.min(width, height) / 4);
            float scale = Math.min(1f, Math.min((float) maxIconSize / iconWidth,
                    (float) maxIconSize / iconHeight));
            iconWidth = Math.max(1, Math.round(iconWidth * scale));
            iconHeight = Math.max(1, Math.round(iconHeight * scale));
            int left = (width - iconWidth) / 2;
            int top = (height - iconHeight) / 2;
            icon.setBounds(left, top, left + iconWidth, top + iconHeight);
            icon.draw(canvas);
        }

        Drawable drawable = new BitmapDrawable(App.getInstance().getResources(), bitmap);
        drawableCache.put(key, drawable);
        return drawable;
    }

    public static void clearCache() {
        drawableCache.clear();
    }

    public static void clearMemoryCache() {
        clearCache();
        try {
            Glide.get(App.getInstance()).clearMemory();
            LOG.i("echo-img-clear-memory-cache");
        } catch (Throwable th) {
            LOG.i("echo-img-clear-memory-cache-error:" + th.getMessage());
        }
    }

    private static Object getUrl(String url) {
        if (url.startsWith("data:")) return url;
        String header = null;
        String referer = null;
        String ua = null;
        String cookie = null;
        if (url.contains("@Headers=")) {
            header = url.split("@Headers=")[1].split("@")[0];
            try {
                header = URLDecoder.decode(header, "UTF-8");
            } catch (UnsupportedEncodingException ignored) {
            }
        }
        if (url.contains("@Cookie=")) cookie = url.split("@Cookie=")[1].split("@")[0];
        if (url.contains("@User-Agent=")) ua = url.split("@User-Agent=")[1].split("@")[0];
        if (url.contains("@Referer=")) referer = url.split("@Referer=")[1].split("@")[0];
        url = url.split("@")[0];
        if (TextUtils.isEmpty(url)) return null;

        LazyHeaders.Builder builder = new LazyHeaders.Builder();
        Map<String, String> headers = new HashMap<>();
        if (!TextUtils.isEmpty(header)) {
            try {
                JsonObject jsonInfo = new Gson().fromJson(header, JsonObject.class);
                for (String key : jsonInfo.keySet()) {
                    putHeader(headers, key, jsonInfo.get(key).getAsString());
                }
            } catch (Throwable ignored) {
            }
        }
        putHeader(headers, "Cookie", cookie);
        if (!TextUtils.isEmpty(ua)) putHeader(headers, "User-Agent", ua);
        if (!TextUtils.isEmpty(referer)) putHeader(headers, "Referer", referer);
        // ===== 域名级自动请求头注入 =====
        // URL 内嵌指令（@Referer= 等）优先级更高：只有当 CMS 没有显式指定该头时，
        // 才按域名规则自动注入，避免覆盖源站特意配置的请求头
        for (Map.Entry<String, Map<String, String>> rule : HOST_HEADER_RULES.entrySet()) {
            if (hostMatches(url, rule.getKey())) {
                for (Map.Entry<String, String> h : rule.getValue().entrySet()) {
                    if (!headers.containsKey(h.getKey())) {
                        putHeader(headers, h.getKey(), h.getValue());
                    }
                }
                break;   // 命中一条规则即止，规则表按域名互斥设计
            }
        }
        for (Map.Entry<String, String> entry : headers.entrySet()) builder.setHeader(entry.getKey(), entry.getValue());
        return new GlideUrl(url, builder.build());
    }

    private static boolean isInvalidImageUrl(String url) {
        if (TextUtils.isEmpty(url)) return true;
        url = url.trim();
        if (TextUtils.isEmpty(url)) return true;
        return hasEmptyProxyParam(url, "img");
    }

    private static boolean hasEmptyProxyParam(String url, String key) {
        if (!url.startsWith("proxy://") && !url.contains("/proxy?")) return false;
        int queryIndex = url.indexOf('?');
        String query = queryIndex >= 0 ? url.substring(queryIndex + 1) : url.substring("proxy://".length());
        String[] pairs = query.split("&");
        for (String pair : pairs) {
            int eqIndex = pair.indexOf('=');
            if (eqIndex < 0) continue;
            if (key.equals(pair.substring(0, eqIndex)) && TextUtils.isEmpty(pair.substring(eqIndex + 1))) {
                return true;
            }
        }
        return false;
    }

    // 判断 URL 的 host 是否等于指定域名后缀，或为其子域（忽略大小写）。
    // 例：host=img2.doubanio.com、domainSuffix=doubanio.com 时返回 true。
    // 不使用 java.net.URL 解析，避免畸形 URL 抛异常中断图片加载。
    private static boolean hostMatches(String url, String domainSuffix) {
        try {
            // 去掉协议前缀（http:// 或 https://），其余协议（proxy:// 等）按原样处理
            String noScheme = (url.startsWith("http://") || url.startsWith("https://"))
                    ? url.substring(url.indexOf("://") + 3) : url;
            // 截取第一个 '/' 之前的部分作为 host（可能含端口）
            String host = noScheme.split("/")[0].toLowerCase();
            int colon = host.indexOf(':');          // 去掉端口
            if (colon >= 0) host = host.substring(0, colon);
            // 完全相等，或以 ".域名后缀" 结尾（子域）才算命中
            return host.equals(domainSuffix) || host.endsWith("." + domainSuffix);
        } catch (Throwable t) {
            return false;                           // 任何解析异常都视为不匹配，不影响加载
        }
    }

    private static void putHeader(Map<String, String> headers, String key, String value) {
        if (TextUtils.isEmpty(key) || TextUtils.isEmpty(value)) return;
        headers.put(key, value.trim());
    }

    private static RequestListener<Bitmap> getListener(final ImageView view, final ImageView.ScaleType scaleType, final Drawable fallback, final String originalUrl) {
        return new RequestListener<Bitmap>() {
            @Override
            public boolean onLoadFailed(@Nullable GlideException e, Object model, Target<Bitmap> target, boolean isFirstResource) {
                // 只记录原始 URL 与 Glide 解析后的地址，不在客户端伪造 CDN 回退。
                // 追加实际发送的请求头，便于诊断 Referer 自动注入是否生效。
                String modelHeaders = (model instanceof GlideUrl)
                        ? String.valueOf(((GlideUrl) model).getHeaders()) : "n/a";
                LOG.i("echo-img-fail original=" + originalUrl
                        + " model=" + String.valueOf(model)
                        + " headers=" + modelHeaders
                        + " err=" + (e == null ? "null" : e.toString()));
                view.setScaleType(scaleType);
                view.setImageDrawable(fallback);
                return true;
            }

            @Override
            public boolean onResourceReady(Bitmap resource, Object model, Target<Bitmap> target, DataSource dataSource, boolean isFirstResource) {
                view.setScaleType(scaleType);
                return false;
            }
        };
    }
}
