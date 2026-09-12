package com.github.catvod.spider;

import android.content.Context;
import android.text.TextUtils;

import com.github.catvod.crawler.Spider;
import com.github.catvod.net.OkHttp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * 配置中心（TVBoxOSC 标准行为）：
 * - ext 为配置列表数据源（文本，每行一个配置地址）
 * - homeContent 返回配置列表；detailContent 返回配置原始内容预览
 * 内置实现（App 内置类优先于 jar 同名类），不依赖任何外部 jar 环境。
 */
public class Config extends Spider {

    private String ext;

    @Override
    public void init(Context context, String extend) {
        super.init(context, extend);
        ext = extend == null ? "" : extend.trim();
    }

    @Override
    public String homeContent(boolean filter) {
        try {
            JSONObject result = new JSONObject();
            JSONArray list = new JSONArray();
            if (!TextUtils.isEmpty(ext)) {
                String data = OkHttp.string(ext);
                if (data != null) {
                    for (String line : data.split("\\r?\\n")) {
                        String s = line.trim();
                        if (s.isEmpty() || s.startsWith("#")) continue;
                        // 支持 名称,URL / 名称|URL 格式；无分隔符则整行当 URL
                        String name = s;
                        String url = s;
                        int sep = s.indexOf(',');
                        if (sep < 0) sep = s.indexOf('|');
                        if (sep > 0) {
                            name = s.substring(0, sep).trim();
                            url = s.substring(sep + 1).trim();
                        }
                        if (url.isEmpty()) continue;
                        JSONObject item = new JSONObject();
                        item.put("vod_id", url);
                        item.put("vod_name", name);
                        item.put("vod_pic", "");
                        item.put("vod_remarks", "");
                        list.put(item);
                    }
                }
            }
            result.put("list", list);
            return result.toString();
        } catch (Throwable t) {
            t.printStackTrace();
            return "";
        }
    }

    @Override
    public String categoryContent(String tid, String pg, boolean filter, java.util.HashMap<String, String> extend) {
        return homeContent(filter);
    }

    @Override
    public String detailContent(List<String> ids) {
        String id = ids == null || ids.isEmpty() ? "" : ids.get(0);
        try {
            JSONObject result = new JSONObject();
            JSONObject item = new JSONObject();
            item.put("vod_id", id);
            item.put("vod_name", id);
            item.put("vod_pic", "");
            item.put("vod_remarks", "");
            result.put("list", new JSONArray().put(item));
            return result.toString();
        } catch (Throwable t) {
            t.printStackTrace();
            return "";
        }
    }

    @Override
    public String searchContent(String key, boolean quick) {
        return "";
    }

    @Override
    public String playerContent(String flag, String id, List<String> vipFlags) {
        return "";
    }
}
