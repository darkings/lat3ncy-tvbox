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

from ponyo_source_manager.core.common import PONYO_HOME as HERE

WEIGHTS = {
    "play_success": 35,
    "stability": 25,
    "speed": 20,
    "func": 10,
    "quality": 10,
}

# 硬性准入 (PLAN §九)
HARD_THRESHOLDS = {
    "func_success_rate": 0.90,  # 搜索和详情成功率 ≥ 90%
    "play_success_rate": 0.85,  # 播放成功率 ≥ 85%
    "hd_ratio": 0.80,  # 720p 比例 ≥ 80%
    "max_consecutive_fail": 3,  # 最近三天无连续严重故障
    "max_first_frame_ms": 4000,  # 首帧中位时间 < 4 秒
}

# 纯音频源没有视频流，高清比例门禁不适用
AUDIO_MEDIA_ROLES = {"audio_music"}
_AUDIO_MARKERS = (
    "[听]",
    "┃听",
    "听书",
    "有声",
    "有聲",
    "音乐",
    "音樂",
    "ktv",
    "mv",
    "dj",
)
_SHORT_DRAMA_MARKERS = ("短剧", "短視頻", "短视频", "微短")


def classify_source_media_role(con: sqlite3.Connection, fp: str) -> str:
    """Classify the source content lane by name; mirrors drpy_runner lanes.

    The media_probe.content_type field is unreliable for non-maccms sources
    because maccms_media probes with movie/series keywords only.  Falling back
    to the source name keeps audio and short-drama sources from being held to
    a 720p gate that has no meaning for them.
    """
    row = con.execute(
        "SELECT r.name FROM raw_source r JOIN norm_source n ON n.raw_id=r.id "
        "WHERE n.fingerprint=?",
        (fp,),
    ).fetchone()
    text = (str(row[0]) if row else "").lower()
    if any(m.lower() in text for m in _AUDIO_MARKERS):
        return "audio_music"
    if any(m in text for m in _SHORT_DRAMA_MARKERS):
        return "short_drama"
    return "general"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den > 0 else 0.0


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _logical_test_rows(
    con: sqlite3.Connection,
    fp: str,
    test_types: tuple[str, ...],
    days: int,
) -> list[dict]:
    """Return one canonical row per connector run, test type, and keyword."""
    placeholders = ",".join("?" for _ in test_types)
    rows = con.execute(
        "SELECT id,test_type,COALESCE(keyword,''),success,latency_ms,tested_at,"
        "COALESCE(run_id,''),COALESCE(adapter_version,''),"
        "COALESCE(evidence_json,'') "
        "FROM drpy_test_result WHERE fingerprint=? "
        f"AND test_type IN ({placeholders}) "
        "AND tested_at >= datetime('now', ?) ORDER BY tested_at,id",
        (fp, *test_types, f"-{days} days"),
    ).fetchall()

    known_drpy_runs: set[str] = set()
    completed_drpy_runs: set[str] = set()
    if _table_exists(con, "drpy_run"):
        for run_id, finished_at in con.execute(
            "SELECT run_id,finished_at FROM drpy_run"
        ).fetchall():
            known_drpy_runs.add(str(run_id))
            if finished_at:
                completed_drpy_runs.add(str(run_id))

    canonical: dict[tuple[str, str, str, str], dict] = {}
    for (
        row_id,
        test_type,
        keyword,
        success,
        latency_ms,
        tested_at,
        run_id,
        adapter,
        evidence_json,
    ) in rows:
        run_id = str(run_id or "")
        if run_id in known_drpy_runs and run_id not in completed_drpy_runs:
            continue
        logical_run = run_id or f"legacy:{row_id}"
        evidence: dict = {}
        if evidence_json:
            try:
                evidence = json.loads(evidence_json)
            except (ValueError, TypeError):
                evidence = {}
        # verify_playback 的 latency_ms 是 m3u8 索引+前 3 段的总下载耗时，
        # 而 4000ms 门槛的语义是“首帧”。优先用 evidence 里的 first_frame_ms
        # （真实首帧时间），老数据无该字段时回退 latency_ms。
        speed_ms = evidence.get("first_frame_ms")
        if not isinstance(speed_ms, (int, float)) or speed_ms < 0:
            speed_ms = latency_ms
        key = (logical_run, str(test_type), str(keyword), str(adapter))
        canonical[key] = {
            "run_id": logical_run,
            "test_type": str(test_type),
            "keyword": str(keyword),
            "success": int(bool(success)),
            "latency_ms": latency_ms,
            "speed_ms": int(speed_ms) if speed_ms is not None else None,
            "tested_at": tested_at,
            "adapter_version": str(adapter),
        }
    return list(canonical.values())


def _run_balanced_rate(rows: list[dict]) -> dict:
    """Average per-run rates so retries and profile sizes cannot dominate."""
    by_run: dict[str, list[int]] = {}
    for row in rows:
        by_run.setdefault(row["run_id"], []).append(row["success"])
    run_rates = {
        run_id: _safe_ratio(sum(values), len(values))
        for run_id, values in by_run.items()
    }
    rate = round(sum(run_rates.values()) / len(run_rates), 4) if run_rates else 0.0
    return {
        "rate": rate,
        "total": len(rows),
        "ok": sum(row["success"] for row in rows),
        "runs": len(run_rates),
        "run_rates": run_rates,
        "applicable": bool(rows),
        "adapters": sorted(
            {row["adapter_version"] for row in rows if row["adapter_version"]}
        ),
    }


def compute_play_success(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算播放成功率。"""
    rows = _logical_test_rows(con, fp, ("playback",), days)
    return _run_balanced_rate(rows)


def compute_stability(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算多时段稳定性：各时段成功率的最小值/平均值。"""
    rows = con.execute(
        "SELECT timeslot,probed_at,MIN(ok) FROM conn_probe "
        "WHERE fingerprint=? "
        "AND probed_at >= datetime('now', ?) "
        "GROUP BY timeslot,probed_at",
        (fp, f"-{days} days"),
    ).fetchall()
    if not rows:
        return {"rate": 0.0, "timeslots": {}}

    slots: dict[str, list[int]] = {}
    for ts, _probed_at, ok in rows:
        slots.setdefault(ts, []).append(ok)

    slot_rates = {ts: _safe_ratio(sum(v), len(v)) for ts, v in slots.items()}
    # 稳定性 = 最差时段成功率 * 0.6 + 平均成功率 * 0.4
    min_rate = min(slot_rates.values()) if slot_rates else 0.0
    avg_rate = sum(slot_rates.values()) / len(slot_rates) if slot_rates else 0.0
    rate = round(min_rate * 0.6 + avg_rate * 0.4, 4)
    return {"rate": rate, "timeslots": slot_rates}


def compute_speed(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算速度得分：基于真实播放延迟统计量。

    playback 测试每轮每源只采样 1 次，近 7 天成功样本常只有 1-3 个。直接用
    ``latencies[N//2]`` 会让单次冷启动抖动被当成“中位 P50”把整源判死（例如
    量子资源站历史 [4749, 4644, 1648]ms，标准 p50=4644 判 > 4s 而 fail，
    但源其实可达到 1648ms）。这里按样本数自适应选统计量，4000ms 门槛不变：

    - ≥5 样本：标准中位 P50（样本足够，稳健）。
    - 3-4 样本：截尾均值（去掉最高单次抖动后取均值）。
    - 1-2 样本：取最低值（代表上游可达能力）。
    - 0 样本：返回 None，由 ``check_hard_thresholds`` 触发缺数据门禁。
    """
    logical_rows = _logical_test_rows(con, fp, ("playback",), days)
    rows = [
        row["speed_ms"]
        for row in logical_rows
        if row["success"] == 1 and row["speed_ms"] is not None
    ]
    if not rows:
        return {"rate": 0.0, "p50": None, "p95": None, "samples": 0}

    latencies = sorted(rows)
    n = len(latencies)
    if n >= 5:
        p50 = latencies[n // 2]
    elif n >= 3:
        # 截尾均值：去掉最高单次抖动后取均值
        trimmed = latencies[:-1]
        p50 = int(sum(trimmed) / len(trimmed))
    else:
        # 样本极少：取最低值代表上游可达能力，不被单次冷启动误判
        p50 = latencies[0]
    p95 = latencies[min(n - 1, int(n * 0.95))]

    # 将延迟转换为 0-1 得分：<500ms=1.0, >5000ms=0
    rate = max(0, min(1.0, 1.0 - (p50 - 500) / 4500))
    return {"rate": round(rate, 4), "p50": p50, "p95": p95, "samples": n}


def compute_func_success(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算搜索/详情/选集成功率。"""
    rows = _logical_test_rows(con, fp, ("search", "detail", "episode"), days)
    return _run_balanced_rate(rows)


def compute_quality(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算高清比例和按内容类型的时长门禁。"""
    rows = con.execute(
        "SELECT quality_tier,duration_pass,success FROM media_probe "
        "WHERE fingerprint=? "
        "AND probed_at >= datetime('now', ?)",
        (fp, f"-{days} days"),
    ).fetchall()
    total = len(rows)
    accepted = [r for r in rows if r[1] == 1 and r[2] == 1]
    hd_plus = sum(1 for r in accepted if r[0] in ("hd", "fhd", "uhd"))
    fhd_plus = sum(1 for r in accepted if r[0] in ("fhd", "uhd"))
    duration_ok = sum(1 for r in rows if r[1] == 1)
    return {
        "rate": _safe_ratio(hd_plus, len(accepted)),
        "hd_ratio": _safe_ratio(hd_plus, len(accepted)),
        "fhd_ratio": _safe_ratio(fhd_plus, len(accepted)),
        "total": total,
        "accepted": len(accepted),
        "duration_pass_rate": _safe_ratio(duration_ok, total),
        "duration_total": total,
    }


def compute_consecutive_fail(con: sqlite3.Connection, fp: str) -> int:
    """计算最近连续失败批次数，而不是失败 URL 行数。"""
    rows = con.execute(
        "SELECT batch_ok FROM ("
        "SELECT probed_at,MIN(ok) AS batch_ok FROM conn_probe "
        "WHERE fingerprint=? GROUP BY probed_at "
        "ORDER BY probed_at DESC LIMIT 20)",
        (fp,),
    ).fetchall()
    count = 0
    for r in rows:
        if r[0] == 0:
            count += 1
        else:
            break
    return count


def compute_timeslot_completeness(
    con: sqlite3.Connection, fp: str, days: int = 7
) -> dict:
    rows = con.execute(
        "SELECT timeslot FROM conn_probe "
        "WHERE fingerprint=? AND probed_at >= datetime('now', ?) "
        "GROUP BY timeslot,probed_at HAVING MIN(ok)=1",
        (fp, f"-{days} days"),
    ).fetchall()
    slots = {r[0] for r in rows if r[0]}
    required_slots = {"morning", "noon", "evening", "night"}
    missing = required_slots - slots
    return {
        "complete": len(missing) == 0,
        "slots_found": sorted(list(slots)),
        "missing": sorted(list(missing)),
    }


def compute_dependency_gate(
    con: sqlite3.Connection,
    fp: str,
    now: datetime | None = None,
) -> dict:
    """Unknown, mutable, or failed JAR dependencies are never hard-passable."""
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='dependency_asset_evidence'"
    ).fetchone()
    if not exists:
        return {"complete": True, "jar_total": 0, "statuses": {}}
    rows = con.execute(
        "SELECT validation_status,lower(content_sha256) "
        "FROM dependency_asset_evidence "
        "WHERE fingerprint=? AND asset_type='jar'",
        (fp,),
    ).fetchall()
    statuses: dict[str, int] = {}
    for status, _sha256 in rows:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    total = len(rows)
    approval_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='dependency_asset_approval'"
    ).fetchone()
    approvals = {}
    if approval_table:
        approvals = {
            row[0]: row[1:]
            for row in con.execute(
                "SELECT lower(content_sha256),status,expires_at,"
                "upstream_repo,upstream_commit,upstream_path,git_blob_sha,"
                "provenance_verified_at FROM dependency_asset_approval"
            ).fetchall()
        }
    now = now or datetime.now(timezone.utc)
    passed = 0
    approval_statuses: dict[str, int] = {}
    for validation_status, sha256 in rows:
        if validation_status == "verified":
            passed += 1
            continue
        gate_status = "not_approved"
        approval = approvals.get(sha256 or "")
        if approval:
            status, expires_at, repo, commit, path, blob_sha, verified_at = approval
            gate_status = str(status)
            if status == "approved":
                try:
                    expiry = datetime.fromisoformat(
                        str(expires_at).replace("Z", "+00:00")
                    )
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    identity_complete = bool(
                        repo
                        and "/" in str(repo)
                        and commit
                        and len(str(commit)) == 40
                        and path
                        and blob_sha
                        and len(str(blob_sha)) == 40
                        and verified_at
                    )
                    if expiry > now and identity_complete:
                        gate_status = "approved_valid"
                        if validation_status == "review_required":
                            passed += 1
                    else:
                        gate_status = "expired" if expiry <= now else "invalid_identity"
                except (TypeError, ValueError):
                    gate_status = "invalid_expiry"
        approval_statuses[gate_status] = approval_statuses.get(gate_status, 0) + 1
    return {
        "complete": total == 0 or passed == total,
        "jar_total": total,
        "jar_verified": statuses.get("verified", 0),
        "jar_approved": approval_statuses.get("approved_valid", 0),
        "jar_passed": passed,
        "statuses": statuses,
        "approval_statuses": approval_statuses,
    }


def check_hard_thresholds(
    metrics: dict, *, media_role: str = "general"
) -> tuple[bool, list[str]]:
    """检查硬性准入条件。返回 (通过, 失败原因列表)。"""
    failures = []
    if not metrics["func"].get("applicable", True):
        failures.append("缺少适用连接器的功能验证")
    elif metrics["func"]["rate"] < HARD_THRESHOLDS["func_success_rate"]:
        failures.append(
            f"功能成功率 {metrics['func']['rate']:.1%} < "
            f"{HARD_THRESHOLDS['func_success_rate']:.0%}"
        )
    if not metrics["play"].get("applicable", True):
        failures.append("缺少适用连接器的播放验证")
    elif metrics["play"]["rate"] < HARD_THRESHOLDS["play_success_rate"]:
        failures.append(
            f"播放成功率 {metrics['play']['rate']:.1%} < "
            f"{HARD_THRESHOLDS['play_success_rate']:.0%}"
        )
    if media_role in AUDIO_MEDIA_ROLES:
        # 纯音频源无视频流，720p 高清比例门禁不适用；时长门禁仍由
        # media_quality.evaluate_duration 按 content_type 独立判定。
        pass
    elif metrics["quality"]["hd_ratio"] < HARD_THRESHOLDS["hd_ratio"]:
        failures.append(
            f"高清比例 {metrics['quality']['hd_ratio']:.1%} < "
            f"{HARD_THRESHOLDS['hd_ratio']:.0%}"
        )
    if metrics["quality"].get("duration_total", 0) == 0:
        failures.append("缺少按内容类型的媒体时长检测")
    elif metrics["quality"].get("duration_pass_rate", 0) < 1.0:
        failures.append(
            f"媒体时长通过率 {metrics['quality'].get('duration_pass_rate', 0):.1%}，要求 100%"
        )
    if metrics["consecutive_fail"] >= HARD_THRESHOLDS["max_consecutive_fail"]:
        failures.append(
            f"连续失败 {metrics['consecutive_fail']} >= "
            f"{HARD_THRESHOLDS['max_consecutive_fail']}"
        )
    p50 = metrics["speed"].get("p50")
    if p50 and p50 > HARD_THRESHOLDS["max_first_frame_ms"]:
        failures.append(f"首帧中位 {p50}ms > {HARD_THRESHOLDS['max_first_frame_ms']}ms")
    if not metrics.get("timeslot_completeness", {}).get("complete"):
        failures.append("尚未具备有效的连通性探测数据")
    dependency = metrics.get("dependency", {})
    if not dependency.get("complete", True):
        failures.append(
            "JAR依赖未完成固定哈希与静态验证: "
            + json.dumps(
                {
                    "static": dependency.get("statuses", {}),
                    "approval": dependency.get("approval_statuses", {}),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return len(failures) == 0, failures


def score_fingerprint(con: sqlite3.Connection, fp: str, days: int = 7) -> dict:
    """计算单个指纹的综合评分。"""
    play = compute_play_success(con, fp, days)
    stability = compute_stability(con, fp, days)
    speed = compute_speed(con, fp, days)
    func = compute_func_success(con, fp, days)
    quality = compute_quality(con, fp, days)
    consecutive_fail = compute_consecutive_fail(con, fp)
    ts_complete = compute_timeslot_completeness(con, fp, days)
    dependency = compute_dependency_gate(con, fp)
    media_role = classify_source_media_role(con, fp)

    total = round(
        play["rate"] * WEIGHTS["play_success"]
        + stability["rate"] * WEIGHTS["stability"]
        + speed["rate"] * WEIGHTS["speed"]
        + func["rate"] * WEIGHTS["func"]
        + quality["rate"] * WEIGHTS["quality"],
        2,
    )

    metrics = {
        "play": play,
        "stability": stability,
        "speed": speed,
        "func": func,
        "quality": quality,
        "consecutive_fail": consecutive_fail,
        "timeslot_completeness": ts_complete,
        "dependency": dependency,
    }
    passed, failures = check_hard_thresholds(metrics, media_role=media_role)

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
        "media_role": media_role,
        "evidence": {
            "func_applicable": func.get("applicable", False),
            "func_runs": func.get("runs", 0),
            "play_applicable": play.get("applicable", False),
            "play_runs": play.get("runs", 0),
            "adapters": sorted(
                set(func.get("adapters", [])) | set(play.get("adapters", []))
            ),
        },
        "metrics": metrics,
    }


def save_score(
    con: sqlite3.Connection,
    score: dict,
    timeslot: str = "daily",
    now: str | None = None,
) -> None:
    """将评分快照写入 score_snapshot 表。"""
    now = now or _now()
    con.execute(
        "INSERT INTO score_snapshot"
        "(fingerprint,timeslot,play_success,stability,speed_score,"
        "func_score,quality_score,total_score,p50_ms,p95_ms,"
        "peak_speed_ms,consecutive_fail,hard_pass,scored_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            score["fingerprint"],
            timeslot,
            score["play_success"],
            score["stability"],
            score["speed_score"],
            score["func_score"],
            score["quality_score"],
            score["total_score"],
            score["p50_ms"],
            score["p95_ms"],
            None,
            score["consecutive_fail"],
            1 if score["hard_pass"] else 0,
            now,
        ),
    )


def run_scoring(
    db_path: str,
    *,
    timeslot: str = "daily",
    report_path: str | None = None,
    now: str | None = None,
) -> dict:
    """对所有活跃指纹执行评分。"""
    now = now or _now()
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    fps = [
        r[0]
        for r in con.execute("SELECT DISTINCT fingerprint FROM norm_source").fetchall()
    ]

    scores = []
    for fp in fps:
        # 跳过已 deny 的
        state = con.execute(
            "SELECT state FROM list_state WHERE fingerprint=?", (fp,)
        ).fetchone()
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
        "evidence_coverage": {
            "functional": sum(1 for s in scores if s["evidence"]["func_applicable"]),
            "playback": sum(1 for s in scores if s["evidence"]["play_applicable"]),
            "adapters": sorted(
                {adapter for s in scores for adapter in s["evidence"]["adapters"]}
            ),
        },
        "top_10": [
            {"fp": s["fingerprint"][:12], "score": s["total_score"]}
            for s in scores[:10]
        ],
    }

    if report_path:
        report = {
            "summary": summary,
            "generated_at": now,
            "scores": [{k: v for k, v in s.items() if k != "metrics"} for s in scores],
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
