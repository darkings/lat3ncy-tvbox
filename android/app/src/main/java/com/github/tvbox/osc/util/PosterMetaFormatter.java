package com.github.tvbox.osc.util;

import android.text.TextUtils;

import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.VodInfo;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Shared copy contract for poster cards.
 *
 * <p>The poster always has one display-name title.  The second line is
 * optional and is selected from short, content-relevant metadata.  Adapters
 * must consume this class instead of concatenating note/year/area locally.</p>
 */
public final class PosterMetaFormatter {
    private static final Pattern SEASON_PATTERN = Pattern.compile(
            "^(?:第\\s*)?([0-9]{1,2})\\s*(?:季|season)$|^S\\s*([0-9]{1,2})$",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern STATUS_PATTERN = Pattern.compile(
            "^(?:完结|已完结|连载中?|更新中?|待更新|即将更新|首播|热播)$");

    private PosterMetaFormatter() {
    }

    /** Immutable result used by every poster-shaped adapter. */
    public static final class Meta {
        public final String title;
        public final String subtitle;
        public final String badge;
        public final String progress;
        public final String contentDescription;

        private Meta(String title, String subtitle, String badge, String progress) {
            this.title = title;
            this.subtitle = subtitle;
            this.badge = badge;
            this.progress = progress;
            this.contentDescription = TextUtils.isEmpty(subtitle)
                    ? title
                    : title + "，" + subtitle;
        }
    }

    public static Meta forVideo(Movie.Video video) {
        if (video == null) return empty();
        return format(video.name, video.type, video.note, video.year, video.area,
                video.state, video.tag);
    }

    public static Meta forVodInfo(VodInfo vodInfo) {
        if (vodInfo == null) return empty();
        return format(vodInfo.name, vodInfo.type, vodInfo.note, vodInfo.year,
                vodInfo.area, vodInfo.state, "");
    }

    public static Meta forName(String name) {
        return format(name, "", "", 0, "", "", "");
    }

    public static Meta empty() {
        return new Meta("未命名内容", "", "", "");
    }

    private static Meta format(String rawName, String rawType, String rawNote,
                               int year, String rawArea, String rawState, String rawTag) {
        String title = displayName(rawName);
        String type = shortField(rawType);
        String area = shortField(rawArea);
        String progress = shortEpisode(rawNote);
        String status = firstNonEmpty(
                progress,
                shortEpisode(rawState),
                shortSeason(rawState),
                shortStatus(rawState),
                shortEpisode(rawTag),
                shortSeason(rawTag),
                shortStatus(rawTag));

        String subtitle;
        if (isDocumentary(type)) {
            subtitle = firstNonEmpty(
                    join(yearText(year), type),
                    join(type, area),
                    yearText(year),
                    type,
                    area);
        } else if (isVariety(type)) {
            subtitle = firstNonEmpty(status, shortSeason(rawNote), join(type, area), type, area);
        } else if (isSeries(type) || !TextUtils.isEmpty(status)) {
            subtitle = firstNonEmpty(status, shortSeason(rawNote), join(type, area), type, area);
        } else if (isMovie(type) || looksLikeMovie(year, area, type)) {
            subtitle = firstNonEmpty(join(yearText(year), area), yearText(year), area);
        } else {
            subtitle = firstNonEmpty(type, area);
        }

        String badge = PosterTextUtil.positiveScore(rawNote);
        return new Meta(title, subtitle, badge, progress);
    }

    private static String displayName(String value) {
        if (TextUtils.isEmpty(value)) return "未命名内容";
        String result = value.replace('　', ' ').trim();
        if (TextUtils.isEmpty(result) || containsUrl(result)) return "未命名内容";
        // Display names are user-facing titles, not compact metadata fields.
        // Do not discard legitimate long movie or series names here.
        return result;
    }

    private static String yearText(int year) {
        return year >= 1900 && year <= 2100 ? String.valueOf(year) : "";
    }

    private static String join(String left, String right) {
        if (TextUtils.isEmpty(left)) return right;
        if (TextUtils.isEmpty(right)) return left;
        return left + " · " + right;
    }

    private static String firstNonEmpty(String... values) {
        for (String value : values) {
            if (!TextUtils.isEmpty(value)) return value;
        }
        return "";
    }

    private static String shortEpisode(String value) {
        if (TextUtils.isEmpty(value)) return "";
        String result = value.trim();
        if (result.length() > 20 || containsUrl(result) || result.indexOf('\n') >= 0) return "";
        String progress = PosterTextUtil.shortProgress(result);
        return TextUtils.isEmpty(progress) ? "" : progress;
    }

    private static String shortSeason(String value) {
        String result = shortField(value);
        if (TextUtils.isEmpty(result)) return "";
        Matcher matcher = SEASON_PATTERN.matcher(result);
        if (!matcher.matches()) return "";
        String number = !TextUtils.isEmpty(matcher.group(1)) ? matcher.group(1) : matcher.group(2);
        return "第 " + number + " 季";
    }

    private static String shortStatus(String value) {
        String result = shortField(value);
        if (STATUS_PATTERN.matcher(result).matches()) return result;
        return "";
    }

    private static String shortField(String value) {
        if (TextUtils.isEmpty(value)) return "";
        String result = value.replace('　', ' ').trim();
        if (TextUtils.isEmpty(result) || result.length() > 14 || containsUrl(result)) return "";
        if (result.contains("简介") || result.contains("推荐") || result.contains("豆瓣")) return "";
        return result;
    }

    private static boolean containsUrl(String value) {
        String lower = value.toLowerCase(Locale.US);
        return lower.contains("http://") || lower.contains("https://")
                || lower.contains("www.") || lower.contains("://");
    }

    private static boolean isMovie(String type) {
        return type.contains("电影") || type.contains("短片")
                || type.toLowerCase(Locale.US).contains("movie")
                || type.toLowerCase(Locale.US).contains("film");
    }

    private static boolean isSeries(String type) {
        return type.contains("剧") || type.contains("动漫") || type.contains("动画")
                || type.contains("番剧") || type.toLowerCase(Locale.US).contains("series")
                || type.toLowerCase(Locale.US).contains("anime");
    }

    private static boolean isVariety(String type) {
        return type.contains("综艺") || type.contains("真人秀") || type.contains("脱口秀")
                || type.contains("节目");
    }

    private static boolean isDocumentary(String type) {
        return type.contains("纪录") || type.contains("专题") || type.contains("纪实")
                || type.toLowerCase(Locale.US).contains("documentary");
    }

    private static boolean looksLikeMovie(int year, String area, String type) {
        return year >= 1900 && !TextUtils.isEmpty(area) && TextUtils.isEmpty(type);
    }
}
