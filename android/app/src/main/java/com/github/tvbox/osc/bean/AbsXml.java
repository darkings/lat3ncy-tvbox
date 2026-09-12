package com.github.tvbox.osc.bean;

import com.thoughtworks.xstream.annotations.XStreamAlias;

import java.io.Serializable;

/**
 * @author pj567
 * @date :2020/12/18
 * @description:
 */
@XStreamAlias("rss")
public class AbsXml implements Serializable {
    public String sourceKey;
    public String searchToken;
    /** 列表 / 详情请求序号，用来丢弃过期回调。 */
    public int requestSeq;
    /** true 表示这次请求失败，而不是空结果。 */
    public boolean failed;

    @XStreamAlias("list")
    public Movie movie;

    @XStreamAlias("msg")
    public String msg;
}
