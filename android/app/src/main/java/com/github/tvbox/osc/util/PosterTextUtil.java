package com.github.tvbox.osc.util;

import android.text.TextUtils;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Poster copy rules shared by the home, grid, search and history cards.
 *
 * <p>Source data uses the same note field for scores, episode progress and
 * recommendation copy. Keeping the parsing here prevents a score of zero or
 * a long recommendation from becoming a poster badge by accident.</p>
 */
public final class PosterTextUtil {
    private static final Pattern SCORE_NOTE = Pattern.compile(
            "^\\s*([+-]?\\d+(?:\\.\\d+)?)\\s*(?:分\\s*)?(?:豆瓣|评分|$)",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern PROGRESS_NOTE = Pattern.compile(
            "^\\s*(?:更新至|更新第|第\\d+集|全\\d+集|共\\d+集|上次看到|已看到|看到).{0,18}\\s*$");

    private PosterTextUtil() {
    }

    /** Returns a compact positive score, or an empty string for zero/missing scores. */
    public static String positiveScore(String note) {
        Matcher matcher = scoreMatcher(note);
        if (matcher == null) return "";
        try {
            double value = Double.parseDouble(matcher.group(1));
            if (value <= 0) return "";
            return String.format(Locale.US, "%s", matcher.group(1));
        } catch (NumberFormatException ignored) {
            return "";
        }
    }

    /** Returns a single useful badge for a regular content grid card. */
    public static String gridBadge(String note, int year) {
        String score = positiveScore(note);
        if (!TextUtils.isEmpty(score)) return score;
        String progress = shortProgress(note);
        if (!TextUtils.isEmpty(progress)) return progress;
        return year > 0 ? String.valueOf(year) : "";
    }

    /** Returns only short episode/progress copy; recommendation paragraphs are ignored. */
    public static String shortProgress(String note) {
        if (TextUtils.isEmpty(note) || scoreMatcher(note) != null) return "";
        String value = note.trim();
        return PROGRESS_NOTE.matcher(value).matches() ? value : "";
    }

    private static Matcher scoreMatcher(String note) {
        if (TextUtils.isEmpty(note)) return null;
        Matcher matcher = SCORE_NOTE.matcher(note.trim());
        return matcher.find() ? matcher : null;
    }
}
