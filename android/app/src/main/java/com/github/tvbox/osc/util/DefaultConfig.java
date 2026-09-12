package com.github.tvbox.osc.util;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.text.TextUtils;

import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.server.ControlManager;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;

/**
 * @author pj567
 * @date :2020/12/21
 * @description:
 */
public class DefaultConfig {

    /**
     * 分类名归一化：消除接口与订阅配置之间的常见命名差异（动画片/动漫、纪录片/记录片、
     * 电视剧/连续剧/剧集、电影/电影片、综艺/综艺片、短剧/微短剧），避免精确匹配丢分类。
     */
    private static String normalizeCateName(String name) {
        if (name == null) return "";
        String n = name.trim();
        switch (n) {
            case "动画片":
            case "动漫片":
            case "动漫":
                return "动漫";
            case "记录片":
            case "纪录片":
                return "纪录片";
            case "连续剧":
            case "电视剧集":
            case "剧集":
            case "电视剧":
                return "电视剧";
            case "综艺片":
            case "综艺":
                return "综艺";
            case "电影片":
            case "电影":
                return "电影";
            case "微短剧":
            case "爽文短剧":
            case "短剧":
                return "短剧";
            case "家庭篇":
            case "家庭片":
                return "家庭片";
            // 少儿类上游命名差异：订阅配置写「少儿」，接口可能返回 儿童/亲子/幼儿/儿童儿歌 等
            case "儿童":
            case "亲子":
            case "幼儿":
            case "儿童儿歌":
            case "少儿频道":
            case "少儿教育":
                return "少儿";
            case "记录":
                return "纪录片";
            default:
                return n;
        }
    }

    // ---- 两级分类：顶级分类 + 子分类（类型/地区）筛选 ----

    /** 电影类型词（无 type_pid 源的子分类识别） */
    private static final String[] TYPE_WORDS = {
            "动作片", "喜剧片", "爱情片", "科幻片", "恐怖片", "剧情片", "战争片", "惊悚片",
            "家庭片", "家庭篇", "古装片", "历史片", "悬疑片", "犯罪片", "灾难片",
            "动画片", "短片", "西部片", "武侠片", "奇幻片", "冒险片", "歌舞片", "传记片",
            "运动片", "音乐片", "伦理片", "未分类"
    };

    /** 无 type_pid 源的顶级分类名（其余不以类型/地区词结尾的也视为顶级） */
    private static final String[] TOP_LEVEL_WORDS = {
            "电影", "电视剧", "连续剧", "剧集", "综艺", "动漫", "短剧", "爽文短剧", "漫剧",
            "体育", "体育赛事", "世界杯", "演唱会", "预告片", "影视解说", "资讯", "新闻资讯",
            "头条", "公告", "少儿", "亲子", "科教", "科普学习", "直播", "纪录片", "4k影视片", "4k影视剧", "4k动漫"
    };

    private static boolean isTypeWord(String name) {
        for (String w : TYPE_WORDS) {
            if (name.equals(w)) return true;
        }
        return false;
    }

    private static boolean isTopLevelWord(String name) {
        for (String w : TOP_LEVEL_WORDS) {
            if (name.equals(w)) return true;
        }
        return false;
    }

    /**
     * 子分类识别（无 type_pid 时）：类型词、地区剧（…剧）、综艺地区（…综艺）、动漫地区（…动漫）。
     * 电视剧/连续剧/短剧/漫剧 等顶级词虽以“剧”结尾但不视为子分类。
     */
    private static boolean isSubCateName(String name) {
        if (isTopLevelWord(name)) return false;
        if (isTypeWord(name)) return true;
        if (name.endsWith("剧") || name.endsWith("综艺") || name.endsWith("动漫")) return true;
        return false;
    }

    /** 综合判定：有 typePid 时以 typePid 为准（>0 即子分类），否则按名称规则 */
    private static boolean isSubCate(MovieSort.SortData sd) {
        if (sd.typePid != null && !sd.typePid.isEmpty() && !"0".equals(sd.typePid)) {
            return true;
        }
        return isSubCateName(sd.name);
    }

    /**
     * 构建两级分类：顶级分类进入分类栏；子分类（type_pid 指向顶级或规则识别）
     * 作为顶级分类的“类型/地区”筛选。筛选值 = 子分类 id（请求 t 直接使用）。
     * 顶级分类保留接口原 type_id（请求 t 用原 id），不再置 "0"——置 "0" 会让
     * 顶级分类请求 t=0 返回源站全局混合推荐，导致分类内容串数据。
     */
    private static void buildSortHierarchy(List<MovieSort.SortData> list) {
        if (list == null || list.isEmpty()) return;
        // 1. 收集子分类：typePid > 0 且存在对应顶级；无 typePid 的源按名称规则识别
        java.util.Map<String, java.util.List<MovieSort.SortData>> children = new java.util.HashMap<>();
        for (MovieSort.SortData sd : list) {
            String pid = sd.typePid;
            String parent = null;
            if (pid != null && !pid.isEmpty() && !"0".equals(pid)) {
                // 找 pid 对应的顶级（按 id 匹配）
                for (MovieSort.SortData top : list) {
                    if (top.id != null && top.id.equals(pid)
                            && (top.typePid == null || "0".equals(top.typePid) || top.typePid.isEmpty())) {
                        parent = top.name;
                        break;
                    }
                }
            } else if (pid == null || pid.isEmpty()) {
                // 无 typePid：按名称规则
                if (isSubCateName(sd.name)) {
                    parent = guessParentCate(sd.name, list);
                }
            }
            if (parent != null) {
                children.computeIfAbsent(parent, k -> new java.util.ArrayList<>()).add(sd);
            }
        }
        // 2. 顶级分类挂筛选（类型/地区）
        for (MovieSort.SortData top : list) {
            if (isSubCate(top)) continue; // 子分类不进入分类栏
            String name = top.name;
            java.util.List<MovieSort.SortData> subs = children.get(name);
            if (subs != null && !subs.isEmpty()) {
                if (top.filters == null) top.filters = new ArrayList<>();
                MovieSort.SortFilter typeFilter = new MovieSort.SortFilter();
                typeFilter.key = "type";
                typeFilter.name = filterNameFor(subs);
                typeFilter.values = new java.util.LinkedHashMap<>();
                // “全部”= 不选子分类，回退到顶级聚合列表（值为空串，选中后 filterSelect 为空）
                typeFilter.values.put("全部", "");
                for (MovieSort.SortData sub : subs) {
                    typeFilter.values.put(sub.name, sub.id);
                }
                top.filters.add(typeFilter);
            }
        }
    }

    /** 筛选名：子分类都是地区剧/综艺/动漫 → “地区”，否则“类型” */
    private static String filterNameFor(java.util.List<MovieSort.SortData> subs) {
        boolean allRegion = true;
        for (MovieSort.SortData s : subs) {
            String n = s.name;
            if (!(n.endsWith("剧") || n.endsWith("综艺") || n.endsWith("动漫"))) {
                allRegion = false;
                break;
            }
        }
        return allRegion ? "地区" : "类型";
    }

    /** 无 type_pid 源：子分类归属的顶级（剧→电视剧类；综艺→综艺；动漫→动漫；类型词→电影） */
    private static String guessParentCate(String subName, List<MovieSort.SortData> list) {
        for (MovieSort.SortData top : list) {
            if (isTopLevelWord(top.name)) {
                if (top.name.equals("电视剧") || top.name.equals("连续剧") || top.name.equals("剧集")) {
                    if (subName.endsWith("剧")) return top.name;
                } else if (top.name.equals("综艺")) {
                    if (subName.endsWith("综艺")) return top.name;
                } else if (top.name.equals("动漫")) {
                    if (subName.endsWith("动漫")) return top.name;
                } else if (top.name.equals("电影")) {
                    if (isTypeWord(subName)) return top.name;
                }
            }
        }
        // 回退：挂到第一个电影类顶级（电影/电影片）
        for (MovieSort.SortData top : list) {
            if (top.name.equals("电影")) return top.name;
        }
        return null;
    }

    public static List<MovieSort.SortData> adjustSort(String sourceKey, List<MovieSort.SortData> list, boolean withMy) {
        List<MovieSort.SortData> data = new ArrayList<>();
        if (sourceKey != null && list != null) {
            // 两级分类构建：子分类挂到顶级分类的筛选（类型/地区），有子分类的顶级默认 id=0（全部=主页内容）
            buildSortHierarchy(list);
            SourceBean sb = ApiConfig.get().getSource(sourceKey);
            if (sb == null || sb.getCategories() == null) {
                for (MovieSort.SortData sortData : list) {
                    if (isSubCate(sortData)) continue; // 子分类不进入分类栏
                    if (sortData.filters == null)
                        sortData.filters = new ArrayList<>();
                    data.add(sortData);
                }
                if (withMy)
                    data.add(0, new MovieSort.SortData("my0", "主页"));
                Collections.sort(data);
                return data;
            }
            ArrayList<String> categories = sb.getCategories();
            if (!categories.isEmpty()) {
                List<MovieSort.SortData> matched = new ArrayList<>();
                for (String cate : categories) {
                    String normalizedCate = normalizeCateName(cate);
                    for (MovieSort.SortData sortData : list) {
                        if (isSubCate(sortData)) continue;
                        if (normalizeCateName(sortData.name).equals(normalizedCate)) {
                            if (sortData.filters == null)
                                sortData.filters = new ArrayList<>();
                            matched.add(sortData);
                        }
                    }
                }
                if (matched.size() >= 3) {
                    // 正常：按配置顺序显示匹配到的顶级分类
                    data.addAll(matched);
                } else {
                    // 兜底：配置与接口差异过大（匹配不足 3 个）时显示接口全部顶级分类，避免分类栏空白
                    for (MovieSort.SortData sortData : list) {
                        if (isSubCate(sortData)) continue;
                        if (sortData.filters == null)
                            sortData.filters = new ArrayList<>();
                        data.add(sortData);
                    }
                }
            } else {
                for (MovieSort.SortData sortData : list) {
                    if (isSubCate(sortData)) continue;
                    if (sortData.filters == null)
                        sortData.filters = new ArrayList<>();
                    data.add(sortData);
                }
            }
        }
        if (withMy)
            data.add(0, new MovieSort.SortData("my0", "主页"));
        Collections.sort(data);
        return data;
    }

    public static int getAppVersionCode(Context mContext) {
        //包管理操作管理类
        PackageManager pm = mContext.getPackageManager();
        try {
            PackageInfo packageInfo = pm.getPackageInfo(mContext.getPackageName(), 0);
            return packageInfo.versionCode;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
        }
        return -1;
    }

    public static String getAppVersionName(Context mContext) {
        //包管理操作管理类
        PackageManager pm = mContext.getPackageManager();
        try {
            PackageInfo packageInfo = pm.getPackageInfo(mContext.getPackageName(), 0);
            return packageInfo.versionName;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
        }
        return "";
    }

    /**
     * 后缀
     *
     * @param name
     * @return
     */
    public static String getFileSuffix(String name) {
        if (TextUtils.isEmpty(name)) {
            return "";
        }
        int endP = name.lastIndexOf(".");
        return endP > -1 ? name.substring(endP) : "";
    }

    /**
     * 获取文件的前缀
     *
     * @param fileName
     * @return
     */
    public static String getFilePrefixName(String fileName) {
        if (TextUtils.isEmpty(fileName)) {
            return "";
        }
        int start = fileName.lastIndexOf(".");
        return start > -1 ? fileName.substring(0, start) : fileName;
    }

    private static final Pattern snifferMatch = Pattern.compile(
            "http((?!http).){12,}?\\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a)\\?.*|" +
            "http((?!http).){12,}\\.(m3u8|mp4|flv|avi|mkv|rm|wmv|mpg|m4a)|" +
            "http((?!http).)*?video/tos*|" +
            "http((?!http).){20,}?/m3u8\\?pt=m3u8.*|" +
            "http((?!http).)*?default\\.ixigua\\.com/.*|" +
            "http((?!http).)*?dycdn-tos\\.pstatp[^\\?]*|" +
            "http.*?/player/m3u8play\\.php\\?url=.*|" +
            "http.*?/player/.*?[pP]lay\\.php\\?url=.*|" +
            "http.*?/playlist/m3u8/\\?vid=.*|" +
            "http.*?\\.php\\?type=m3u8&.*|" +
            "http.*?/download.aspx\\?.*|" +
            "http.*?/api/up_api.php\\?.*|" +
            "https.*?\\.66yk\\.cn.*|" +
            "http((?!http).)*?netease\\.com/file/.*"
    );
    public static boolean isVideoFormat(String url) {
        Uri uri = Uri.parse(url);
        String path = uri.getPath();
        if (TextUtils.isEmpty(path)) {
            return false;
        }
        if (snifferMatch.matcher(url).find()) return true;
        return false;
    }


    public static String safeJsonString(JsonObject obj, String key, String defaultVal) {
        try {
            if (obj.has(key)){
                return obj.get(key).isJsonObject() || obj.get(key).isJsonArray()?obj.get(key).toString().trim():obj.getAsJsonPrimitive(key).getAsString().trim();
            }
            else
                return defaultVal;
        } catch (Throwable th) {
        }
        return defaultVal;
    }

    public static int safeJsonInt(JsonObject obj, String key, int defaultVal) {
        try {
            if (obj.has(key))
                return obj.getAsJsonPrimitive(key).getAsInt();
            else
                return defaultVal;
        } catch (Throwable th) {
        }
        return defaultVal;
    }

    public static ArrayList<String> safeJsonStringList(JsonObject obj, String key) {
        ArrayList<String> result = new ArrayList<>();
        try {
            if (obj.has(key)) {
                if (obj.get(key).isJsonObject()) {
                    result.add(obj.get(key).getAsString());
                } else {
                    for (JsonElement opt : obj.getAsJsonArray(key)) {
                        result.add(opt.getAsString());
                    }
                }
            }
        } catch (Throwable th) {
        }
        return result;
    }

    public static String checkReplaceProxy(String urlOri) {
        if (urlOri.startsWith("proxy://"))
            return urlOri.replace("proxy://", ControlManager.get().getAddress(true) + "proxy?");
        return urlOri;
    }

    private static final List<String> NO_AD_KEYWORDS = Arrays.asList(
            "tx", "youku", "qq","qiyi", "letv", "leshi","sohu", "mgtv", "bilibili", "imgo","优酷", "芒果", "腾讯", "奇艺"
    );

    public static boolean noAd(String flag) {
        if (flag == null || flag.isEmpty()) return false;
        for (String keyword : NO_AD_KEYWORDS) {
            if (flag.equals(keyword) || flag.contains(keyword)) {
                return true;
            }
        }
        return false;
    }
}
