#!/usr/bin/env python3
"""儿童内容聚合：多源去重、统一分类、多线路选择与安全过滤。

对应 PLAN §十一。用户只看到一个「儿童动画」入口，
后台从多个源中汇总、去重、排序，选出最佳播放线路。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_HOME as HERE

# PLAN §十一 统一分类
DEFAULT_CATEGORIES = [
    "热门推荐", "学龄前", "国产动画", "经典动画",
    "少儿英语", "动画电影", "科普启蒙",
]

# 分类关键词映射（标题归类用；列表采集后用它把节目分到 Ponyo 六类）
CATEGORY_KEYWORDS = {
    "学龄前": ["宝宝", "巴士", "贝瓦", "儿歌", "幼儿", "早教", "启蒙",
              "peppa", "佩奇", "汪汪队", "可可", "碰碰狐", "超级飞侠",
              "巧虎", "萌鸡", "布鲁伊", "bluey", "小鹿蓝蓝", "海底小纵队",
              "帮帮龙", "天线宝宝", "花园宝宝", "托马斯", "朵拉", "dora",
              "乐迪", "包警长", "小企鹅", "瑞奇", "宝宝巴士"],
    "国产动画": ["熊出没", "喜羊羊", "猪猪侠", "哪吒", "大头儿子",
               "巴啦啦", "叶罗丽", "奥特曼", "葫芦娃", "葫芦兄弟",
               "黑猫警长", "舒克", "贝塔", "阿凡提", "大闹天宫",
               "赛尔号", "洛克王国", "开心超人", "果宝特攻", "铠甲勇士",
               "咖宝", "宇宙护卫队", "迷你特工队", "大耳朵图图",
               "蓝猫", "虹猫", "阿u", "光头强", "灰太狼", "熊大", "熊二"],
    "经典动画": ["猫和老鼠", "海绵宝宝", "米老鼠", "唐老鸭", "变形金刚",
               "叮当猫", "机器猫", "哆啦", "蓝精灵", "蜡笔小新",
               "樱桃小丸子", "柯南", "宝可梦", "皮卡丘", "龙猫",
               "千与千寻", "小黄人", "史努比", "加菲猫", "小熊维尼",
               "蜘蛛侠", "功夫熊猫", "冰雪奇缘", "疯狂动物城",
               "玩具总动员", "狮子王", "海底总动员", "赛车总动员",
               "超能陆战队", "寻梦环游", "头脑特工队", "芭比", "乐高",
               "灰姑娘", "白雪公主", "小马宝莉", "米奇妙妙屋"],
    "少儿英语": ["英语", "english", "abc", "phonics", "disney",
               "frozen", "英文", "peppa", "nursery", "rhymes",
               "singsing", "little angel", "nunu", "dave and ava",
               "cocomelon", "dream english"],
    "动画电影": ["电影", "movie", "剧场版", "大电影"],
    "科普启蒙": ["科普", "科学", "恐龙", "太空", "海洋", "动物",
              "nature", "百科", "地球", "宇宙"],
}

# 儿童安全屏蔽词（成人/博彩等）
UNSAFE_KEYWORDS = [
    "成人", "伦理", "18禁", "色情", "赌博", "博彩",
    "约炮", "AV", "三级", "情色",
]

# 儿童节目标题白名单：必须命中其中之一才收录。
# 不用「动画/动漫/动物」这种过宽词，避免把修仙国漫、日番全收进来。
CHILDREN_TITLE_MARKERS = [
    # 学龄前 / 早教
    "汪汪队", "小猪佩奇", "超级飞侠", "碰碰狐", "佩奇", "peppa",
    "巧虎", "萌鸡", "布鲁伊", "bluey", "小鹿蓝蓝", "海底小纵队",
    "帮帮龙", "天线宝宝", "花园宝宝", "托马斯", "朵拉", "dora",
    "宝宝巴士", "贝瓦", "儿歌", "早教", "乐迪", "包警长",
    "瑞奇冲冲", "小企鹅", "布鲁伊",
    # 国产动画
    "熊出没", "喜羊羊", "猪猪侠", "哪吒", "大头儿子", "巴啦啦",
    "叶罗丽", "奥特曼", "葫芦娃", "葫芦兄弟", "黑猫警长",
    "舒克", "贝塔", "阿凡提", "大闹天宫", "天书奇谭",
    "赛尔号", "洛克王国", "开心超人", "果宝特攻", "铠甲勇士",
    "咖宝", "宇宙护卫队", "迷你特工队", "大耳朵图图", "蓝猫",
    "虹猫", "光头强", "灰太狼", "熊大", "熊二", "海尔兄弟",
    "阿u", "新大头", "巴拉拉", "精灵梦",
    # 经典 / 电影
    "猫和老鼠", "海绵宝宝", "哆啦", "机器猫", "蓝精灵", "蜡笔小新",
    "樱桃小丸子", "柯南", "宝可梦", "皮卡丘", "pokemon",
    "龙猫", "千与千寻", "小黄人", "史努比", "加菲猫", "小熊维尼",
    "米老鼠", "唐老鸭", "米奇妙妙屋", "变形金刚", "蜘蛛侠",
    "功夫熊猫", "冰雪奇缘", "疯狂动物城", "玩具总动员", "狮子王",
    "海底总动员", "赛车总动员", "超能陆战队", "寻梦环游",
    "头脑特工队", "芭比", "乐高", "灰姑娘", "白雪公主", "小马宝莉",
    "神偷奶爸", "小羊肖恩", "冰川时代", "马达加斯加", "驯龙高手",
    "怪物史莱克", "花木兰", "海洋奇缘", "无敌破坏王", "飞屋环游",
    "爱丽丝", "彼得兔", "比得兔", "小美人鱼", "长发公主",
    "冰雪", "艾莎", "elsa", "frozen", "zootopia", "minions",
    "大白", "baymax", "尼莫", "麦昆",
]

# 明确不是给儿童看的：修仙、动态漫小说、解说、短剧、恐怖等
CHILDREN_BLOCK_MARKERS = [
    "无数据", "解说", "动态漫画", "动态漫", "短剧",
    "修仙", "修真", "逆天", "系统", "穿越", "重生",
    "仙尊", "魔尊", "帝尊", "神王", "仙王", "斗破", "遮天",
    "斗罗", "武魂", "雾山五行", "链锯", "后宫", "恋爱",
    "监禁", "怪谈", "霹雳", "布袋戏", "伦理", "成人",
    "血腥", "杀戮", "尸鬼", "进击的巨人", "咒术", "鬼灭",
]

# 方向1：儿童源晋级最低评分（原要求 hard_pass=1，儿童源播放验证受
# csp_/本地相对路径规则形式限制几乎全失败，实际为 0 个可晋级）
MIN_CHILD_SCORE = 15.0

# 运行时兜底：drpy-node 配置中按名字挑选的儿童/动漫规则（DB 内儿童源
# 大多不可由 HTTP 适配器执行，兜底用本地 drpyS 运行时已有的规则填充缓存）
CHILDREN_RULE_MARKERS = ["少儿", "儿童", "亲子", "幼儿"]
ANIME_RULE_MARKERS = ["动漫", "动画", "卡通"]
MAX_RUNTIME_POOL_RULES = 3
# 每分类、每关键词最多收录条数（搜索兜底用，避免单个词把缓存撑满重复季）
MAX_ITEMS_PER_KEYWORD = 16
# 搜索无标题时，最多回源详情页补标题的次数（动漫豆搜索 vod_name 为空）
MAX_DETAIL_FILL_PER_KEYWORD = 4
# 分类列表分页：每规则、每分类最多翻多少页；连续空页/重复页即停
MAX_LIST_PAGES = 40
# 动漫豆 occident 会出现中间占位页（pg=2 无数据、pg=5 又有片），连续 8 页空才停
MAX_EMPTY_PAGES = 8
# 全量缓存安全上限，避免一次刷新把库撑爆
MAX_CACHE_ITEMS = 2500
# 实测可出 m3u8 的规则优先；平台官源（腾讯/优酷/爱奇艺）详情常返回网页，App 播不了
PREFERRED_RUNTIME_RULES = ["动漫豆[漫]"]
# 只收录已验证能出直链的规则。优酷/爱奇艺/腾讯/樱之空目前返回网页，点播会空线路。
PLAYABLE_RUNTIME_RULES = ["动漫豆[漫]"]
# 动漫豆分类：china/cartoon/occident 有儿童片；japan 几乎全是新番；annotate 是解说
LIST_CLASSES_BY_RULE = {
    "动漫豆[漫]": ["china", "cartoon", "occident"],
}
# 明确少儿分类：分类名本身就是儿童信号，不再强制中文 IP 白名单
# （无尽/索尼「儿童儿歌」大量英文童谣，旧白名单会漏收）
DEDICATED_KIDS_CLASS_MARKERS = (
    "少儿", "儿童", "亲子", "幼儿", "儿歌", "幼教", "童谣", "早教",
)
# 普通动画分类：必须逐条命中儿童标题白名单，不能整类导入
WHITELIST_ANIME_CLASS_MARKERS = (
    "国产动漫", "动画片", "动画电影", "欧美动漫", "国漫",
)
# 分类名含这些词直接跳过（日漫/解说/成人站「卡通动漫」不能当少儿源）
SKIP_CLASS_MARKERS = (
    "日漫", "日本", "解说", "短剧", "综艺", "电视剧", "大陆剧",
    "港台", "真人", "纪录片", "音轨", "演唱", "伦理", "番号",
    "里番", "麻豆",
)
# 英文儿童/儿歌关键词：补白名单，也用于少儿英语归类
ENGLISH_KIDS_MARKERS = [
    "nursery", "rhymes", "rhyme", "phonics", "singsing",
    "little angel", "nunu tv", "dave and ava", "dave_and_ava",
    "cocomelon", "coco melon", "baby shark", "pinkfong",
    "super simple", "kids song", "dream english", "babybus",
    "baby bus", "english singsing",
]
# 明确少儿分类里仍要丢掉的成人/擦边词（玉兔「卡通动漫」就是反例）
DEDICATED_EXTRA_BLOCK = (
    "痴汉", "自慰", "妊娠", "里番", "番号", "r18", "h动漫",
    "警备员", "强奸", "情色", "av",
)
# 网页站不算可播直链
WEB_PLAY_HOSTS = (
    "v.qq.com", "iqiyi.com", "youku.com", "mgtv.com",
    "bilibili.com", "iq.com",
)
# 首批已核实：分类存在、有内容、抽样 m3u8 可读。
# 不收录秒播（少儿/亲子为空）和玉兔（卡通动漫实为成人片）。
MACCMS_KIDS_SOURCES = [
    {
        "name": "无尽资源",
        "fingerprint": "maccms:api.wujinapi.com",
        "api": "https://api.wujinapi.com/api.php/provide/vod/",
        "store_api": "https://api.wujinapi.com/api.php/provide/vod/",
        "ext": "maccms",
        "kind": "maccms",
        "score": 80,
        # 64=儿童儿歌：整类收录（安全过滤）
        "kids_classes": ["64"],
        # 29=国产动漫 33=动画片：只收白名单标题
        "anime_classes": ["29", "33"],
    },
    {
        "name": "索尼资源",
        "fingerprint": "maccms:suoniapi.com",
        "api": "https://suoniapi.com/api.php/provide/vod/",
        "store_api": "https://suoniapi.com/api.php/provide/vod/",
        "ext": "maccms",
        "kind": "maccms",
        "score": 80,
        # 77=儿童儿歌
        "kids_classes": ["77"],
        # 29=国产动漫 39=动画片
        "anime_classes": ["29", "39"],
    },
]
# 兜底池排除：
# - 新闻/IPTV：搜索「宝宝/儿歌」命中新闻片段
# - 腾云驾雾[官]：搜索 vod_id 是 float_vinfo2 API URL，详情解析 video_ids 崩溃
# - 漫画/小说/听书/短剧/直播/cat：不是儿童动画点播
# - 平台官源：playurl 是网页，App 播不了
EXCLUDED_RUNTIME_RULES = {
    "央视大全[官]", "IPTV四川[官]", "腾云驾雾[官]", "豆瓣[官]",
    "优酷[官]", "奇珍异兽[官]", "菜狗[官]", "樱之空动漫",
}
EXCLUDED_RUNTIME_MARKERS = (
    "漫画", "[画]", "[书]", "[听]", "[短]", "直播", "(cat)", "小说", "畅听",
    "[官]",
)
# 每分类使用多个具象关键词（不再命中即停），补齐动画电影等空分类
SEARCH_KEYWORDS_BY_CATEGORY = {
    "学龄前": ["汪汪队", "小猪佩奇", "超级飞侠", "碰碰狐"],
    "国产动画": ["熊出没", "喜羊羊", "猪猪侠", "哪吒"],
    "经典动画": ["猫和老鼠", "海绵宝宝", "哆啦A梦", "蓝精灵"],
    "少儿英语": ["小猪佩奇", "英语动画", "abc"],
    "动画电影": ["熊出没大电影", "哪吒之魔童", "汪汪队大电影"],
    "科普启蒙": ["恐龙", "太空", "海洋"],
}
# 兼容旧名：单关键词映射（测试/外部引用）
SEARCH_KEYWORD_BY_CATEGORY = {
    cat: kws[0] for cat, kws in SEARCH_KEYWORDS_BY_CATEGORY.items()
}


def _normalize_title(title: str) -> str:
    """标准化标题用于去重。"""
    t = title.strip()
    t = re.sub(r"[（(].+?[)）]", "", t)  # 去括号内容
    t = re.sub(r"第?\d+季", "", t)        # 去季数
    t = re.sub(r"\s+", "", t)
    return t.lower()


def classify_children_content(title: str) -> str:
    """将儿童内容分到统一分类。"""
    text = title.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return cat
    # 英文儿歌/早教 IP：标题未命中中文关键词时归少儿英语
    if any(m.lower() in text for m in ENGLISH_KIDS_MARKERS):
        return "少儿英语"
    return "热门推荐"


def is_safe_content(title: str, category: str = "") -> bool:
    """检查是否为安全的儿童内容。"""
    text = (title + " " + category).lower()
    return not any(kw.lower() in text for kw in UNSAFE_KEYWORDS)


def _text_has_marker(text: str, markers) -> bool:
    """标题是否命中屏蔽词。短英文词（av/r18）用边界匹配，避免 Ava 误伤。"""
    low = (text or "").lower()
    for raw in markers:
        marker = str(raw).lower()
        if not marker:
            continue
        if marker.isascii() and len(marker) <= 3:
            if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", low):
                return True
        elif marker in low:
            return True
    return False


def is_children_title(title: str) -> bool:
    """是否为可收录的儿童节目：必须命中白名单，且不能是修仙/解说/短剧等。"""
    t = (title or "").strip()
    if not t or "无数据" in t:
        return False
    low = t.lower()
    if any(b.lower() in low for b in CHILDREN_BLOCK_MARKERS):
        return False
    if not is_safe_content(t):
        return False
    return any(m.lower() in low for m in CHILDREN_TITLE_MARKERS)


def is_dedicated_kids_title(title: str) -> bool:
    """明确儿童/儿歌分类的安全过滤，不强制命中中文 IP 白名单。

    无尽/索尼「儿童儿歌」大量英文童谣，旧白名单会漏收；
    但仍必须丢掉成人/擦边词，不能因为分类名是少儿就整类放行。
    """
    t = (title or "").strip()
    if not t or "无数据" in t:
        return False
    if _text_has_marker(t, CHILDREN_BLOCK_MARKERS):
        return False
    if _text_has_marker(t, UNSAFE_KEYWORDS):
        return False
    if _text_has_marker(t, DEDICATED_EXTRA_BLOCK):
        return False
    return True


def category_type_id(category: str) -> str:
    """把统一分类名映射成 App 使用的 type_id（1..6）。"""
    keys = list(CATEGORY_KEYWORDS.keys())
    if category in keys:
        return str(keys.index(category) + 1)
    return "2"


def type_id_for_title(title: str, source_class: str = "") -> str:
    """按标题和来源分类，给出 Ponyo 六类 type_id。"""
    cat = classify_children_content(title)
    src = (source_class or "").lower()
    # 动漫豆 cartoon 是电影分区：未命中更细分类时归到动画电影
    if cat == "热门推荐":
        if src in ("cartoon", "电影", "剧场", "剧场版") or any(
            k in src for k in ("电影", "剧场")
        ):
            cat = "动画电影"
        elif src in ("occident", "欧美") or "欧美" in src:
            cat = "经典动画"
        elif any(k in src for k in ("儿歌", "童谣", "英语", "english")):
            cat = "少儿英语"
        elif any(k in src for k in ("少儿", "儿童", "亲子", "幼儿", "早教")):
            cat = "学龄前"
        else:
            cat = "国产动画"
    elif src in ("cartoon",) and any(k in title for k in ("电影", "剧场版", "大电影")):
        cat = "动画电影"
    return category_type_id(cat)


def dedupe_children_content(items: list[dict]) -> list[dict]:
    """跨源去重：相同标题+年份+季数+语言的内容只保留最佳线路。

    PLAN §十一第4节：不能只按标题合并，避免同名但不同版本混淆。
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        title = _normalize_title(item.get("title", ""))
        year = item.get("year", "")
        season = item.get("season", "")
        lang = item.get("language", "")
        key = f"{title}|{year}|{season}|{lang}"
        groups.setdefault(key, []).append(item)

    deduped = []
    for key, members in groups.items():
        # 按质量得分排序，保留最佳
        members.sort(key=lambda m: (
            -m.get("quality_score", 0),
            -m.get("play_success_rate", 0),
            -m.get("speed_score", 0),
        ))
        best = members[0].copy()
        # 保留所有来源作为备用线路
        best["routes"] = [
            {"source": m.get("source_fp", ""),
             "play_url": m.get("play_url", ""),
             "quality": m.get("quality_tier", ""),
             "success_rate": m.get("play_success_rate", 0)}
            for m in members
        ]
        deduped.append(best)

    return deduped


def aggregate_children_sources(db_path: str, *,
                               report_path: str | None = None,
                               now: str | None = None) -> dict:
    """从数据库中聚合所有儿童内容。"""
    now = now or datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(str(db_path))

    # 查找所有儿童/少儿分类的源
    rows = con.execute("""
        SELECT n.fingerprint, n.category, r.name, r.site_key,
               ls.state
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE (
            n.category = '儿童'
            OR EXISTS (
                SELECT 1 FROM capability_sampling cs
                WHERE cs.fingerprint=n.fingerprint
                  AND cs.capability='children'
                  AND cs.hit_count>0
            )
        )
        AND n.category NOT IN ('直播', '网盘', '工具')
        AND COALESCE(ls.state, 'candidate') IN ('allow', 'candidate')
    """).fetchall()

    # 统计每个源的评分和质量
    # 儿童源晋级门槛放宽（方向1）：不再要求 hard_pass=1（儿童源播放验证受
    # csp_/本地规则形式限制几乎全失败），改为评分 >= MIN_CHILD_SCORE 且
    # 连通性探测近期有成功即可进入候选池。
    sources = []
    for fp, cat, name, key, state in rows:
        score_row = con.execute(
            "SELECT total_score, hard_pass FROM score_snapshot "
            "WHERE fingerprint=? ORDER BY scored_at DESC LIMIT 1",
            (fp,)).fetchone()
        if not score_row:
            continue
        total_score, hard_pass = score_row
        if total_score < MIN_CHILD_SCORE:
            continue
        quality_row = con.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN quality_tier IN ('hd','fhd','uhd') THEN 1 ELSE 0 END) as hd "
            "FROM media_probe WHERE fingerprint=? AND success=1",
            (fp,)).fetchone()

        sources.append({
            "fingerprint": fp, "name": name, "key": key,
            "state": state or "candidate",
            "score": total_score,
            "hard_pass": hard_pass,
            "hd_count": quality_row[1] if quality_row else 0,
            "total_probes": quality_row[0] if quality_row else 0,
        })

    con.close()

    # 按评分排序（hard_pass 优先同分），分主力和备用
    sources.sort(key=lambda s: (-int(s.get("hard_pass", 0)), -s.get("score", 0)))
    primary = sources[:2] if len(sources) >= 2 else sources
    backup = sources[2:4] if len(sources) > 2 else []
    ready = len(primary) == 2

    import os
    api_url = os.environ.get("CHILDREN_API_URL", "")
    if not api_url:
        raise ValueError("A12: 环境变量 CHILDREN_API_URL 未设置。正式订阅中儿童API必须使用电视可访问的HTTPS域名，不得使用 127.0.0.1 或 localhost。")
    if "127.0.0.1" in api_url or "localhost" in api_url:
        raise ValueError(f"A12: CHILDREN_API_URL 不得包含 127.0.0.1 或 localhost: {api_url}")

    tvbox_site = {
        "key": "Ponyo_Children",
        "name": "儿童动画",
        "type": 1,
        # 必须带 /api.php/provide/vod/ 路径：App 对 type=1 源直接请求该 MacCMS 端点
        "api": api_url.rstrip("/") + "/api.php/provide/vod/",
        "searchable": 1,
        "quickSearch": 1,
        "filterable": 1,
        "ext": "",
        # 静态分类：让 App 预读站点时即可识别为少儿频道，无需等 ac=list 动态下发
        "categories": ["少儿"],
        "category_provenance": "children_aggregate"
    } if ready else None

    summary = {
        "total_children_sources": len(sources),
        "primary": len(primary),
        "backup": len(backup),
        "ready": ready,
        "primary_names": [s["name"] for s in primary],
        "backup_names": [s["name"] for s in backup],
        "categories": DEFAULT_CATEGORIES,
        "tvbox_site": tvbox_site,
    }

    if report_path:
        report = {
            "summary": summary, "generated_at": now,
            "sources": sources,
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # [NEW] Populate children_cache.db with search results from primary sources。
    # 只有配置了 DRPY2_ADAPTER 的执行环境（调度器 cron）才刷新缓存；
    # daily_publish 等无适配器环境跳过，避免清空已有缓存。
    if ready and os.environ.get("DRPY2_ADAPTER"):
        _populate_cache_from_sources(db_path, primary)

    return summary


def _runtime_fallback_rules() -> list[dict]:
    """从 drpy-node 配置中挑选可执行的儿童/动漫规则。

    DB 中的儿童源大多是 csp_/本地相对路径规则，HTTP 适配器无法执行
    （new URL('csp_Xxx') -> Invalid URL / rule must point to /api/:mod），
    兜底改用本地 drpyS 运行时（DRPY2_BASE_URL）已有的规则填充儿童缓存。
    """
    import os
    import urllib.request as urlreq
    from urllib.parse import parse_qs, urlsplit

    base = os.environ.get("DRPY2_BASE_URL", "http://127.0.0.1:5757").rstrip("/")
    config_url = os.environ.get(
        "DRPY2_CONFIG_URL", f"{base}/config/1?pwd=ponyo-local-drpy")
    pwd = ""
    try:
        pwd = (parse_qs(urlsplit(config_url).query).get("pwd") or [""])[0]
    except Exception:
        pwd = ""
    try:
        with urlreq.urlopen(config_url, timeout=10) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"[children] runtime config fetch failed: {e}")
        return []
    sites = doc.get("sites") or []
    by_name: dict[str, dict] = {}
    for s in sites:
        name = str(s.get("name") or "").replace("(DS)", "").replace("(DR2)", "").strip()
        api = str(s.get("api") or "")
        if not name or not api or name in by_name:
            continue
        if name in EXCLUDED_RUNTIME_RULES:
            continue
        if any(m in name for m in EXCLUDED_RUNTIME_MARKERS):
            continue
        by_name[name] = {"name": name, "api": api}

    def _to_rule(name: str, api: str, score: int) -> dict:
        if not api.startswith("http"):
            api = f"{base}/{api.lstrip('/')}"
        rule = api
        if pwd and "?" not in rule:
            rule += f"?pwd={pwd}"
        # store_api：供 children-api 容器解析详情/播放使用（容器内经
        # 容器名访问 drpy-node；宿主 127.0.0.1:5757 在容器内不可达）
        store_base = os.environ.get(
            "CHILDREN_DRPY_BASE", "http://ponyo-drpy-node:5757").rstrip("/")
        path_q = rule[len(base):] if rule.startswith(base) else rule
        store_api = store_base + path_q
        return {
            "fingerprint": f"runtime:{name}",
            "name": name,
            "api": rule,
            "store_api": store_api,
            "ext": "",
            "score": score,
        }

    picked: list[dict] = []
    seen: set[str] = set()

    # 只收已验证能出直链 m3u8 的规则。网页源（优酷/爱奇艺/腾讯/樱之空）
    # 即使节目再多，点播也会变成「当前来源没有可播放线路」。
    for name in PLAYABLE_RUNTIME_RULES:
        site = by_name.get(name)
        if not site or name in seen:
            continue
        seen.add(name)
        picked.append(_to_rule(name, site["api"], score=100))
        if len(picked) >= MAX_RUNTIME_POOL_RULES:
            break
    if picked:
        return picked[:MAX_RUNTIME_POOL_RULES]

    # 没有可播放规则时，才退回儿童名规则（仍排除官源/漫画）
    for markers in (CHILDREN_RULE_MARKERS, ANIME_RULE_MARKERS):
        for name, site in by_name.items():
            if name in seen:
                continue
            if not any(m in name for m in markers):
                continue
            seen.add(name)
            picked.append(_to_rule(name, site["api"], score=10))
            if len(picked) >= MAX_RUNTIME_POOL_RULES:
                return picked
    return picked[:MAX_RUNTIME_POOL_RULES]


def _item_title(item: dict) -> str:
    """从搜索/列表结果抽出标题，去掉 drpy 搜索高亮 <em>。"""
    title = str(item.get("vod_name") or item.get("name") or "").strip()
    return re.sub(r"<[^>]+>", "", title)


def _is_placeholder_item(item: dict, title: str = "") -> bool:
    """drpy 规则用「无数据,防无限请求」占位，防止客户端无限翻页。"""
    name = title or _item_title(item)
    vid = str(item.get("vod_id") or item.get("id") or "")
    return (not name) or ("无数据" in name) or vid in ("no_data", "none")


def _append_video(all_items: list[dict], *, title: str, vod_id: str, pic: str,
                  latest: str, source_fp: str, api: str, ext: str,
                  score: float, source_class: str = "",
                  title_ok=None, kind: str = "", class_name: str = "") -> bool:
    """把一条儿童节目写入采集列表。非儿童/无 ID 返回 False。

    title_ok: 标题过滤器。默认 is_children_title（普通动画分类白名单）；
    明确少儿/儿歌分类传入 is_dedicated_kids_title。
    不把播放 URL 写入条目，点播时再实时解析。
    """
    if not vod_id or not title or _is_placeholder_item({}, title):
        return False
    checker = title_ok or is_children_title
    if not checker(title):
        return False
    type_src = class_name or source_class
    all_items.append({
        "title": title,
        "vod_id": vod_id,
        "pic": pic or "",
        "latest": latest or "",
        "type_id": type_id_for_title(title, type_src),
        "source_fp": source_fp,
        "api": api,
        "ext": ext or "",
        "kind": kind or "",
        "class_name": class_name or "",
        "source_class": type_src,
        "quality_score": score,
        "play_success_rate": 0,
        "speed_score": 0,
    })
    return True


def _http_json(url: str, timeout: int = 20) -> dict | None:
    """GET JSON。失败返回 None，不抛到采集主循环外。"""
    import urllib.request as urlreq
    from ponyo_source_manager.core.common import iri_to_uri
    try:
        # 规则名含中文和 []，必须先转成 ASCII URI，否则 urlopen 会失败
        req = urlreq.Request(iri_to_uri(url), headers={"User-Agent": "ponyo-children"})
        with urlreq.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"[children] http fail {url[:120]}: {str(e)[:100]}")
        return None


def _with_query(api: str, **params) -> str:
    """在规则 API 上追加 ac/t/pg 等查询参数。"""
    from urllib.parse import quote
    url = api
    for key, value in params.items():
        if value is None:
            continue
        sep = "&" if "?" in url else "?"
        url += f"{sep}{key}={quote(str(value))}"
    return url


def _maccms_request_url(endpoint: str, **params) -> str:
    """合并 MacCMS endpoint 已有 query，避免重复追加 ac=。"""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    parts = urlsplit(endpoint or "")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            continue
        query[str(key)] = str(value)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def is_maccms_endpoint(api: str, ext: str = "") -> bool:
    """判断缓存条目是否应走 MacCMS 详情，而不是 drpy。"""
    if str(ext or "").strip().lower() == "maccms":
        return True
    u = (api or "").strip().lower()
    if not u.startswith("http"):
        return False
    return "/api.php/provide/vod" in u or "/provide/vod" in u


def is_playable_media_url(url: str) -> bool:
    """只接受播放器能直接打开的媒体地址，网页站一律丢掉。"""
    u = (url or "").strip().lower()
    if not u.startswith("http"):
        return False
    if any(host in u for host in WEB_PLAY_HOSTS):
        return False
    return any(token in u for token in (".m3u8", ".mp4", ".flv", "/m3u8"))


def maccms_cache_id(fingerprint: str, vod_id: str) -> str:
    """不同 endpoint 可能撞 vod_id，缓存主键带上源指纹。"""
    return f"{fingerprint}:{vod_id}"


def video_cache_id(item: dict, fallback: int = 0) -> str:
    """写入 children_cache.db 的主键。MacCMS 用冒号，避免跨源冲突。"""
    fp = str(item.get("source_fp") or "")
    vod_id = str(item.get("vod_id") or fallback)
    if str(item.get("kind") or "") == "maccms" or fp.startswith("maccms:"):
        return maccms_cache_id(fp, vod_id)
    return f"{fp}_{vod_id}"


def _rule_classes(api: str) -> list[tuple[str, str]]:
    """读取规则首页分类 [(type_id, type_name), ...]。"""
    doc = _http_json(_with_query(api, ac="list")) or _http_json(api) or {}
    out = []
    for item in doc.get("class") or []:
        tid = str(item.get("type_id") or "").strip()
        name = str(item.get("type_name") or "").strip()
        if tid:
            out.append((tid, name))
    return out


def _pick_child_classes(rule_name: str, classes: list[tuple[str, str]]) -> list[str]:
    """选出儿童相关分类 ID。优先用实测表，否则按分类名筛选。"""
    configured = LIST_CLASSES_BY_RULE.get(rule_name)
    if configured:
        return list(configured)
    skip = ("日漫", "日本", "解说", "短剧", "综艺", "电视剧", "大陆剧",
            "港台", "真人", "纪录片", "音轨", "演唱")
    keep = ("少儿", "儿童", "亲子", "幼儿", "卡通", "国产", "国漫",
            "欧美", "美漫", "电影", "剧场", "动画")
    picked = []
    for tid, name in classes:
        if any(s in name for s in skip):
            continue
        if any(k in name for k in keep):
            picked.append(tid)
    return picked


def _class_mode(class_name: str) -> str:
    """根据分类名决定过滤策略：dedicated / whitelist / skip / unknown。"""
    name = class_name or ""
    if any(s in name for s in SKIP_CLASS_MARKERS):
        return "skip"
    if any(k in name for k in DEDICATED_KIDS_CLASS_MARKERS):
        return "dedicated"
    if any(k in name for k in WHITELIST_ANIME_CLASS_MARKERS):
        return "whitelist"
    return "unknown"


def _maccms_resolve_classes(source: dict) -> list[tuple[str, str, str]]:
    """用 ac=list 校验硬编码分类 ID，返回 [(class_id, class_name, mode), ...]。

    不盲信 kids_classes / anime_classes：ID 失效或分类名变成成人/日漫时跳过。
    """
    endpoint = source.get("store_api") or source.get("api") or ""
    name = source.get("name") or endpoint
    live = {tid: cname for tid, cname in _rule_classes(endpoint)}
    wanted: list[tuple[str, str]] = []
    for tid in source.get("kids_classes") or []:
        wanted.append((str(tid), "dedicated"))
    for tid in source.get("anime_classes") or []:
        wanted.append((str(tid), "whitelist"))
    resolved: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for tid, fallback_mode in wanted:
        if tid in seen:
            continue
        seen.add(tid)
        cname = live.get(tid, "")
        if live and tid not in live:
            print(f"[children] {name} class {tid} 当前接口不存在，跳过")
            continue
        mode = _class_mode(cname) if cname else fallback_mode
        if mode == "skip":
            print(f"[children] {name} class {tid} {cname!r} 命中跳过词")
            continue
        if mode == "unknown":
            mode = fallback_mode
        resolved.append((tid, cname or tid, mode))
    return resolved


def _maccms_detail(endpoint: str, vod_id: str) -> dict | None:
    """请求 MacCMS ac=detail&ids=，失败返回 None。"""
    if not endpoint or not vod_id:
        return None
    doc = _http_json(_maccms_request_url(endpoint, ac="detail", ids=str(vod_id)))
    if not isinstance(doc, dict):
        return None
    lst = doc.get("list") or []
    if not lst:
        return None
    first = lst[0]
    return first if isinstance(first, dict) else None


def _maccms_extract_episodes(detail: dict) -> list[dict]:
    """从 vod_play_from / vod_play_url 拆线路和选集，只留真实媒体地址。"""
    if not isinstance(detail, dict):
        return []
    play_from = str(detail.get("vod_play_from") or "")
    play_url = str(detail.get("vod_play_url") or "")
    if not play_url:
        return []
    line_names = [x for x in play_from.split("$$$") if x] or ["儿童专线"]
    url_lines = play_url.split("$$$")
    episodes: list[dict] = []
    for idx, url_line in enumerate(url_lines):
        line_name = line_names[idx] if idx < len(line_names) else f"线路{idx + 1}"
        for ep in url_line.split("#"):
            if "$" not in ep:
                continue
            name, url = ep.split("$", 1)
            name, url = name.strip(), url.strip()
            if not (name and url):
                continue
            if not is_playable_media_url(url):
                continue
            episodes.append({
                "name": name,
                "line": line_name,
                "url": url,
                "flag": url,
            })
    return episodes


def maccms_play_fields(detail: dict, max_lines: int = 1, max_eps: int = 24) -> tuple[str, str]:
    """把 MacCMS 详情转成 App 用的 vod_play_from / vod_play_url。

    只保留真实 m3u8/mp4/flv；网页、空地址、整条线路无效时返回空字符串，
    不生成假线路。
    """
    episodes = _maccms_extract_episodes(detail)
    if not episodes:
        return "儿童专线", ""
    lines: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for ep in episodes:
        line = str(ep.get("line") or "").strip() or "儿童专线"
        if line not in grouped:
            lines.append(line)
            grouped[line] = []
        grouped[line].append(ep)
    # 跳过整条都是网页/空地址的线路，再按 max_lines 取真实可播线路
    playable_lines: list[str] = []
    for line in lines:
        eps = [
            ep for ep in grouped.get(line, [])
            if is_playable_media_url(str(ep.get("url") or ""))
        ]
        if eps:
            grouped[line] = eps
            playable_lines.append(line)
    if not playable_lines:
        return "儿童专线", ""
    chosen = playable_lines[: max(1, int(max_lines or 1))]
    picked: list[dict] = []
    for line in chosen:
        picked.extend(grouped.get(line, []))
    picked = picked[: max(1, int(max_eps or 1))]
    parts = [f"{ep['name']}${ep['url']}" for ep in picked]
    if not parts:
        return "儿童专线", ""
    return chosen[0], "#".join(parts)


def _maccms_list_collect(sources: list[dict], all_items: list[dict]) -> int:
    """采集 MacCMS 少儿/动画分类。单源失败不中断全局。

    kids_classes 用 is_dedicated_kids_title（允许英文儿歌）；
    anime_classes 用 is_children_title（必须命中儿童 IP 白名单）。
    不把播放 URL 固化进长期缓存。
    """
    before = len(all_items)
    seen_ids: set[str] = {
        video_cache_id(x) for x in all_items if x.get("vod_id")
    }
    for ts in sources:
        name = ts.get("name") or ""
        endpoint = ts.get("store_api") or ts.get("api") or ""
        fp = ts.get("fingerprint") or f"maccms:{name}"
        ext = ts.get("ext") or "maccms"
        score = ts.get("score", 80)
        try:
            classes = _maccms_resolve_classes(ts)
        except Exception as e:
            print(f"[children] maccms {name} class list failed: {str(e)[:100]}")
            continue
        if not classes:
            print(f"[children] maccms {name} 没有可用少儿/动画分类，跳过")
            continue
        print(f"[children] maccms {name} classes={[(c[0], c[2]) for c in classes]}")
        for tid, cname, mode in classes:
            title_ok = is_dedicated_kids_title if mode == "dedicated" else is_children_title
            empty = 0
            for pg in range(1, MAX_LIST_PAGES + 1):
                if len(all_items) >= MAX_CACHE_ITEMS:
                    return len(all_items) - before
                try:
                    doc = _http_json(
                        _maccms_request_url(endpoint, ac="videolist", t=tid, pg=str(pg))
                    )
                except Exception as e:
                    print(f"[children] maccms {name} t={tid} pg={pg} fail: {str(e)[:80]}")
                    empty += 1
                    if empty >= MAX_EMPTY_PAGES:
                        break
                    continue
                if not isinstance(doc, dict):
                    empty += 1
                    if empty >= MAX_EMPTY_PAGES:
                        break
                    continue
                lst = doc.get("list") or []
                pagecount = 0
                try:
                    pagecount = int(doc.get("pagecount") or 0)
                except (TypeError, ValueError):
                    pagecount = 0
                if not lst or all(_is_placeholder_item(it) for it in lst):
                    empty += 1
                    # 空页也要看 pagecount，避免无效分类空翻到 MAX_EMPTY_PAGES
                    if empty >= MAX_EMPTY_PAGES or (pagecount and pg >= pagecount):
                        break
                    continue
                empty = 0
                page_keys = []
                for it in lst:
                    vid = str(it.get("vod_id") or it.get("id") or "")
                    if vid:
                        page_keys.append(maccms_cache_id(fp, vid))
                if page_keys and all(k in seen_ids for k in page_keys):
                    break
                got = 0
                for item in lst:
                    if _is_placeholder_item(item):
                        continue
                    title = _item_title(item)
                    vod_id = str(item.get("vod_id") or item.get("id") or "")
                    cache_key = maccms_cache_id(fp, vod_id)
                    if not vod_id or cache_key in seen_ids:
                        continue
                    seen_ids.add(cache_key)
                    if _append_video(
                        all_items,
                        title=title,
                        vod_id=vod_id,
                        pic=str(item.get("vod_pic") or ""),
                        latest=str(item.get("vod_remarks") or ""),
                        source_fp=fp,
                        api=endpoint,
                        ext=ext,
                        score=score,
                        source_class=tid,
                        title_ok=title_ok,
                        kind="maccms",
                        class_name=cname,
                    ):
                        got += 1
                print(
                    f"[children] maccms {name} t={tid}/{cname} pg={pg} "
                    f"raw={len(lst)} kids={got} total={len(all_items)}"
                )
                if pagecount and pg >= pagecount:
                    break
    return len(all_items) - before


def _list_collect(task_sources: list[dict], all_items: list[dict]) -> int:
    """按分类列表分页采集，不再靠关键词搜索凑数。

    请求 ac=videolist&t=<分类>&pg=<页>，直到空页、重复页或达到页数上限。
    只收录命中儿童白名单且能出直链的规则结果。
    """
    before = len(all_items)
    seen_ids: set[str] = {str(x.get("vod_id") or "") for x in all_items}
    for ts in task_sources:
        name = ts.get("name") or ""
        api = ts["api"]
        store_api = ts.get("store_api") or api
        fp = ts["fingerprint"]
        ext = ts.get("ext") or ""
        score = ts.get("score", 0)
        classes = _rule_classes(api)
        type_ids = _pick_child_classes(name, classes)
        if not type_ids:
            print(f"[children] {name} 没有儿童相关分类，跳过列表采集")
            continue
        print(f"[children] {name} list classes={type_ids}")
        for tid in type_ids:
            empty = 0
            for pg in range(1, MAX_LIST_PAGES + 1):
                if len(all_items) >= MAX_CACHE_ITEMS:
                    return len(all_items) - before
                doc = _http_json(_with_query(api, ac="videolist", t=tid, pg=str(pg)))
                lst = (doc or {}).get("list") or []
                if not lst or all(_is_placeholder_item(it) for it in lst):
                    empty += 1
                    if empty >= MAX_EMPTY_PAGES:
                        break
                    continue
                empty = 0
                page_ids = [str(it.get("vod_id") or it.get("id") or "") for it in lst]
                if page_ids and all(vid in seen_ids for vid in page_ids if vid):
                    # 整页都见过，停止该分类翻页
                    break
                got = 0
                for item in lst:
                    if _is_placeholder_item(item):
                        continue
                    title = _item_title(item)
                    vod_id = str(item.get("vod_id") or item.get("id") or "")
                    if not vod_id or vod_id in seen_ids:
                        continue
                    seen_ids.add(vod_id)
                    if _append_video(
                        all_items,
                        title=title,
                        vod_id=vod_id,
                        pic=str(item.get("vod_pic") or ""),
                        latest=str(item.get("vod_remarks") or ""),
                        source_fp=fp,
                        api=store_api,
                        ext=ext,
                        score=score,
                        source_class=tid,
                    ):
                        got += 1
                print(f"[children] {name} t={tid} pg={pg} raw={len(lst)} kids={got} total={len(all_items)}")
    return len(all_items) - before


def _fill_title_from_detail(run_drpy_detail, api: str, vod_id: str) -> str:
    """搜索无标题时回源详情页补 vod_name（动漫豆搜索字段为空）。"""
    if not vod_id:
        return ""
    try:
        detail_res = run_drpy_detail(api, vod_id)
    except Exception as e:
        print(f"[children] detail-fill crashed: {str(e)[:100]}")
        return ""
    if not detail_res.get("success"):
        return ""
    det = detail_res.get("detail") or {}
    title = str(det.get("vod_name") or det.get("title") or "").strip()
    return re.sub(r"<[^>]+>", "", title)


def _search_collect(run_drpy_search, task_sources, all_items,
                    run_drpy_detail=None) -> int:
    """按分类关键词对任务源池执行搜索并收集安全条目。

    每个分类遍历多个关键词；每个关键词遍历规则池，不再命中即停。
    搜索无标题但有 vod_id 时，有限次回源详情补标题（动漫豆）。
    """
    before = len(all_items)
    for type_name, keywords in CATEGORY_KEYWORDS.items():
        type_id = str(list(CATEGORY_KEYWORDS.keys()).index(type_name) + 1)
        kws = SEARCH_KEYWORDS_BY_CATEGORY.get(type_name) or [keywords[0]]
        for kw in kws:
            for ts in task_sources:
                fp = ts["fingerprint"]
                api = ts["api"]
                ext = ts.get("ext") or ""
                store_api = ts.get("store_api") or api
                try:
                    res = run_drpy_search(api, kw)
                except Exception as e:
                    print(f"[children] search {ts.get('name')}/{kw} crashed: {str(e)[:100]}")
                    continue
                if not (res.get("success") and res.get("items")):
                    continue
                got = 0
                detail_fills = 0
                for item in res["items"]:
                    if got >= MAX_ITEMS_PER_KEYWORD:
                        break
                    title = _item_title(item)
                    vod_id = item.get("vod_id") or item.get("id") or ""
                    # 动漫豆等规则搜索不带标题：有限次回源详情补齐
                    if not title and vod_id and run_drpy_detail and detail_fills < MAX_DETAIL_FILL_PER_KEYWORD:
                        title = _fill_title_from_detail(run_drpy_detail, api, vod_id)
                        detail_fills += 1
                    if not title:
                        continue
                    if not _append_video(
                        all_items,
                        title=title,
                        vod_id=str(vod_id),
                        pic=str(item.get("vod_pic") or ""),
                        latest=str(item.get("vod_remarks") or ""),
                        source_fp=fp,
                        api=store_api,
                        ext=ext,
                        score=ts.get("score", 0),
                        source_class=type_name,
                    ):
                        continue
                    got += 1
                if got:
                    print(f"[children] {ts.get('name')}/{kw} collected {got}")
                    # 该关键词已从该规则拿到条目，换下一个关键词（仍遍历所有关键词）
                    break
    return len(all_items) - before


def _populate_cache_from_sources(db_path: str, primary_sources: list[dict]):
    from ponyo_source_manager.core.common import DATA_DIR
    from ponyo_source_manager.probes.drpy_runner import run_drpy_detail, run_drpy_search
    from urllib.parse import urlsplit

    cache_db = DATA_DIR / "children_cache.db"
    con = sqlite3.connect(str(cache_db))
    con.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            type_id TEXT,
            name TEXT,
            pic TEXT,
            latest TEXT,
            source_fp TEXT,
            source_id TEXT,
            api TEXT,
            ext TEXT
        )
    """)
    # 先采集再写库。MacCMS 临时失败不能把已有动漫豆缓存清掉。

    src_db = sqlite3.connect(db_path)
    # A11: 先收集所有条目，再统一去重和安全过滤。
    # 只挑 HTTP 适配器可执行的规则（http(s) + /api/:mod 形式）；
    # 其余（csp_*/本地相对路径/远程 js）交由运行时兜底规则覆盖。
    task_sources: list[dict] = []
    for ps in primary_sources:
        fp = ps["fingerprint"]
        row = src_db.execute(
            "SELECT api, ext FROM raw_source r JOIN norm_source n "
            "ON r.id = n.raw_id WHERE n.fingerprint=?",
            (fp,)).fetchone()
        if not row:
            continue
        api, ext = row
        rule_path = str(api or ext or "")
        if not rule_path:
            continue
        executable = False
        try:
            u = urlsplit(rule_path)
            executable = u.scheme in ("http", "https") and "/api/" in u.path
        except Exception:
            executable = False
        if executable:
            task_sources.append({
                "fingerprint": fp,
                "name": ps.get("name", ""),
                "api": rule_path,
                "ext": ext or "",
                "score": ps.get("score", 0),
            })
    src_db.close()

    if not task_sources:
        print("[children] DB 儿童源均不可由 HTTP 适配器执行，使用运行时兜底规则")
        task_sources = _runtime_fallback_rules()

    all_items: list[dict] = []
    # 主路径：分类列表分页全量采集（整合源，不再靠几个关键词凑数）
    listed = _list_collect(task_sources, all_items)
    print(f"[children] list-collect got {listed}")
    # 列表已经够用时不再跑关键词搜索：动漫豆搜索无标题，回源 detail 很慢
    if listed < 50:
        _search_collect(run_drpy_search, task_sources, all_items,
                        run_drpy_detail=run_drpy_detail)
    if not all_items:
        fb = _runtime_fallback_rules()
        fb = [t for t in fb if t["api"] not in {x["api"] for x in task_sources}]
        if fb:
            print(f"[children] 主源无结果，追加运行时兜底规则: {[t['name'] for t in fb]}")
            extra = _list_collect(fb, all_items)
            if extra < 50:
                _search_collect(run_drpy_search, fb, all_items,
                                run_drpy_detail=run_drpy_detail)

    # MacCMS 少儿/儿歌分类：失败只记日志，不影响已采到的动漫豆条目
    try:
        maccms_got = _maccms_list_collect(MACCMS_KIDS_SOURCES, all_items)
        print(f"[children] maccms-collect got {maccms_got}")
    except Exception as e:
        print(f"[children] maccms-collect failed: {str(e)[:120]}")

    if not all_items:
        print("[children] 本次采集为空，保留已有 children_cache.db")
        con.close()
        return

    # A11: 跨源去重 - 相同标题+年份+季数+语言只保留最佳线路
    deduped = dedupe_children_content(all_items)

    con.execute("DELETE FROM videos")
    inserted = 0
    for item in deduped:
        vid = video_cache_id(item, inserted)
        con.execute(
            "INSERT OR REPLACE INTO videos (id, type_id, name, pic, latest, source_fp, source_id, api, ext) VALUES (?,?,?,?,?,?,?,?,?)",
            (vid, item.get("type_id", ""), item.get("title", ""), item.get("pic", ""), item.get("latest", ""), item.get("source_fp", ""), item.get("vod_id", ""), item.get("api", ""), item.get("ext", ""))
        )
        inserted += 1
    con.commit()
    con.close()
    print(f"Populated {inserted} videos into children_cache.db (filtered from {len(all_items)} raw items)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--report",
                   default=str(HERE / "reports" / "children-report.json"))
    args = p.parse_args()
    result = aggregate_children_sources(args.db, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
