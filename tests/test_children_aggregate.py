#!/usr/bin/env python3
import pytest
from children_aggregate import classify_children_content, is_safe_content, dedupe_children_content


def test_classify_children_content():
    assert classify_children_content("小猪佩奇第一季") == "学龄前"
    assert classify_children_content("熊出没之怪兽计划") == "国产动画"
    assert classify_children_content("猫和老鼠全集") == "经典动画"


def test_is_safe_content():
    assert is_safe_content("小猪佩奇") is True
    assert is_safe_content("成人午夜剧场") is False


def test_dedupe_children_content():
    items = [
        {"title": "小猪佩奇", "year": "2020", "season": "1", "source_fp": "fp1", "quality_score": 90, "play_url": "url1"},
        {"title": "小猪佩奇(第一季)", "year": "2020", "season": "1", "source_fp": "fp2", "quality_score": 95, "play_url": "url2"},
    ]
    deduped = dedupe_children_content(items)
    assert len(deduped) == 1
    assert deduped[0]["routes"][0]["source"] == "fp2"
