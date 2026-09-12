from ponyo_source_manager.publishing.category_taxonomy import (
    CategoryResult,
    apply_site_category_overrides,
    classify_title,
    ensure_official_platform_categories,
    load_taxonomy,
    normalize_categories,
    normalize_category_name,
)


def test_exact_and_substring_mapping():
    tx = load_taxonomy()
    assert normalize_category_name("电影", tx) == "电影"
    assert normalize_category_name("动作片", tx) == "电影"
    assert normalize_category_name("喜剧片", tx) == "电影"
    assert normalize_category_name("连续剧", tx) == "电视剧"
    assert normalize_category_name("港台剧", tx) == "电视剧"
    assert normalize_category_name("番剧", tx) == "动漫"
    assert normalize_category_name("记录片", tx) == "纪录片"
    assert normalize_category_name("亲子", tx) == "少儿"
    assert normalize_category_name("爽文短剧", tx) == "短剧"
    assert normalize_category_name("世界杯", tx) == "体育"
    assert normalize_category_name("央视", tx) == "直播"
    assert normalize_category_name("影视解说", tx) == "其他"


def test_specific_category_wins_over_generic():
    tx = load_taxonomy()
    assert normalize_category_name("动画电影", tx) == "动漫"
    assert normalize_category_name("动漫电影", tx) == "动漫"
    assert normalize_category_name("欧美综艺", tx) == "综艺"
    assert normalize_category_name("4k影视剧", tx) == "电视剧"
    assert normalize_category_name("AI漫剧", tx) == "短剧"


def test_adult_names_denied_not_mapped():
    tx = load_taxonomy()
    assert normalize_category_name("伦理片", tx) is None
    assert normalize_category_name("福利", tx) is None
    assert normalize_category_name("里番", tx) is None


def test_unmapped_collected():
    tx = load_taxonomy()
    result = normalize_categories(["电影", "乱七八糟", "伦理片"], tx)
    assert result.categories == ["电影"]
    assert result.unmapped == ["乱七八糟"]
    assert result.denied == ["伦理片"]


def test_dedupe_and_taxonomy_order():
    tx = load_taxonomy()
    result = normalize_categories(["动漫", "电影", "动作片", "综艺"], tx)
    assert result.categories == ["动漫", "综艺", "电影"]


def test_host_whitelist_priority(tmp_path):
    import json

    whitelist_path = tmp_path / "whitelist.json"
    whitelist_path.write_text(
        json.dumps({"mdzyapi.com": ["电影", "连续剧", "记录片", "AI漫剧", "央视"]}),
        encoding="utf-8",
    )
    tx = load_taxonomy()
    result = normalize_categories(
        ["广告"], tx, host="www.mdzyapi.com", host_whitelist={}
    )
    assert result.categories == []  # 无白名单配置时按原始输入
    import json as _json

    wl = _json.loads(whitelist_path.read_text(encoding="utf-8"))
    result = normalize_categories(
        ["广告"], tx, host="mdzyapi.com", host_whitelist=wl
    )
    assert result.categories == ["纪录片", "短剧", "电影", "电视剧", "直播"]


def test_classify_title():
    tx = load_taxonomy()
    assert classify_title("更新至第12集", tx) == "电视剧"
    assert classify_title("某电影大电影", tx) == "电影"
    assert classify_title("世界杯决赛", tx) == "体育"


OFFICIAL_KEYS = (
    "drpyS_腾云驾雾[官]",
    "drpyS_优酷[官]",
    "drpyS_百忙无果[官]",
    "drpyS_奇珍异兽[官]",
)


def test_site_override_adds_documentary_to_official_sources(tmp_path):
    # 覆盖配置是订阅白名单来源之一：官源默认四类后必须追加纪录片
    override = tmp_path / "site-category-overrides.json"
    override.write_text(
        '{"add": {"drpyS_腾云驾雾[官]": ["少儿", "纪录片"]}}',
        encoding="utf-8",
    )
    sites = [
        {
            "key": "drpyS_腾云驾雾[官]",
            "categories": ["电影", "电视剧", "综艺", "动漫"],
            "category_provenance": "default_drpy",
        }
    ]
    changed = apply_site_category_overrides(sites, path=override)
    assert changed == 1
    assert sites[0]["categories"] == [
        "电影",
        "电视剧",
        "综艺",
        "动漫",
        "少儿",
        "纪录片",
    ]
    assert sites[0]["category_provenance"].endswith("+site_override")


def test_ensure_official_platform_categories_fills_missing_docs():
    # 覆盖文件缺失时，代码兜底仍要给四个官源补上基础四类 + 少儿/纪录片
    sites = [
        {"key": "drpyS_腾云驾雾[官]", "categories": ["电影", "电视剧", "综艺", "动漫"]},
        {"key": "drpyS_优酷[官]", "categories": None},
        {"key": "drpyS_百忙无果[官]", "categories": ["少儿"]},
        {"key": "drpyS_奇珍异兽[官]", "categories": ["电影", "电视剧", "综艺", "动漫"]},
        {"key": "other-cms", "categories": ["电影"]},
    ]
    changed = ensure_official_platform_categories(sites)
    assert changed == 4
    required = ["电影", "电视剧", "综艺", "动漫", "少儿", "纪录片"]
    for site in sites[:4]:
        for name in required:
            assert name in site["categories"]
        assert "official_required" in site["category_provenance"]
    assert sites[4]["categories"] == ["电影"]


def test_ensure_official_platform_categories_is_idempotent():
    # 已经齐全时不再改写，避免每次生成 provenance 无限追加
    sites = [
        {
            "key": key,
            "categories": ["电影", "电视剧", "综艺", "动漫", "少儿", "纪录片"],
            "category_provenance": "default_drpy+site_override",
        }
        for key in OFFICIAL_KEYS
    ]
    assert ensure_official_platform_categories(sites) == 0
    for site in sites:
        assert site["categories"][-2:] == ["少儿", "纪录片"]
        assert site["category_provenance"] == "default_drpy+site_override"
