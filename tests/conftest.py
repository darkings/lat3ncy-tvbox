import json
from pathlib import Path
import pytest

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def policy():
    return json.loads((PROJECT / "source-manager" / "config" / "policy.json").read_text(encoding="utf-8"))


@pytest.fixture
def sites():
    # 8 条：s0/s1 同 api 不同 name(应同指纹)；s2 带 md5 尾巴与 s3 无尾巴(应同指纹)；其余分类样本
    return [
        {"key": "a1", "name": "星辰影视", "type": 3,
         "api": "https://cdn.jsdelivr.net/gh/x/y@main/js/star.js", "ext": ""},
        {"key": "a2", "name": "极速星辰", "type": 3,
         "api": "https://cdn.jsdelivr.net/gh/x/y@main/js/star.js", "ext": ""},
        {"key": "b1", "name": "次元动漫", "type": 3,
         "api": "https://host.tld/api.php/prov/vod",
         "ext": "https://cdn.jsdelivr.net/gh/x/y@main/jar/spider.jar;md5;ABC123"},
        {"key": "b2", "name": "次元番剧", "type": 3,
         "api": "https://host.tld/api.php/prov/vod",
         "ext": "https://cdn.jsdelivr.net/gh/x/y@main/jar/spider.jar"},
        {"key": "c1", "name": "宝宝巴士儿童", "type": 3, "api": "https://k.tld/kids", "ext": ""},
        {"key": "d1", "name": "自然纪录世界", "type": 3, "api": "https://d.tld/doc", "ext": ""},
        {"key": "e1", "name": "夸克网盘", "type": 3, "api": "https://q.tld/quark", "ext": ""},
        {"key": "f1", "name": "Ponyo 设置", "type": 3, "api": "https://s.tld/settings", "ext": ""},
    ]
