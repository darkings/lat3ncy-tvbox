import json

from ponyo_source_manager.probes.playback_audit import (
    build_playback_audit,
    classify_play_url,
    sanitize_playurl_evidence,
)


def test_classification_covers_tvbox_playback_handoffs():
    assert classify_play_url("https://cdn.test/master.m3u8?token=x")["url_class"] == "hls"
    assert classify_play_url("https://cdn.test/video.mp4")["url_class"] == "direct_media"
    assert classify_play_url("https://v.qq.com/x/abc.html")["url_class"] == "platform_or_web_page"
    assert classify_play_url("http://127.0.0.1:5757/proxy/a/b.m3u8")["url_class"] == "local_proxy"
    assert classify_play_url("https://jx.test/parse?id=1")["url_class"] == "parser_endpoint"


def test_sanitized_evidence_never_contains_url_query_or_header_values():
    result = {
        "play_url": "https://cdn.test/a.m3u8?token=top-secret#fragment",
        "header": {"Referer": "https://secret.example/", "Cookie": "sid=secret"},
    }
    evidence = sanitize_playurl_evidence(result)
    serialized = json.dumps(evidence)
    assert evidence["host"] == "cdn.test"
    assert evidence["header_keys"] == ["cookie", "referer"]
    assert evidence["sensitive_header_present"] is True
    assert "top-secret" not in serialized
    assert "sid=secret" not in serialized
    assert "secret.example" not in serialized


def test_report_builds_transition_counts_and_remediation_cohort():
    report = {
        "sources": [
            {
                "fingerprint": "fp-page", "name": "Page", "content_lane": "vod",
                "results": [
                    {"test_type": "playurl", "success": 1, "play_url": "https://x.test/watch/a.html"},
                    {"test_type": "playback", "success": 1},
                    {"test_type": "ffprobe", "success": 0, "failure_stage": "ffprobe_failed"},
                ],
            },
            {
                "fingerprint": "fp-hls", "name": "HLS", "content_lane": "vod",
                "results": [
                    {"test_type": "playurl", "success": 1, "play_url": "https://x.test/a.m3u8"},
                    {"test_type": "playback", "success": 0, "failure_stage": "media_manifest_failed"},
                ],
            },
        ]
    }
    audit = build_playback_audit(report)
    assert audit["summary"]["play_urls_classified"] == 2
    assert audit["summary"]["classifications"] == {
        "hls": 1, "platform_or_web_page": 1,
    }
    assert audit["summary"]["transitions"]["platform_or_web_page->ffprobe_failed"] == 1
    assert audit["candidates"][0]["fingerprint"] == "fp-page"
    assert all("play_url" not in row for row in audit["evidence"])
