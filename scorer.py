#!/usr/bin/env python3
"""综合评分引擎：100 分制，按 PLAN §九 五维度加权。

| 指标               | 权重 |
|---|---:|
| 播放成功率          | 35 |
| 多时段稳定性        | 25 |
| 首帧与读取速度      | 20 |
| 搜索/详情/选集成功率 | 10 |
| 高清比例与内容质量   | 10 |
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

WEIGHTS = {
    "play_success": 35,
    "stability": 25,
    "speed": 20,
    "func": 10,
    "quality": 10,
}

# 硬性准入 (PLAN §九)
HARD_THRESHOLDS = {
    "func_success_rate": 0.90,     # 搜索和详情成功率 ≥ 90%
    "play_success_rate": 0.85,     # 播放成功率 ≥ 85%
    "hd_ratio": 0.80,             # 720p 比例 ≥ 80%
    "max_consecutive_fail": 3,     # 最近三天无连续严重故障
    "max_first_frame_ms": 4000,   # 首帧中位时间 < 4 秒
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den > 0 else 0.0


def compute_play_success(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算播放成功率。"""
    rows = con.execute(
        "SELECT success FROM drpy_test_result "
        "WHERE fingerprint=? AND test_type='playurl' "
        "AND tested_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    total = len(rows)
    ok = sum(r[0] for r in rows)
    return {"rate": _safe_ratio(ok, total), "total": total, "ok": ok}


def compute_stability(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算多时段稳定性：各时段成功率的最小值/平均值。"""
    rows = con.execute(
        "SELECT timeslot, ok FROM conn_probe "
        "WHERE fingerprint=? "
        "AND probed_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    if not rows:
        return {"rate": 0.0, "timeslots": {}}

    slots: dict[str, list[int]] = {}
    for ts, ok in rows:
        slots.setdefault(ts, []).append(ok)

    slot_rates = {ts: _safe_ratio(sum(v), len(v)) for ts, v in slots.items()}
    # 稳定性 = 最差时段成功率 * 0.6 + 平均成功率 * 0.4
    min_rate = min(slot_rates.values()) if slot_rates else 0.0
    avg_rate = sum(slot_rates.values()) / len(slot_rates) if slot_rates else 0.0
    rate = round(min_rate * 0.6 + avg_rate * 0.4, 4)
    return {"rate": rate, "timeslots": slot_rates}


def compute_speed(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算速度得分：基于延迟 P50/P95。"""
    rows = con.execute(
        "SELECT latency_ms FROM conn_probe "
        "WHERE fingerprint=? AND ok=1 "
        "AND probed_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    if not rows:
        return {"rate": 0.0, "p50": None, "p95": None}

    latencies = sorted(r[0] for r in rows if r[0] is not None)
    if not latencies:
        return {"rate": 0.0, "p50": None, "p95": None}

    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    # 将延迟转换为 0-1 得分：<500ms=1.0, >5000ms=0
    rate = max(0, min(1.0, 1.0 - (p50 - 500) / 4500))
    return {"rate": round(rate, 4), "p50": p50, "p95": p95}


def compute_func_success(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算搜索/详情/选集成功率。"""
    rows = con.execute(
        "SELECT test_type, success FROM drpy_test_result "
        "WHERE fingerprint=? AND test_type IN ('search','detail','episode') "
        "AND tested_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    total = len(rows)
    ok = sum(r[1] for r in rows)
    return {"rate": _safe_ratio(ok, total), "total": total, "ok": ok}


def compute_quality(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算高清比例。"""
    rows = con.execute(
        "SELECT quality_tier FROM media_probe "
        "WHERE fingerprint=? AND success=1 "
        "AND probed_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    total = len(rows)
    hd_plus = sum(1 for r in rows if r[0] in ("hd", "fhd", "uhd"))
    fhd_plus = sum(1 for r in rows if r[0] in ("fhd", "uhd"))
    return {
        "rate": _safe_ratio(hd_plus, total),
        "hd_ratio": _safe_ratio(hd_plus, total),
        "fhd_ratio": _safe_ratio(fhd_plus, total),
        "total": total,
    }


def compute_consecutive_fail(con: sqlite3.Connection, fp: str) -> int:
    """计算最近连续失败次数。"""
    rows = con.execute(
        "SELECT ok FROM conn_probe "
        "WHERE fingerprint=? "
        "ORDER BY probed_at DESC LIMIT 20",
        (fp,)).fetchall()
    count = 0
    for r in rows:
        if r[0] == 0:
            count += 1
        else:
            break
    return count


def check_hard_thresholds(metrics: dict) -> tuple[bool, list[str]]:
    """检查硬性准入条件。返回 (通过, 失败原因列表)。"""
    failures = []
    if metrics["func"]["rate"] < HARD_THRESHOLDS["func_success_rate"]:
        failures.append(
            f"功能成功率 {metrics['func']['rate']:.1%} < "
            f"{HARD_THRESHOLDS['func_success_rate']:.0%}")
    if metrics["play"]["rate"] < HARD_THRESHOLDS["play_success_rate"]:
        failures.append(
            f"播放成功率 {metrics['play']['rate']:.1%} < "
            f"{HARD_THRESHOLDS['play_success_rate']:.0%}")
    if metrics["quality"]["hd_ratio"] < HARD_THRESHOLDS["hd_ratio"]:
        failures.append(
            f"高清比例 {metrics['quality']['hd_ratio']:.1%} < "
            f"{HARD_THRESHOLDS['hd_ratio']:.0%}")
    if metrics["consecutive_fail"] >= HARD_THRESHOLDS["max_consecutive_fail"]:
        failures.append(
            f"连续失败 {metrics['consecutive_fail']} >= "
            f"{HARD_THRESHOLDS['max_consecutive_fail']}")
    p50 = metrics["speed"].get("p50")
    if p50 and p50 > HARD_THRESHOLDS["max_first_frame_ms"]:
        failures.append(
            f"首帧中位 {p50}ms > {HARD_THRESHOLDS['max_first_frame_ms']}ms")
    return len(failures) == 0, failures


def score_fingerprint(con: sqlite3.Connection, fp: str,
                      days: int = 7) -> dict:
    """计算单个指纹的综合评分。"""
    play = compute_play_success(con, fp, days)
    stability = compute_stability(con, fp, days)
    speed = compute_speed(con, fp, days)
    func = compute_func_success(con, fp, days)
    quality = compute_quality(con, fp, days)
    consecutive_fail = compute_consecutive_fail(con, fp)

    total = round(
        play["rate"] * WEIGHTS["play_success"]
        + stability["rate"] * WEIGHTS["stability"]
        + speed["rate"] * WEIGHTS["speed"]
        + func["rate"] * WEIGHTS["func"]
        + quality["rate"] * WEIGHTS["quality"],
        2)

    metrics = {
        "play": play, "stability": stability, "speed": speed,
        "func": func, "quality": quality,
        "consecutive_fail": consecutive_fail,
    }
    passed, failures = check_hard_thresholds(metrics)

    return {
        "fingerprint": fp,
        "total_score": total,
        "play_success": round(play["rate"], 4),
        "stability": round(stability["rate"], 4),
        "speed_score": round(speed["rate"], 4),
        "func_score": round(func["rate"], 4),
        "quality_score": round(quality["rate"], 4),
        "p50_ms": speed.get("p50"),
        "p95_ms": speed.get("p95"),
        "consecutive_fail": consecutive_fail,
        "hard_pass": passed,
        "hard_failures": failures,
        "metrics": metrics,
    }


def save_score(con: sqlite3.Connection, score: dict,
               timeslot: str = "daily", now: str | None = None) -> None:
    """将评分快照写入 score_snapshot 表。"""
    now = now or _now()
    con.execute(
        "INSERT INTO score_snapshot"
        "(fingerprint,timeslot,play_success,stability,speed_score,"
        "func_score,quality_score,total_score,p50_ms,p95_ms,"
        "peak_speed_ms,consecutive_fail,scored_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (score["fingerprint"], timeslot,
         score["play_success"], score["stability"],
         score["speed_score"], score["func_score"], score["quality_score"],
         score["total_score"], score["p50_ms"], score["p95_ms"],
         None, score["consecutive_fail"], now))


def run_scoring(db_path: str, *, timeslot: str = "daily",
                report_path: str | None = None, now: str | None = None) -> dict:
    """对所有活跃指纹执行评分。"""
    now = now or _now()
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    fps = [r[0] for r in con.execute(
        "SELECT DISTINCT fingerprint FROM norm_source").fetchall()]

    scores = []
    for fp in fps:
        # 跳过已 deny 的
        state = con.execute(
            "SELECT state FROM list_state WHERE fingerprint=?",
            (fp,)).fetchone()
        if state and state[0] == "deny":
            continue
        s = score_fingerprint(con, fp)
        save_score(con, s, timeslot, now)
        scores.append(s)

    con.commit()

    # 按总分排名
    scores.sort(key=lambda s: s["total_score"], reverse=True)
    summary = {
        "total_scored": len(scores),
        "hard_pass": sum(1 for s in scores if s["hard_pass"]),
        "hard_fail": sum(1 for s in scores if not s["hard_pass"]),
        "top_10": [{"fp": s["fingerprint"][:12], "score": s["total_score"]}
                   for s in scores[:10]],
    }

    if report_path:
        report = {
            "summary": summary, "generated_at": now,
            "scores": [{k: v for k, v in s.items() if k != "metrics"}
                      for s in scores],
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    con.close()
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--timeslot", default="daily")
    p.add_argument("--report", default=str(HERE / "reports" / "scoring-report.json"))
    args = p.parse_args()
    result = run_scoring(args.db, timeslot=args.timeslot, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
