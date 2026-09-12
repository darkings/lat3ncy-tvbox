package com.github.tvbox.osc.bean;

import static com.github.tvbox.osc.util.RegexUtils.getPattern;

import com.github.tvbox.osc.util.VodPlayData;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * @author pj567
 * @date :2020/12/22
 * @description:
 */
public class VodInfo implements Serializable {
    public String last;//时间
    //内容id
    public String id;
    //父级id
    public int tid;
    //影片名称 <![CDATA[老爸当家]]>
    public String name;
    //类型名称
    public String type;
    //视频分类zuidam3u8,zuidall
    public String dt;
    //图片
    public String pic;
    //语言
    public String lang;
    //地区
    public String area;
    //年份
    public int year;
    public String state;
    //描述集数或者影片信息<![CDATA[共40集]]>
    public String note;
    //演员<![CDATA[张国立,蒋欣,高鑫,曹艳艳,王维维,韩丹彤,孟秀,王新]]>
    public String actor;
    //导演<![CDATA[陈国星]]>
    public String director;
    public ArrayList<VodSeriesFlag> seriesFlags;
    public LinkedHashMap<String, List<VodSeries>> seriesMap;
    public String des;// <![CDATA[权来]
    public String playFlag = null;
    public int playIndex = 0;
    public String playNote = "";
    public String sourceKey;
    public String playerCfg = "";
    public boolean reverseSort = false;

    public void setVideo(Movie.Video video) {
        last = video.last;
        id = video.id;
        tid = video.tid;
        name = video.name;
        type = video.type;
        // dt = video.dt;
        pic = video.pic;
        lang = video.lang;
        area = video.area;
        year = video.year;
        state = video.state;
        note = video.note;
        actor = video.actor;
        director = video.director;
        des = video.des;
        seriesFlags = new ArrayList<>();
        seriesMap = new LinkedHashMap<>();
        if (video.urlBean != null && video.urlBean.infoList != null && !video.urlBean.infoList.isEmpty()) {
            LinkedHashMap<String, List<VodSeries>> tempSeriesMap = new LinkedHashMap<>();
            for (Movie.Video.UrlBean.UrlInfo urlInfo : video.urlBean.infoList) {
                if (urlInfo == null || VodPlayData.isBlank(urlInfo.flag) || VodPlayData.isPlaceholderText(urlInfo.flag)) {
                    continue;
                }
                if (urlInfo.beanList == null || urlInfo.beanList.isEmpty()) {
                    continue;
                }
                List<VodSeries> seriesList = new ArrayList<>();
                for (Movie.Video.UrlBean.UrlInfo.InfoBean infoBean : urlInfo.beanList) {
                    if (infoBean == null || !VodPlayData.isValidEpisode(infoBean.name, infoBean.url)) {
                        continue;
                    }
                    seriesList.add(new VodSeries(infoBean.name, infoBean.url));
                }
                if (seriesList.isEmpty()) {
                    continue;
                }
                tempSeriesMap.put(urlInfo.flag, seriesList);
                seriesFlags.add(new VodSeriesFlag(urlInfo.flag));
            }
            for (VodSeriesFlag flag : seriesFlags) {
                List<VodSeries> list = tempSeriesMap.get(flag.name);
                if (list == null || list.isEmpty()) {
                    continue;
                }
                if (seriesFlags.size() <= 5 && isReverse(list)) {
                    Collections.reverse(list);
                }
                seriesMap.put(flag.name, list);
            }
        }
    }

    private int extractNumber(String name) {
        java.util.regex.Matcher matcher = getPattern("\\d+").matcher(name);
        if (matcher.find()) {
            return Integer.parseInt(matcher.group());
        }
        return 0;
    }
    private boolean isReverse(List<VodInfo.VodSeries> list) {
        int ascCount = 0, descCount = 0;
        // 比较最多前 6 个相邻元素对
        int limit = Math.min(list.size() - 1, 6);
        for (int i = 0; i < limit; i++) {
            int current = extractNumber(list.get(i).name);
            int next = extractNumber(list.get(i + 1).name);
            if (current < next) {
                ascCount++;
                if (ascCount == 2) return false;
            } else if (current > next) {
                descCount++;
                if (descCount == 2) return true;
            }
        }
        return false;
    }

    public void reverse() {
        if (seriesMap == null || seriesMap.isEmpty()) {
            return;
        }
        Set<String> flags = seriesMap.keySet();
        for (String flag : flags) {
            List<VodSeries> list = seriesMap.get(flag);
            if (list != null && !list.isEmpty()) {
                Collections.reverse(list);
            }
        }
    }

    /**
     * 详情快照用的深拷贝，避免换源失败前的点击/倒序污染上一个来源。
     */
    public VodInfo copy() {
        VodInfo copy = new VodInfo();
        copy.last = last;
        copy.id = id;
        copy.tid = tid;
        copy.name = name;
        copy.type = type;
        copy.dt = dt;
        copy.pic = pic;
        copy.lang = lang;
        copy.area = area;
        copy.year = year;
        copy.state = state;
        copy.note = note;
        copy.actor = actor;
        copy.director = director;
        copy.des = des;
        copy.playFlag = playFlag;
        copy.playIndex = playIndex;
        copy.playNote = playNote;
        copy.sourceKey = sourceKey;
        copy.playerCfg = playerCfg;
        copy.reverseSort = reverseSort;
        copy.seriesFlags = new ArrayList<>();
        if (seriesFlags != null) {
            for (VodSeriesFlag flag : seriesFlags) {
                if (flag == null) {
                    continue;
                }
                VodSeriesFlag copiedFlag = new VodSeriesFlag(flag.name);
                copiedFlag.displayName = flag.displayName;
                copiedFlag.statusText = flag.statusText;
                copiedFlag.selected = flag.selected;
                copy.seriesFlags.add(copiedFlag);
            }
        }
        copy.seriesMap = new LinkedHashMap<>();
        if (seriesMap != null) {
            for (Map.Entry<String, List<VodSeries>> entry : seriesMap.entrySet()) {
                List<VodSeries> copiedList = new ArrayList<>();
                if (entry.getValue() != null) {
                    for (VodSeries series : entry.getValue()) {
                        if (series == null) {
                            continue;
                        }
                        VodSeries copiedSeries = new VodSeries(series.name, series.url);
                        copiedSeries.selected = series.selected;
                        copiedSeries.watched = series.watched;
                        copiedList.add(copiedSeries);
                    }
                }
                copy.seriesMap.put(entry.getKey(), copiedList);
            }
        }
        return copy;
    }

    public static class VodSeriesFlag implements Serializable {

        public String name;
        /** 可读线路名称，用于详情页展示；name 保留为源 key 供播放逻辑使用。 */
        public String displayName;
        /** 本次详情请求得到的线路状态摘要。 */
        public String statusText;
        public boolean selected;

        public VodSeriesFlag() {

        }

        public VodSeriesFlag(String name) {
            this.name = name;
        }
    }

    public static class VodSeries implements Serializable {

        public String name;
        public String url;
        public boolean selected;
        /** 当前播放位置之前的集数，用于详情页显示已看状态。 */
        public boolean watched;

        public VodSeries() {
        }

        public VodSeries(String name, String url) {
            this.name = name;
            this.url = url;
        }
    }
}
