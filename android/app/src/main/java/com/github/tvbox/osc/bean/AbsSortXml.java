package com.github.tvbox.osc.bean;

import com.thoughtworks.xstream.annotations.XStreamAlias;

import java.io.Serializable;
import java.util.List;

/**
 * @author pj567
 * @date :2020/12/18
 * @description:
 */
@XStreamAlias("rss")
public class AbsSortXml implements Serializable {
    public String sourceKey;
    /** 首页分类请求序号，用来丢弃过期回调。 */
    public int requestSeq;
    /** true 表示这次分类请求失败，而不是空分类。 */
    public boolean failed;

    @XStreamAlias("class")
    public MovieSort classes;

    @XStreamAlias("list")
    public Movie list;

    public List<Movie.Video> videoList;
}