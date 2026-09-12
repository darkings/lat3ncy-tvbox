package com.github.tvbox.osc.bean;

import android.util.Base64;

import com.github.tvbox.osc.util.DefaultConfig;

/**
 * @author pj567
 * @date :2021/3/8
 * @description:
 */
public class ParseBean {

    private String name;
    private String url;
    private String ext;
    private int type;   // 0 普通嗅探 1 json 2 Json扩展 3 聚合

    private boolean isDefault = false;

    /**
     * 该解析器真实出流测试通过的平台（qq/mgtv/qiyi/youku）。
     * 空 = 未测试/不限制（所有平台可用）。
     */
    private java.util.Set<String> platforms;

    public java.util.Set<String> getPlatforms() {
        return platforms;
    }

    public void setPlatforms(java.util.Set<String> platforms) {
        this.platforms = platforms;
    }

    /**
     * 平台 flag 归一化：drpyS 官源的 flag 是站名分组（中文别名，可能带空格/视频后缀，
     * 如 优酷/优 酷/优酷视频/腾讯/腾 讯/腾讯视频/芒果/芒 果 T V/爱奇艺/爱 奇 艺），
     * 统一映射回订阅 platforms 里存的英文 key（qq/mgtv/qiyi/youku）。
     */
    public static String normFlag(String flag) {
        if (flag == null) return "";
        String raw = flag.trim();
        String f = raw.toLowerCase(java.util.Locale.ROOT).replaceAll("\\s+", "");
        if (f.contains("qq") || f.contains("腾讯") || f.contains("tencent")) return "qq";
        if (f.contains("mgtv") || f.contains("芒果") || f.contains("imgo")) return "mgtv";
        if (f.contains("qiyi") || f.contains("iqiyi") || f.contains("奇艺") || f.contains("爱奇艺")) return "qiyi";
        if (f.contains("youku") || f.contains("优酷")) return "youku";
        return raw;
    }

    /** 该解析器是否可用于指定平台（platforms 为空=不限制；flag 先做别名归一化）。 */
    public boolean usableFor(String flag) {
        if (flag == null || flag.isEmpty()) {
            return true;
        }
        if (platforms == null || platforms.isEmpty()) {
            return true;
        }
        return platforms.contains(normFlag(flag));
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getUrl() {
        return DefaultConfig.checkReplaceProxy(url);
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public boolean isDefault() {
        return isDefault;
    }

    public void setDefault(boolean b) {
        isDefault = b;
    }

    public int getType() {
        return type;
    }

    public void setType(int type) {
        this.type = type;
    }

    public String getExt() {
        return ext;
    }

    public void setExt(String ext) {
        this.ext = ext;
    }

    public String mixUrl() {
        if (!ext.isEmpty()) {
            int idx = url.indexOf("?");
            if (idx > 0) {
                return url.substring(0, idx + 1) + "cat_ext=" + Base64.encodeToString(ext.getBytes(), Base64.DEFAULT | Base64.URL_SAFE | Base64.NO_WRAP) + "&" + url.substring(idx + 1);
            }
        }
        return url;
    }
}