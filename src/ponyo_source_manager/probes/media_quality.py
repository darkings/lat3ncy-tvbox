#!/usr/bin/env python3
"""ffprobe 媒体质量检测：检查实际分辨率、码率、编码，判定高清等级。

对应 PLAN §六 第 6 层 + §七 高清判断标准。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_HOME as HERE

DURATION_RULES = {
    "movie": 20 * 60,
    "series": 8 * 60,
    "short_drama": 30,
    "animation": 5 * 60,
    "documentary": 10 * 60,
    "variety": 10 * 60,
    "children": 3 * 60,
    "audio_music": 60,  # 歌曲/听书：≥1 分钟即可，避免 3-5 分钟歌曲被按剧集门槛误杀
    "unknown": 30,
}

CONTENT_TYPE_PATTERNS = (
    ("short_drama", r"短剧|微短|竖屏|爽剧|短视频|\[短\]"),
    ("audio_music", r"\[听\]|音乐|dj|music|song|album"),
    ("documentary", r"纪录|纪实|documentary"),
    ("variety", r"综艺|真人秀|脱口秀|variety|show"),
    ("animation", r"动漫|动画|番剧|anime|cartoon"),
    ("children", r"儿童|少儿|亲子|宝宝|幼儿|kids"),
    ("movie", r"电影|影院|院线|动作片|喜剧片|科幻片|恐怖片|剧情片|movie|film"),
    ("series", r"电视剧|连续剧|国产剧|港剧|美剧|韩剧|日剧|泰剧|剧集|series|tv"),
)


def infer_content_type(
    title: str = "",
    metadata: dict | None = None,
    *,
    episode_count: int = 0,
    source_hint: str = "",
) -> dict:
    """Infer a conservative duration class from T4 metadata and source hints."""
    metadata = metadata if isinstance(metadata, dict) else {}
    fields = (
        "type_name",
        "vod_class",
        "vod_type",
        "vod_tag",
        "class",
        "category",
        "cate",
        "vod_name",
    )
    values = [str(title or ""), str(source_hint or "")]
    values.extend(str(metadata.get(field, "")) for field in fields)
    text = " ".join(values).lower()
    for content_type, pattern in CONTENT_TYPE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return {
                "content_type": content_type,
                "confidence": "explicit",
                "evidence": pattern,
            }
    if episode_count > 1:
        return {
            "content_type": "series",
            "confidence": "episode_count",
            "evidence": f"episode_count={episode_count}",
        }
    return {"content_type": "unknown", "confidence": "fallback", "evidence": ""}


def evaluate_duration(duration_s: float | int | None, content_type: str) -> dict:
    content_type = content_type if content_type in DURATION_RULES else "unknown"
    minimum = float(DURATION_RULES[content_type])
    try:
        duration = float(duration_s) if duration_s is not None else None
    except (TypeError, ValueError):
        duration = None
    passed = bool(duration is not None and duration >= minimum)
    if duration is None:
        reason = f"missing duration for {content_type}"
    elif passed:
        reason = (
            f"duration {duration:.2f}s >= {minimum:.0f}s minimum for {content_type}"
        )
    else:
        reason = f"duration {duration:.2f}s < {minimum:.0f}s minimum for {content_type}"
    return {
        "content_type": content_type,
        "min_duration_s": minimum,
        "duration_pass": 1 if passed else 0,
        "duration_reason": reason,
    }


# PLAN §七 高清判断标准
QUALITY_TIERS = [
    {"tier": "uhd", "min_height": 2160, "min_bitrate": 10_000_000},
    {"tier": "fhd", "min_height": 1080, "min_bitrate": 3_000_000},
    {"tier": "hd", "min_height": 720, "min_bitrate": 1_500_000},
    {"tier": "sd", "min_height": 0, "min_bitrate": 0},
]


# ffprobe frequently omits bitrate for HLS, and some demuxers report tiny
# placeholder values such as 53 or 156 bit/s. Such values are not reliable
# enough to downgrade otherwise valid resolution evidence.
MIN_RELIABLE_VIDEO_BITRATE = 100_000
RESOLUTION_TIERS = [
    {"tier": "uhd", "min_long_edge": 3840, "min_short_edge": 1600},
    {"tier": "fhd", "min_long_edge": 1920, "min_short_edge": 720},
    {"tier": "hd", "min_long_edge": 1280, "min_short_edge": 540},
]
TIER_RANK = {"sd": 0, "hd": 1, "fhd": 2, "uhd": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_quality(height: int, bitrate: int, *, width: int = 0) -> str:
    """Classify quality without treating missing HLS bitrate as SD.

    Resolution is orientation independent and accepts common cinematic crops
    such as 1920x808. A reliable bitrate may cap the resolution-derived tier;
    missing or implausibly tiny bitrate values are treated as unknown.
    """
    width = max(0, int(width or 0))
    height = max(0, int(height or 0))
    bitrate = max(0, int(bitrate or 0))

    resolution_tier = "sd"
    if width and height:
        long_edge = max(width, height)
        short_edge = min(width, height)
        for tier in RESOLUTION_TIERS:
            if (
                long_edge >= tier["min_long_edge"]
                and short_edge >= tier["min_short_edge"]
            ):
                resolution_tier = tier["tier"]
                break
    elif height:
        # Compatibility for callers that only know the vertical size.
        for tier in QUALITY_TIERS:
            if height >= tier["min_height"]:
                resolution_tier = tier["tier"]
                break

    if bitrate < MIN_RELIABLE_VIDEO_BITRATE:
        return resolution_tier

    bitrate_tier = "sd"
    for tier in QUALITY_TIERS:
        if bitrate >= tier["min_bitrate"]:
            bitrate_tier = tier["tier"]
            break
    if resolution_tier == "sd":
        return "sd"
    return min(
        (resolution_tier, bitrate_tier),
        key=lambda tier: TIER_RANK[tier],
    )


def run_ffprobe(
    url: str,
    *,
    timeout: int = 15,
    ffprobe_cmd: str = "ffprobe",
    request_headers: dict[str, str] | None = None,
) -> dict:
    """调用 ffprobe 检查媒体流信息。

    可通过替换 ffprobe_cmd 或 mock subprocess 实现测试。
    """
    cmd = [
        ffprobe_cmd,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-timeout",
        str(timeout * 1_000_000),  # ffprobe 用微秒
    ]
    if request_headers:
        header_blob = "".join(
            f"{key}: {value}\r\n" for key, value in request_headers.items()
        )
        cmd.extend(["-headers", header_blob])
    cmd.append(url)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 5
        )
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
            "success": 0,
            "error": probe_result.get("error"),
            "width": None,
            "height": None,
            "video_codec": None,
            "video_bitrate": None,
            "audio_codec": None,
            "frame_rate": None,
            "duration_s": None,
            "quality_tier": None,
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

    quality_tier = classify_quality(
        height or 0,
        v_bitrate or 0,
        width=width or 0,
    )

    return {
        "success": 1,
        "width": width,
        "height": height,
        "video_codec": video_codec,
        "video_bitrate": v_bitrate,
        "audio_codec": audio_codec,
        "frame_rate": frame_rate,
        "duration_s": duration_s,
        "quality_tier": quality_tier,
        "error": None,
    }


def probe_and_save(
    db_path: str,
    fingerprint: str,
    play_url: str,
    content_title: str = "",
    *,
    ffprobe_cmd: str = "ffprobe",
    request_headers: dict[str, str] | None = None,
    content_type: str = "unknown",
    now: str | None = None,
) -> dict:
    """执行 ffprobe 并将结果写入 media_probe 表。"""
    now = now or _now()
    raw = run_ffprobe(
        play_url, ffprobe_cmd=ffprobe_cmd, request_headers=request_headers
    )
    info = analyze_stream(raw)
    ffprobe_success = int(bool(info.get("success")))
    duration = evaluate_duration(info.get("duration_s"), content_type)
    info.update(duration)
    if ffprobe_success and not duration["duration_pass"]:
        info["success"] = 0
        info["error"] = duration["duration_reason"]
    info["ffprobe_success"] = ffprobe_success

    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO media_probe"
        "(fingerprint,content_title,play_url,width,height,video_codec,"
        "video_bitrate,audio_codec,frame_rate,duration_s,quality_tier,"
        "success,error,probed_at,content_type,min_duration_s,duration_pass,"
        "duration_reason,ffprobe_success)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            fingerprint,
            content_title,
            play_url,
            info["width"],
            info["height"],
            info["video_codec"],
            info["video_bitrate"],
            info["audio_codec"],
            info["frame_rate"],
            info["duration_s"],
            info["quality_tier"],
            info["success"],
            info["error"],
            now,
            info["content_type"],
            info["min_duration_s"],
            info["duration_pass"],
            info["duration_reason"],
            info["ffprobe_success"],
        ),
    )
    con.commit()
    con.close()
    return info


def reclassify_existing_media(db_path: str) -> dict:
    """Reclassify stored successful ffprobe evidence without network access."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,width,height,video_bitrate,quality_tier FROM media_probe "
        "WHERE ffprobe_success=1 AND width IS NOT NULL AND height IS NOT NULL"
    ).fetchall()
    changes: list[tuple[str, int]] = []
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for row in rows:
        old_tier = row["quality_tier"] or "sd"
        new_tier = classify_quality(
            row["height"] or 0,
            row["video_bitrate"] or 0,
            width=row["width"] or 0,
        )
        before[old_tier] = before.get(old_tier, 0) + 1
        after[new_tier] = after.get(new_tier, 0) + 1
        if new_tier != old_tier:
            changes.append((new_tier, row["id"]))
    con.executemany(
        "UPDATE media_probe SET quality_tier=? WHERE id=?",
        changes,
    )
    con.commit()
    con.close()
    return {
        "scanned": len(rows),
        "changed": len(changes),
        "before": before,
        "after": after,
    }


def get_quality_stats(db_path: str, fingerprint: str, days: int = 7) -> dict:
    """获取某源近 N 天的高清比例统计。"""
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT quality_tier, COUNT(*) FROM media_probe "
        "WHERE fingerprint=? AND success=1 "
        "AND probed_at >= datetime('now', ?) "
        "GROUP BY quality_tier",
        (fingerprint, f"-{days} days"),
    ).fetchall()
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
    p.add_argument("--url", help="播放地址")
    p.add_argument("--fingerprint")
    p.add_argument("--title", default="")
    p.add_argument("--ffprobe", default="ffprobe")
    p.add_argument(
        "--reclassify-existing",
        action="store_true",
        help="只使用已有ffprobe宽高证据重新计算质量等级",
    )
    args = p.parse_args()
    if args.reclassify_existing:
        print(json.dumps(reclassify_existing_media(args.db), ensure_ascii=False))
        return
    if not args.url or not args.fingerprint:
        p.error("--url 与 --fingerprint 必须同时提供")
    result = probe_and_save(
        args.db, args.fingerprint, args.url, args.title, ffprobe_cmd=args.ffprobe
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
