#!/usr/bin/env python3
"""direct_parse 语言标注单元测试（中期建议：原声中字提示 + 集名语言兜底）。

异步函数（_try_ranked）用 asyncio.run 包装成同步测试 —— 项目未装 pytest-asyncio，
与现有测试套件（全同步）保持一致。
"""
import asyncio

from ponyo_source_manager.api.direct_parse import (
    _dub_state,
    _try_ranked,
    norm_title,
    pick_episode,
)


# ---------------------------------------------------------------- _dub_state
def test_dub_state_hd_zhongzi_is_unknown():
    # "HD中字" = 原声对白 + 中文字幕，不是中文配音
    assert _dub_state("HD中字") == "unknown"


def test_dub_state_gq_is_unknown():
    # "高清" 无任何语言信息
    assert _dub_state("高清") == "unknown"


def test_dub_state_guoyu_is_dub():
    assert _dub_state("HD国语") == "dub"


def test_dub_state_putonghua_is_dub():
    assert _dub_state("普通话版") == "dub"


def test_dub_state_yuansheng_is_orig():
    assert _dub_state("原声中字") == "orig"


def test_dub_state_english_is_orig():
    assert _dub_state("英语中字") == "orig"


def test_dub_state_vod_name_fallback():
    # 集名无标记时看候选片名
    assert _dub_state("第01集", "小猪佩奇[普通话版]") == "dub"


def test_dub_state_empty():
    assert _dub_state("") == "unknown"
    assert _dub_state(None, None) == "unknown"


# ---------------------------------------------------------------- pick_episode
def test_pick_episode_returns_label_single():
    url, label = pick_episode("HD中字$https://x/index.m3u8", None)
    assert url == "https://x/index.m3u8"
    assert label == "HD中字"


def test_pick_episode_returns_label_multi():
    url, label = pick_episode("第01集$u1#第02集$u2", 2)
    assert url == "u2"
    assert label == "第02集"


def test_pick_episode_out_of_range_takes_last():
    url, label = pick_episode("第01集$u1#第02集$u2", 99)
    assert url == "u2"
    assert label == "第02集"


def test_pick_episode_empty():
    url, label = pick_episode("", 1)
    assert url is None
    assert label is None


# ---------------------------------------------------------------- _try_ranked（mock 出流链）
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """mock httpx.AsyncClient：fetch_detail 返回固定 vod，resolve_share_link 直通。"""

    def __init__(self, vod):
        self._vod = vod

    async def get(self, *args, **kwargs):
        return _FakeResp({"list": [self._vod]})


def _mk_ranked(play_url, vod_name="超级马力欧银河大电影"):
    vod = {"vod_id": "1", "vod_name": vod_name, "vod_play_url": play_url}
    src = {"name": "lzm3u8", "api": "http://x/api.php/provide/vod"}
    return vod, [(vod, src)]


def test_try_ranked_mandarin_request_tags_orig_sub():
    # 请求普通话，命中资源 "HD中字"（无配音标记）-> jxFrom 带 ~原声中字
    vod, ranked = _mk_ranked("HD中字$https://v.lzcdn31.com/x/index.m3u8")
    hit = asyncio.run(_try_ranked(_FakeClient(vod), ranked, ep_index=1, lang_bucket="mandarin"))
    assert hit is not None
    assert hit["jxFrom"] == "direct:lzm3u8~原声中字"
    assert hit["parse"] == 0


def test_try_ranked_mandarin_request_dub_resource_no_tag():
    # 请求普通话，命中资源 "HD国语"（真配音）-> 不加标注
    vod, ranked = _mk_ranked("HD国语$https://v.lzcdn31.com/x/index.m3u8")
    hit = asyncio.run(_try_ranked(_FakeClient(vod), ranked, ep_index=1, lang_bucket="mandarin"))
    assert hit is not None
    assert hit["jxFrom"] == "direct:lzm3u8"


def test_try_ranked_no_lang_request_no_tag():
    # 无语言请求（普通内容）-> 行为与旧版完全一致，不加标注
    vod, ranked = _mk_ranked("第01集$https://x/index.m3u8", vod_name="狂飙")
    hit = asyncio.run(_try_ranked(_FakeClient(vod), ranked, ep_index=1))
    assert hit is not None
    assert hit["jxFrom"] == "direct:lzm3u8"


def test_try_ranked_english_request_not_tagged():
    # 请求英文（非普通话桶）-> 不做原声中字标注（该标注只针对普通话请求）
    vod, ranked = _mk_ranked("HD中字$https://v.lzcdn31.com/x/index.m3u8")
    hit = asyncio.run(_try_ranked(_FakeClient(vod), ranked, ep_index=1, lang_bucket="english"))
    assert hit is not None
    assert hit["jxFrom"] == "direct:lzm3u8"


def test_try_ranked_vod_name_dub_marker_no_tag():
    # 集名无标记但候选片名带 [普通话版] -> 视为配音资源，不加标注
    vod, ranked = _mk_ranked("第01集$https://x/index.m3u8", vod_name="小猪佩奇[普通话版]")
    hit = asyncio.run(_try_ranked(_FakeClient(vod), ranked, ep_index=1, lang_bucket="mandarin"))
    assert hit is not None
    assert hit["jxFrom"] == "direct:lzm3u8"


# ---------------------------------------------------------------- norm_title（回归）
def test_norm_title_regression():
    t, lang, season = norm_title("小猪佩奇 第12季[普通话版]")
    assert lang == "mandarin"
    assert season == 12
    t, lang, season = norm_title("超级马力欧银河大电影")
    assert lang is None
    assert season is None
