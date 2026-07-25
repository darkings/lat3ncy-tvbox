import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import compute_fingerprint, classify, strip_md5, assert_no_proxy


def test_strip_md5():
    assert strip_md5("http://x/a.jar;md5;ABC") == "http://x/a.jar"
    assert strip_md5("http://x/a.jar") == "http://x/a.jar"


def test_same_api_diff_name_same_fp(sites):
    fp1, _ = compute_fingerprint(sites[0])  # 星辰影视
    fp2, _ = compute_fingerprint(sites[1])  # 极速星辰
    assert fp1 == fp2


def test_md5_tail_does_not_change_fp(sites):
    fp1, _ = compute_fingerprint(sites[2])  # ext 带 ;md5;
    fp2, _ = compute_fingerprint(sites[3])  # ext 无尾巴
    assert fp1 == fp2


def test_diff_api_diff_fp(sites):
    fp1, _ = compute_fingerprint(sites[0])
    fp3, _ = compute_fingerprint(sites[4])
    assert fp1 != fp3


def test_api_host_extracted(sites):
    _, meta = compute_fingerprint(sites[2])
    assert meta["api_host"] == "host.tld"


def test_classify_kids_before_anime(policy):
    assert classify("宝宝巴士儿童动画", policy) == "儿童"


def test_classify_categories(policy):
    assert classify("次元动漫", policy) == "动漫"
    assert classify("夸克网盘", policy) == "网盘"
    assert classify("自然纪录世界", policy) == "纪录"
    assert classify("Ponyo 设置", policy) == "工具"
    assert classify("无关键词xyz", policy) == "未分类"


def test_assert_no_proxy_returns_list():
    assert isinstance(assert_no_proxy(), list)
