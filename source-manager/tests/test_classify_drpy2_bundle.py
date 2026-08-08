from ponyo_source_manager.probes.classify_drpy2_bundle import _episodes, _media_verified, classify_rule


def test_episodes_prioritize_direct_lines():
    vod = {"vod_play_from": "网页$$$量子m3u8", "vod_play_url": "正片$page$$$第1集$direct"}
    episodes = _episodes(vod)
    assert episodes[0]["flag"] == "量子m3u8"
    assert episodes[0]["play_id"] == "direct"


def test_classify_rule_fails_closed_on_search(monkeypatch):
    monkeypatch.setattr(
        "ponyo_source_manager.probes.classify_drpy2_bundle._request_json",
        lambda *_args, **_kwargs: {"list": [{"vod_id": "1", "vod_name": "无关内容"}]},
    )
    result = classify_rule(
        {"module": "r1", "url": "https://cdn/r.js", "source_ids": [1], "names": ["测试"]},
        "http://127.0.0.1:5759", "pwd", ["熊出没"],
    )
    assert result["success"] is False
    assert result["stage"] == "search"


def test_media_verification_rejects_plain_webpage_success():
    assert _media_verified({"success": 1, "m3u8_ok": 0, "segments_ok": 0, "ffprobe_valid": 0}) is False
    assert _media_verified({"success": 1, "m3u8_ok": 1, "segments_ok": 1, "ffprobe_valid": 0}) is True
