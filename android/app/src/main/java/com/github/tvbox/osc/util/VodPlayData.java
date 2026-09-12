package com.github.tvbox.osc.util;

import android.text.TextUtils;

import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.bean.VodInfo;

import java.util.Collections;
import java.util.List;

/**
 * 详情 / 快速搜索 / 播放共用的数据校验。
 * 无效来源、错误占位文案、空线路都不能进入详情页或播放器。
 */
public final class VodPlayData {
    private static final String[] PLACEHOLDER_PHRASES = {
            "搜索失败",
            "无匹配资源",
            "API异常",
            "解析失败",
            "点我播放",
            "TG频道分享"
    };

    private VodPlayData() {
    }

    public static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    /**
     * 名称、备注、类型、ID、集名里出现的错误占位。
     * 空字符串本身不算占位，由调用方决定空值是否合法。
     */
    public static boolean isPlaceholderText(String text) {
        if (isBlank(text)) {
            return false;
        }
        String trimmed = text.trim();
        if ("error".equalsIgnoreCase(trimmed) || "null".equalsIgnoreCase(trimmed)) {
            return true;
        }
        for (String phrase : PLACEHOLDER_PHRASES) {
            if (trimmed.contains(phrase)) {
                return true;
            }
        }
        return false;
    }

    public static boolean isValidId(String id) {
        if (isBlank(id)) {
            return false;
        }
        String trimmed = id.trim();
        if ("error".equalsIgnoreCase(trimmed) || "null".equalsIgnoreCase(trimmed)) {
            return false;
        }
        if (trimmed.startsWith("msearch:")) {
            return false;
        }
        return !isPlaceholderText(trimmed);
    }

    public static boolean isValidPlayUrl(String url) {
        if (isBlank(url) || isPlaceholderText(url)) {
            return false;
        }
        String trimmed = url.trim();
        return !"error".equalsIgnoreCase(trimmed) && !"null".equalsIgnoreCase(trimmed);
    }

    public static boolean isValidEpisode(String name, String url) {
        if (isBlank(name) || isPlaceholderText(name)) {
            return false;
        }
        return isValidPlayUrl(url);
    }

    /**
     * 快速搜索结果能否被选中并进入详情。
     */
    public static boolean isValidSearchVideo(Movie.Video video) {
        if (video == null) {
            return false;
        }
        if (!isValidId(video.id) || isBlank(video.sourceKey)) {
            return false;
        }
        if (ApiConfig.get().getSource(video.sourceKey) == null) {
            return false;
        }
        if (isBlank(video.name) || isPlaceholderText(video.name)) {
            return false;
        }
        if (isPlaceholderText(video.note) || isPlaceholderText(video.type)) {
            return false;
        }
        return true;
    }

    public static boolean hasValidPlayData(VodInfo vodInfo) {
        if (vodInfo == null || vodInfo.seriesMap == null || vodInfo.seriesMap.isEmpty()) {
            return false;
        }
        if (vodInfo.seriesFlags == null || vodInfo.seriesFlags.isEmpty()) {
            return false;
        }
        for (List<VodInfo.VodSeries> seriesList : vodInfo.seriesMap.values()) {
            if (hasValidSeries(seriesList)) {
                return true;
            }
        }
        return false;
    }

    /**
     * 单条线路是否真的可播。名称/地址含「解析失败」「error」等占位时不算可用。
     */
    public static boolean hasValidSeries(List<VodInfo.VodSeries> seriesList) {
        if (seriesList == null || seriesList.isEmpty()) {
            return false;
        }
        for (VodInfo.VodSeries series : seriesList) {
            if (series == null) {
                continue;
            }
            if (isPlaceholderText(series.name)) {
                continue;
            }
            if (isValidPlayUrl(series.url)) {
                return true;
            }
        }
        return false;
    }

    public static List<VodInfo.VodSeries> getSeriesList(VodInfo vodInfo) {
        if (vodInfo == null) {
            return Collections.emptyList();
        }
        return getSeriesList(vodInfo, vodInfo.playFlag);
    }

    public static List<VodInfo.VodSeries> getSeriesList(VodInfo vodInfo, String flag) {
        if (vodInfo == null || vodInfo.seriesMap == null || isBlank(flag)) {
            return Collections.emptyList();
        }
        List<VodInfo.VodSeries> seriesList = vodInfo.seriesMap.get(flag);
        return seriesList == null ? Collections.emptyList() : seriesList;
    }

    public static VodInfo.VodSeries getSeries(VodInfo vodInfo, String flag, int index) {
        if (vodInfo == null || vodInfo.seriesMap == null || isBlank(flag)) {
            return null;
        }
        List<VodInfo.VodSeries> seriesList = vodInfo.seriesMap.get(flag);
        if (seriesList == null || seriesList.isEmpty()) {
            return null;
        }
        int safeIndex = Math.max(0, Math.min(index, seriesList.size() - 1));
        return seriesList.get(safeIndex);
    }

    public static String getSourceName(String sourceKey) {
        try {
            SourceBean source = ApiConfig.get().getSource(sourceKey);
            if (source != null && !TextUtils.isEmpty(source.getName())) {
                return source.getName();
            }
        } catch (Throwable ignored) {
        }
        return sourceKey == null ? "" : sourceKey;
    }

    public static String sanitizeUrl(String url) {
        if (isBlank(url)) {
            return "";
        }
        String trimmed = url.trim();
        int query = trimmed.indexOf('?');
        if (query > 0 && trimmed.length() > query + 24) {
            return trimmed.substring(0, query + 24) + "...";
        }
        if (trimmed.length() > 160) {
            return trimmed.substring(0, 160) + "...";
        }
        return trimmed;
    }
}
