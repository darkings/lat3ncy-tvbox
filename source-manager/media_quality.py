#!/usr/bin/env python3
"""ffprobe 媒体质量检测：检查实际分辨率、码率、编码，判定高清等级。

对应 PLAN §六 第 6 层 + §七 高清判断标准。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# PLAN §七 高清判断标准
QUALITY_TIERS = [
    {"tier": "uhd",  "min_height": 2160, "min_bitrate": 10_000_000},
    {"tier": "fhd",  "min_height": 1080, "min_bitrate":  3_000_000},
    {"tier": "hd",   "min_height":  720, "min_bitrate":  1_500_000},
    {"tier": "sd",   "min_height":    0, "min_bitrate":          0},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_quality(height: int, bitrate: int) -> str:
    """根据 PLAN §七 标准判定等级。"""
    for tier in QUALITY_TIERS:
        if height >= tier["min_height"] and bitrate >= tier["min_bitrate"]:
            return tier["tier"]
    return "sd"


def run_ffprobe(url: str, *, timeout: int = 15,
                ffprobe_cmd: str = "ffprobe") -> dict:
    """调用 ffprobe 检查媒体流信息。

    可通过替换 ffprobe_cmd 或 mock subprocess 实现测试。
    """
    cmd = [
        ffprobe_cmd,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        "-timeout", str(timeout * 1_000_000),  # ffprobe 用微秒
        url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()[:500]}
        return {"success": True, **json.loads(result.stdout)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"ffprobe timeout after {timeout}s"}
    except (json.JSONDecodeError, Exception) as e:
        return {"success": False, "error": str(e)[:500]}


def analyze_stream(probe_result: dict) -> dict:
    """从 ffprobe 结果中提取视频/音频关键信息。"""
    if not probe_result.get("success"):
        return {
            "success": 0, "error": probe_result.get("error"),
            "width": None, "height": None, "video_codec": None,
            "video_bitrate": None, "audio_codec": None,
            "frame_rate": None, "duration_s": None, "quality_tier": None,
        }

    streams = probe_result.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = probe_result.get("format", {})

    width = video.get("width") if video else None
    height = video.get("height") if video else None
    video_codec = video.get("codec_name") if video else None

    # 码率：优先 stream 级别，其次 format 级别
    v_bitrate = None
    if video:
        v_bitrate = video.get("bit_rate")
        if v_bitrate:
            v_bitrate = int(v_bitrate)
    if not v_bitrate and fmt.get("bit_rate"):
        v_bitrate = int(fmt["bit_rate"])

    audio_codec = audio.get("codec_name") if audio else None

    # 帧率
    frame_rate = None
    if video and video.get("r_frame_rate"):
        parts = video["r_frame_rate"].split("/")
        if len(parts) == 2 and int(parts[1]) > 0:
            frame_rate = round(int(parts[0]) / int(parts[1]), 2)

    duration_s = None
    if fmt.get("duration"):
        duration_s = round(float(fmt["duration"]), 2)

    quality_tier = classify_quality(height or 0, v_bitrate or 0)

    return {
        "success": 1,
        "width": width, "height": height,
        "video_codec": video_codec, "video_bitrate": v_bitrate,
        "audio_codec": audio_codec, "frame_rate": frame_rate,
        "duration_s": duration_s, "quality_tier": quality_tier,
        "error": None,
    }


def probe_and_save(db_path: str, fingerprint: str, play_url: str,
                   content_title: str = "", *, ffprobe_cmd: str = "ffprobe",
                   now: str | None = None) -> dict:
    """执行 ffprobe 并将结果写入 media_probe 表。"""
    now = now or _now()
    raw = run_ffprobe(play_url, ffprobe_cmd=ffprobe_cmd)
    info = analyze_stream(raw)

    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO media_probe"
        "(fingerprint,content_title,play_url,width,height,video_codec,"
        "video_bitrate,audio_codec,frame_rate,duration_s,quality_tier,"
        "success,error,probed_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fingerprint, content_title, play_url,
         info["width"], info["height"], info["video_codec"],
         info["video_bitrate"], info["audio_codec"], info["frame_rate"],
         info["duration_s"], info["quality_tier"],
         info["success"], info["error"], now))
    con.commit()
    con.close()
    return info


def get_quality_stats(db_path: str, fingerprint: str,
                      days: int = 7) -> dict:
    """获取某源近 N 天的高清比例统计。"""
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT quality_tier, COUNT(*) FROM media_probe "
        "WHERE fingerprint=? AND success=1 "
        "AND probed_at >= datetime('now', ?) "
        "GROUP BY quality_tier",
        (fingerprint, f"-{days} days")).fetchall()
    con.close()

    total = sum(count for _, count in rows)
    tiers = {tier: count for tier, count in rows}
    if total == 0:
        return {"total": 0, "hd_ratio": 0, "fhd_ratio": 0}

    hd_plus = sum(tiers.get(t, 0) for t in ("hd", "fhd", "uhd"))
    fhd_plus = sum(tiers.get(t, 0) for t in ("fhd", "uhd"))
    return {
        "total": total,
        "tiers": tiers,
        "hd_ratio": round(hd_plus / total, 3),
        "fhd_ratio": round(fhd_plus / total, 3),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--url", required=True, help="播放地址")
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--ffprobe", default="ffprobe")
    args = p.parse_args()
    result = probe_and_save(args.db, args.fingerprint, args.url,
                           args.title, ffprobe_cmd=args.ffprobe)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
