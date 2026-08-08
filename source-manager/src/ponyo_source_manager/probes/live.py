#!/usr/bin/env python3
"""直播管理：候选池管理、频道抽测与唯一正式直播源裁决。

对应 PLAN §十五 电视直播。
用户端只维护一个正式直播源。后台维护 3~5 个直播候选，自动测速竞争。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import CODE_DIR, CONFIG_DIR, DATA_DIR, REPORT_DIR
from ponyo_source_manager.probes import playback

# PLAN §十五 5 维度评分权重
WEIGHTS = {
    "channel_validity": 35,  # 主流频道有效率
    "stability": 30,  # 多时段稳定性
    "first_frame": 20,  # 首帧速度
    "clarity": 10,  # 清晰度与码率
    "metadata": 5,  # EPG、台标和频道整理
}

# PLAN §十五 准入条件
HARD_THRESHOLDS = {
    "channel_validity": 0.90,  # 主流频道有效率 ≥ 90%
    "stability": 0.85,  # 多时段成功率 ≥ 85%
    "max_first_frame_ms": 5000,  # 首帧中位时间 < 5s
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_test_channels(path: str | None = None) -> list[str]:
    p = Path(path) if path else CONFIG_DIR / "live_test_channels.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return ["CCTV-1", "CCTV-5", "CCTV-6", "CCTV-8", "CCTV-13", "CCTV-14"]


def probe_live_channel(
    channel_url: str, *, timeout: int = 8, probe_fn=net.probe
) -> dict:
    """测试单个直播频道的 HLS 连通性和首帧响应。"""
    res = playback.verify_playback(channel_url)
    return {
        "url": channel_url,
        "ok": res.get("success", 0),
        "status": 200 if res.get("success") else 500,
        "latency_ms": res.get("latency_ms", 9999),
        "err": res.get("error"),
    }


def parse_live_channels(content: str) -> dict[str, str]:
    """支持解析 TVBox TXT 格式和标准 M3U 格式，提取频道名到 URL 的映射。"""
    mapping = {}
    lines = content.splitlines()
    if content.strip().startswith("#EXTM3U"):
        current_name = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                parts = line.split(",")
                current_name = parts[-1].strip()
            elif line.startswith(("http://", "https://")) and current_name:
                mapping.setdefault(current_name, line)
                mapping.setdefault(_normalize_channel_name(current_name), line)
                current_name = None
    else:
        for line in lines:
            line = line.strip()
            if "," in line and ("http://" in line or "https://" in line):
                parts = line.split(",", 1)
                name = parts[0].strip()
                url = parts[1].strip()
                if name and url.startswith(("http://", "https://")):
                    mapping.setdefault(name, url)
                    mapping.setdefault(_normalize_channel_name(name), url)
    return mapping


def parse_live_channel_routes(content: str) -> dict[str, list[str]]:
    """解析频道到多线路 URL 列表（M3U 连续 URL 行 / TXT 多行同频道）。"""
    routes: dict[str, list[str]] = {}
    lines = content.splitlines()
    if content.strip().startswith("#EXTM3U"):
        current_name = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                parts = line.split(",")
                current_name = parts[-1].strip()
            elif line.startswith(("http://", "https://")) and current_name:
                routes.setdefault(current_name, []).append(line)
                routes.setdefault(_normalize_channel_name(current_name), []).append(
                    line
                )
                # 同一条目可有多条线路（如咪咕），下一条 #EXTINF 才切换频道
    else:
        for line in lines:
            line = line.strip()
            if "," in line and ("http://" in line or "https://" in line):
                parts = line.split(",", 1)
                name = parts[0].strip()
                url = parts[1].strip()
                if name and url.startswith(("http://", "https://")):
                    routes.setdefault(name, []).append(url)
                    routes.setdefault(_normalize_channel_name(name), []).append(url)
    # 去重保序
    return {k: list(dict.fromkeys(v)) for k, v in routes.items()}


def inspect_live_metadata(content: str) -> dict:
    """从 M3U/TXT 头与频道行提取 EPG/台标/回看元数据。"""
    meta = {
        "has_epg": False,
        "epg_url": None,
        "logo_count": 0,
        "catchup": False,
        "channel_count": 0,
    }
    header = content.strip().splitlines()[:5]
    for line in header:
        if 'x-tvg-url="' in line:
            meta["has_epg"] = True
            m = re.search(r'x-tvg-url="([^"]+)"', line)
            if m:
                meta["epg_url"] = m.group(1).split(",")[0]
        if "catchup=" in line:
            meta["catchup"] = True
    meta["channel_count"] = sum(
        1
        for line in content.splitlines()
        if line.strip().startswith("#EXTINF")
        or (
            "," in line
            and not line.strip().startswith("#")
            and ("http://" in line or "https://" in line)
        )
    )
    meta["logo_count"] = sum(1 for line in content.splitlines() if 'tvg-logo="' in line)
    return meta


def _normalize_channel_name(name: str) -> str:
    """Normalize common CCTV/satellite naming variants for deterministic probes."""
    value = re.sub(r"[\s_\-—]+", "", name or "").upper()
    value = value.replace("中央电视台", "CCTV").replace("央视", "CCTV")
    cctv_match = re.match(r"^CCTV0*(\d+)", value)
    if cctv_match:
        return f"CCTV{int(cctv_match.group(1))}"
    value = re.sub(r"(综合|频道|高清|HD|超高清|4K)$", "", value)
    return value


def load_configured_live_candidates(path: str | Path | None = None) -> list[dict]:
    candidate_path = Path(path) if path else CONFIG_DIR / "live_candidates.json"
    if not candidate_path.exists():
        return []
    data = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("live_candidates.json must contain an array")
    return [
        item for item in data if isinstance(item, dict) and item.get("enabled", True)
    ]


def evaluate_live_source(
    source_key: str,
    live_url: str,
    channels: list[str],
    *,
    probe_channel_fn=probe_live_channel,
) -> dict:
    """评估单个直播源表现：实际下载频道列表并测速。"""
    probed_channels = []
    metadata = {
        "has_epg": False,
        "epg_url": None,
        "logo_count": 0,
        "catchup": False,
        "channel_count": 0,
    }

    try:
        content = net.fetch_text(live_url, timeout=10)
        mapping = parse_live_channels(content)
        routes = parse_live_channel_routes(content)
        metadata = inspect_live_metadata(content)
    except Exception as e:
        mapping = {}
        routes = {}

    for ch in channels:
        # 多线路 fallback：同频道多条 URL，第一条失败依次尝试后续线路
        ch_routes = routes.get(ch) or routes.get(_normalize_channel_name(ch))
        target_url = mapping.get(ch) or mapping.get(_normalize_channel_name(ch))
        if ch_routes and not target_url:
            target_url = ch_routes[0]
        if target_url:
            res = None
            for route in ch_routes or [target_url]:
                res = probe_channel_fn(route, timeout=5)
                if res["ok"] == 1:
                    target_url = route
                    break
            if res is None:
                res = probe_channel_fn(target_url, timeout=5)
            probed_channels.append(
                {
                    "channel": ch,
                    "url": target_url,
                    "routes": (ch_routes or [target_url])[:3],
                    "ok": res["ok"],
                    "latency_ms": res["latency_ms"],
                }
            )
        else:
            probed_channels.append(
                {"channel": ch, "url": None, "ok": 0, "latency_ms": 9999}
            )

    valid_count = sum(1 for c in probed_channels if c["ok"] == 1)
    total_count = len(probed_channels)
    validity_rate = valid_count / total_count if total_count > 0 else 0.0

    avg_latency = (
        (sum(c["latency_ms"] for c in probed_channels if c["ok"] == 1) / valid_count)
        if valid_count > 0
        else 9999
    )

    # 计算 100 分制得分
    score_validity = validity_rate * WEIGHTS["channel_validity"]
    score_stability = validity_rate * WEIGHTS["stability"]  # 简化计算
    score_speed = max(0, (5000 - avg_latency) / 5000) * WEIGHTS["first_frame"]
    score_clarity = 8  # 默认高清给 8 分
    # 元数据分：EPG 数据源 + 台标真实存在才给满分（不再无条件默认）
    score_meta = (
        WEIGHTS["metadata"] if metadata["has_epg"] and metadata["logo_count"] > 0 else 0
    )

    total_score = round(
        score_validity + score_stability + score_speed + score_clarity + score_meta, 2
    )
    hard_pass = (validity_rate >= HARD_THRESHOLDS["channel_validity"]) and (
        avg_latency <= HARD_THRESHOLDS["max_first_frame_ms"]
    )

    return {
        "key": source_key,
        "url": live_url,
        "total_score": total_score,
        "validity_rate": round(validity_rate, 4),
        "avg_latency_ms": int(avg_latency),
        "hard_pass": hard_pass,
        "metadata": metadata,
        "probed_channels": probed_channels,
    }


def select_official_live_source(
    db_path: str, *, report_path: str | None = None, now: str | None = None
) -> dict:
    """从数据库中筛选 Live 候选源，竞选唯一正式直播源。"""
    now = now or _now()
    channels = load_test_channels()

    con = sqlite3.connect(str(db_path))
    # 查找分类为 '直播' 的源
    rows = con.execute("""
        SELECT n.fingerprint, r.site_key, r.name, r.api, r.ext
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE (n.category = '直播' OR r.name LIKE '%直播%')
        AND COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()
    con.close()

    evaluations = []
    for candidate in load_configured_live_candidates():
        live_url = str(candidate.get("url", "")).strip()
        if not live_url:
            continue
        key = str(candidate.get("key") or candidate.get("name") or live_url)
        eval_res = evaluate_live_source(key, live_url, channels)
        eval_res["fingerprint"] = None
        eval_res["name"] = str(candidate.get("name") or key)
        eval_res["configured"] = True
        evaluations.append(eval_res)

    for fp, key, name, api, ext in rows:
        live_url = api or ext or ""
        if not live_url:
            continue
        eval_res = evaluate_live_source(key, live_url, channels)
        eval_res["fingerprint"] = fp
        eval_res["name"] = name
        evaluations.append(eval_res)

    evaluations.sort(key=lambda x: (-int(x["hard_pass"]), -x["total_score"]))
    # A13: 全部候选失败时 official 必须为 None，不得选失败候选
    if evaluations and evaluations[0]["hard_pass"]:
        official = evaluations[0]
    else:
        official = None

    summary = {
        "total_candidates": len(evaluations),
        "official_source": official["name"] if official else None,
        "official_key": official["key"] if official else None,
        "official_url": official["url"] if official else None,
        "official_score": official["total_score"] if official else 0,
    }

    if report_path:
        report = {"summary": summary, "generated_at": now, "candidates": evaluations}
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--report", default=str(REPORT_DIR / "live-report.json"))
    args = p.parse_args()
    result = select_official_live_source(args.db, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
