#!/usr/bin/env python3
import sqlite3

import pytest

from ponyo_source_manager.probes.media_quality import (
    analyze_stream,
    classify_quality,
    evaluate_duration,
    infer_content_type,
    reclassify_existing_media,
)


def test_classify_quality():
    assert classify_quality(2160, 12_000_000) == "uhd"
    assert classify_quality(1080, 4_000_000) == "fhd"
    assert classify_quality(720, 2_000_000) == "hd"
    assert classify_quality(480, 800_000) == "sd"


@pytest.mark.parametrize(
    ("width", "height", "bitrate", "expected"),
    [
        (1920, 808, 0, "fhd"),
        (1920, 1080, 65, "fhd"),
        (1280, 720, 0, "hd"),
        (1080, 1920, 0, "fhd"),
        (720, 1280, 0, "hd"),
        (512, 288, 397_716, "sd"),
        (1920, 1080, 2_000_000, "hd"),
    ],
)
def test_classify_quality_uses_resolution_when_bitrate_is_missing_or_invalid(
    width, height, bitrate, expected
):
    assert classify_quality(height, bitrate, width=width) == expected


def test_analyze_stream_accepts_cinematic_fhd_without_bitrate():
    result = analyze_stream(
        {
            "success": True,
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 808,
                    "codec_name": "h264",
                    "r_frame_rate": "24/1",
                }
            ],
            "format": {"duration": "7056.76"},
        }
    )
    assert result["quality_tier"] == "fhd"


def test_reclassify_existing_media_updates_only_successful_video_evidence(tmp_path):
    db_path = tmp_path / "sources.db"
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE media_probe ("
        "id INTEGER PRIMARY KEY, width INTEGER, height INTEGER, "
        "video_bitrate INTEGER, quality_tier TEXT, ffprobe_success INTEGER)"
    )
    con.executemany(
        "INSERT INTO media_probe VALUES(?,?,?,?,?,?)",
        [
            (1, 1920, 808, None, "sd", 1),
            (2, 1280, 720, 55, "sd", 1),
            (3, 512, 288, 397_716, "sd", 1),
            (4, 1920, 1080, None, "sd", 0),
        ],
    )
    con.commit()
    con.close()

    result = reclassify_existing_media(db_path)
    assert result == {
        "scanned": 3,
        "changed": 2,
        "before": {"sd": 3},
        "after": {"fhd": 1, "hd": 1, "sd": 1},
    }
    con = sqlite3.connect(db_path)
    assert con.execute(
        "SELECT id,quality_tier FROM media_probe ORDER BY id"
    ).fetchall() == [(1, "fhd"), (2, "hd"), (3, "sd"), (4, "sd")]
    con.close()


def test_analyze_stream():
    mock_ffprobe_res = {
        "success": True,
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "codec_name": "h264",
                "bit_rate": "3500000",
                "r_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "120.5"},
    }
    info = analyze_stream(mock_ffprobe_res)
    assert info["success"] == 1
    assert info["height"] == 1080
    assert info["quality_tier"] == "fhd"
    assert info["video_codec"] == "h264"
    assert info["frame_rate"] == 30.0


@pytest.mark.parametrize(
    ("metadata", "episodes", "hint", "expected"),
    [
        ({"type_name": "动作电影"}, 1, "", "movie"),
        ({"vod_class": "国产电视剧"}, 36, "", "series"),
        ({}, 80, "短剧聚合[短]", "short_drama"),
        ({"type_name": "少儿动画"}, 20, "", "animation"),
        ({"type_name": "纪录片"}, 1, "", "documentary"),
        ({"type_name": "综艺"}, 12, "", "variety"),
        ({}, 30, "爱玩音乐[听]", "audio_music"),
        ({"vod_name": "夜曲"}, 1, "DJ音乐[听]", "audio_music"),
        ({"type_name": "音乐"}, 1, "", "audio_music"),
    ],
)
def test_infer_content_type(metadata, episodes, hint, expected):
    result = infer_content_type(
        "测试内容", metadata, episode_count=episodes, source_hint=hint
    )
    assert result["content_type"] == expected


def test_audio_music_duration_rule():
    # 3-5 分钟歌曲应通过 60s 门槛；10 秒碎片应拒绝
    assert evaluate_duration(230, "audio_music")["duration_pass"] == 1
    assert evaluate_duration(61, "audio_music")["duration_pass"] == 1
    assert evaluate_duration(59, "audio_music")["duration_pass"] == 0
    assert evaluate_duration(10, "audio_music")["duration_pass"] == 0


def test_duration_rules_are_type_specific():
    assert evaluate_duration(1_300, "movie")["duration_pass"] == 1
    assert evaluate_duration(600, "movie")["duration_pass"] == 0
    assert evaluate_duration(480, "series")["duration_pass"] == 1
    assert evaluate_duration(120, "series")["duration_pass"] == 0
    assert evaluate_duration(45, "short_drama")["duration_pass"] == 1
    assert evaluate_duration(8, "short_drama")["duration_pass"] == 0
    assert evaluate_duration(None, "unknown")["duration_pass"] == 0
