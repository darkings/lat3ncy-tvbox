import json
from pathlib import Path

from ponyo_source_manager.publishing.release import (
    publish_release,
    validate_before_publish,
)


def _create_mock_staging(
    tmp_path: Path, normal_count: int, children_count: int, live_count: int
):
    staging = tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    sites = []
    # A10/A23: 生成匹配 20/4/2/2/1 分类配额的站点名称
    category_names = {
        "影视": [f"影视综合站{i}" for i in range(30)],
        "动漫": [f"动漫资源站{i}" for i in range(10)],
        "纪录": [f"纪录片频道{i}" for i in range(5)],
        "综艺": [f"综艺大全{i}" for i in range(5)],
        "听书短剧": [f"啊哈DJ[听]{i}" for i in range(5)],
    }
    # 按配额分配: 影视20, 动漫4, 纪录2, 综艺2, 听书短剧1 = 29
    quota = {"影视": 20, "动漫": 4, "纪录": 2, "综艺": 2, "听书短剧": 1}
    idx = 0
    for cat, count in quota.items():
        for j in range(min(count, normal_count - idx)):
            if idx >= normal_count:
                break
            sites.append({"key": f"normal_site_{idx}", "name": category_names[cat][j]})
            idx += 1
    # 如果 normal_count 不是 29，用影视填充剩余
    while idx < normal_count:
        sites.append({"key": f"normal_site_{idx}", "name": f"影视综合站{idx}"})
        idx += 1

    for i in range(children_count):
        sites.append({"key": "Ponyo_Children", "name": "Ponyo Children"})

    # 加上豁免站点
    sites.append({"key": "drpy_js_豆瓣", "name": "豆瓣"})

    lives = [
        {"name": f"Live {i}", "url": f"http://live{i}.m3u8"} for i in range(live_count)
    ]

    lite_data = {"sites": sites, "lives": lives}
    lite_str = json.dumps(lite_data)
    (staging / "ponyo-lite.json").write_text(lite_str, encoding="utf-8")
    (staging / "ponyo-full.json").write_text(
        json.dumps({"sites": sites}), encoding="utf-8"
    )
    (staging / "ponyo-live.json").write_text(
        json.dumps({"lives": lives}), encoding="utf-8"
    )
    (staging / "ponyo-children.json").write_text(
        json.dumps({"sites": []}), encoding="utf-8"
    )

    import hashlib

    def _sha256(b):
        return hashlib.sha256(b).hexdigest()

    manifest_data = {
        "version": "test-v1",
        "files": {
            "ponyo-lite.json": {
                "sha256": _sha256(lite_str.encode("utf-8")),
                "size": len(lite_str),
            },
            "ponyo-full.json": {
                "sha256": _sha256(json.dumps({"sites": sites}).encode("utf-8")),
                "size": 10,
            },
            "ponyo-live.json": {
                "sha256": _sha256(json.dumps({"lives": lives}).encode("utf-8")),
                "size": 10,
            },
            "ponyo-children.json": {
                "sha256": _sha256(json.dumps({"sites": []}).encode("utf-8")),
                "size": 10,
            },
        },
    }
    (staging / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    return staging


def test_validate_rejects_non_29_plus_1(tmp_path):
    # 28 + 1 (应该被拦截)
    stg28 = _create_mock_staging(
        tmp_path / "stg28", normal_count=28, children_count=1, live_count=1
    )
    valid, errs = validate_before_publish(stg28)
    assert valid is False
    assert any("不等于 29" in e for e in errs)

    # 30 + 1 (应该被拦截)
    stg30 = _create_mock_staging(
        tmp_path / "stg30", normal_count=30, children_count=1, live_count=1
    )
    valid, errs = validate_before_publish(stg30)
    assert valid is False

    # 29 + 0 (应该被拦截)
    stg29_0 = _create_mock_staging(
        tmp_path / "stg29_0", normal_count=29, children_count=0, live_count=1
    )
    valid, errs = validate_before_publish(stg29_0)
    assert valid is False
    assert any("不等于 1" in e for e in errs)

    # 严格 29 + 1 (应该放行)
    stg29_1 = _create_mock_staging(
        tmp_path / "stg29_1", normal_count=29, children_count=1, live_count=1
    )
    valid, errs = validate_before_publish(stg29_1)
    assert valid is True
    assert len(errs) == 0
