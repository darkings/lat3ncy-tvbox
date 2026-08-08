#!/usr/bin/env python3
"""晋级/淘汰引擎：管理源从 candidate → allow → deny 的状态流转。

对应 PLAN §十 精选30的晋级和淘汰。

规则：
- 新源晋级：连续 3 天合格 + 至少 3 个不同时段 + 综合分高于当前正式源最低分
- 正式源淘汰：连续两时段失败 / 三天成功率<80% / 新增高危
- 防抖：每天最多替换 3 个
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_HOME as HERE

MAX_DAILY_CHANGES = 3
MIN_OBSERVATION_DAYS = 7
MIN_TIMESLOTS_PASSED = 3
DEMOTE_CONSECUTIVE_FAIL_TIMESLOTS = 2
DEMOTE_SUCCESS_RATE_THRESHOLD = 0.80
DEMOTE_SUCCESS_RATE_DAYS = 3
ALLOW_QUOTA = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_current_state(con: sqlite3.Connection, fp: str) -> str:
    row = con.execute(
        "SELECT state FROM list_state WHERE fingerprint=?", (fp,)).fetchone()
    return row[0] if row else "candidate"


def get_allow_count(con: sqlite3.Connection) -> int:
    row = con.execute(
        "SELECT COUNT(*) FROM list_state WHERE state='allow'").fetchone()
    return row[0] if row else 0


def get_daily_change_count(con: sqlite3.Connection, today: str) -> int:
    """今天已经执行的晋级/淘汰次数。"""
    row = con.execute(
        "SELECT COUNT(*) FROM promotion_log "
        "WHERE action IN ('promote','demote') AND acted_at >= ?",
        (today,)).fetchone()
    return row[0] if row else 0


def get_latest_scores(con: sqlite3.Connection, fp: str,
                      days: int = 7) -> list[dict]:
    rows = con.execute(
        "SELECT total_score, timeslot, scored_at, hard_pass FROM score_snapshot "
        "WHERE fingerprint=? AND scored_at >= datetime('now', ?) "
        "ORDER BY scored_at DESC",
        (fp, f"-{days} days")).fetchall()
    return [{"score": r[0], "timeslot": r[1], "scored_at": r[2], "hard_pass": r[3]} for r in rows]


def get_observation_days(con: sqlite3.Connection, fp: str) -> int:
    """计算源被观察的天数。"""
    row = con.execute(
        "SELECT MIN(scored_at) FROM score_snapshot WHERE fingerprint=?",
        (fp,)).fetchone()
    if not row or not row[0]:
        return 0
    first = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return max(0, (now - first).days)


def get_distinct_timeslots_passed(con: sqlite3.Connection, fp: str,
                                  days: int = 7) -> int:
    """近 N 天通过的不同连通性探测时段数。"""
    rows = con.execute(
        "SELECT DISTINCT timeslot FROM conn_probe "
        "WHERE fingerprint=? AND ok=1 "
        "AND probed_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    return len(rows)


def get_allow_min_score(con: sqlite3.Connection) -> tuple[float, str]:
    """获取当前正式源的最低分和对应的指纹。"""
    row = con.execute(
        "SELECT MIN(s.total_score), s.fingerprint FROM score_snapshot s "
        "JOIN list_state ls ON s.fingerprint = ls.fingerprint "
        "WHERE ls.state = 'allow' "
        "AND s.scored_at = ("
        "  SELECT MAX(scored_at) FROM score_snapshot "
        "  WHERE fingerprint = s.fingerprint)").fetchone()
    if row and row[0] is not None:
        return row[0], row[1]
    return 0.0, ""


def get_consecutive_timeslot_failures(con: sqlite3.Connection, fp: str) -> int:
    """最近连续失败的时段数。"""
    rows = con.execute(
        "SELECT ok FROM conn_probe "
        "WHERE fingerprint=? ORDER BY probed_at DESC LIMIT 10",
        (fp,)).fetchall()
    count = 0
    for r in rows:
        if r[0] == 0:
            count += 1
        else:
            break
    return count


def get_recent_play_success_rate(con: sqlite3.Connection, fp: str,
                                 days: int = 3) -> float:
    rows = con.execute(
        "SELECT success FROM drpy_test_result "
        "WHERE fingerprint=? AND test_type='playback' "
        "AND tested_at >= datetime('now', ?)",
        (fp, f"-{days} days")).fetchall()
    if not rows:
        return 1.0  # 无数据不淘汰
    return sum(r[0] for r in rows) / len(rows)


def has_high_security_finding(con: sqlite3.Connection, fp: str) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM security_finding "
        "WHERE fingerprint=? AND severity='high'",
        (fp,)).fetchone()
    return (row[0] or 0) > 0


def evaluate_promotion(con: sqlite3.Connection, fp: str) -> dict:
    """评估候选源是否应该晋级。"""
    state = get_current_state(con, fp)
    if state != "candidate":
        return {"action": "hold", "reason": f"state is {state}, not candidate"}

    obs_days = get_observation_days(con, fp)
    if obs_days < MIN_OBSERVATION_DAYS:
        return {"action": "hold",
                "reason": f"观察天数 {obs_days} < {MIN_OBSERVATION_DAYS}"}

    timeslots = get_distinct_timeslots_passed(con, fp)
    if timeslots < MIN_TIMESLOTS_PASSED:
        return {"action": "hold",
                "reason": f"通过时段数 {timeslots} < {MIN_TIMESLOTS_PASSED}"}

    scores = get_latest_scores(con, fp)
    if not scores:
        return {"action": "hold", "reason": "无评分数据"}

    latest_score_obj = scores[0]
    if not latest_score_obj.get("hard_pass"):
        return {"action": "hold", "reason": "最新评分未通过硬性条件"}
        
    latest_score = latest_score_obj["score"]
    min_allow_score, min_allow_fp = get_allow_min_score(con)
    allow_count = get_allow_count(con)

    # 名额未满直接晋级（只要通过硬性条件）
    if allow_count >= ALLOW_QUOTA:
        if latest_score <= min_allow_score:
            return {"action": "hold",
                    "reason": f"分数 {latest_score} ≤ 正式源最低分 {min_allow_score}"}
        else:
            if has_high_security_finding(con, fp):
                return {"action": "hold", "reason": "存在高危安全发现"}
            return {"action": "swap", "target_fp": min_allow_fp,
                    "reason": f"分数 {latest_score} > 最低分 {min_allow_score}"}

    if has_high_security_finding(con, fp):
        return {"action": "hold", "reason": "存在高危安全发现"}

    return {
        "action": "promote",
        "reason": f"观察{obs_days}天, {timeslots}个时段, 分数{latest_score}",
    }


def evaluate_demotion(con: sqlite3.Connection, fp: str) -> dict:
    """评估正式源是否应该淘汰。"""
    state = get_current_state(con, fp)
    if state != "allow":
        return {"action": "hold", "reason": f"state is {state}, not allow"}

    # 高危安全发现 → 立即淘汰
    if has_high_security_finding(con, fp):
        return {"action": "demote", "reason": "新增高危安全发现"}

    # 连续时段失败
    consec = get_consecutive_timeslot_failures(con, fp)
    if consec >= DEMOTE_CONSECUTIVE_FAIL_TIMESLOTS:
        return {"action": "demote",
                "reason": f"连续 {consec} 个时段失败"}

    # 三天播放成功率
    rate = get_recent_play_success_rate(con, fp, DEMOTE_SUCCESS_RATE_DAYS)
    if rate < DEMOTE_SUCCESS_RATE_THRESHOLD:
        return {"action": "demote",
                "reason": f"{DEMOTE_SUCCESS_RATE_DAYS}天播放成功率 {rate:.1%} < "
                          f"{DEMOTE_SUCCESS_RATE_THRESHOLD:.0%}"}

    return {"action": "hold", "reason": "正常运行"}


def _log_action(con: sqlite3.Connection, fp: str, action: str,
                old_state: str, new_state: str, reason: str,
                now: str) -> None:
    con.execute(
        "INSERT INTO promotion_log"
        "(fingerprint,action,old_state,new_state,reason,acted_at)"
        " VALUES(?,?,?,?,?,?)",
        (fp, action, old_state, new_state, reason, now))


def _set_state(con: sqlite3.Connection, fp: str, state: str,
               reason: str, now: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO list_state(fingerprint,state,reason,updated_at)"
        " VALUES(?,?,?,?)", (fp, state, reason, now))


def run_promote_demote(db_path: str, *, report_path: str | None = None,
                       now: str | None = None) -> dict:
    """执行一轮晋级/淘汰评估。"""
    now = now or _now()
    today = now[:10]  # YYYY-MM-DD
    con = sqlite3.connect(str(db_path))

    daily_changes = get_daily_change_count(con, today)
    remaining = MAX_DAILY_CHANGES - daily_changes

    fps = [r[0] for r in con.execute(
        "SELECT DISTINCT fingerprint FROM norm_source").fetchall()]

    actions = []

    # 先评估淘汰（优先处理不健康的正式源）
    for fp in fps:
        if remaining <= 0:
            break
        state = get_current_state(con, fp)
        if state != "allow":
            continue
        result = evaluate_demotion(con, fp)
        if result["action"] == "demote":
            _set_state(con, fp, "candidate", result["reason"], now)
            _log_action(con, fp, "demote", "allow", "candidate",
                       result["reason"], now)
            actions.append({"fp": fp, **result})
            remaining -= 1

    # 再评估晋级
    for fp in fps:
        if remaining <= 0:
            break
        state = get_current_state(con, fp)
        if state != "candidate":
            continue
        result = evaluate_promotion(con, fp)
        if result["action"] == "promote":
            _set_state(con, fp, "allow", result["reason"], now)
            _log_action(con, fp, "promote", "candidate", "allow",
                       result["reason"], now)
            actions.append({"fp": fp, **result})
            remaining -= 1
        elif result["action"] == "swap":
            target_fp = result["target_fp"]
            _set_state(con, target_fp, "candidate", f"被 {fp[:8]} 挤出", now)
            _log_action(con, target_fp, "demote", "allow", "candidate",
                       f"被 {fp[:8]} 挤出", now)
            
            _set_state(con, fp, "allow", result["reason"], now)
            _log_action(con, fp, "promote", "candidate", "allow",
                       result["reason"], now)
            actions.append({"fp": fp, **result})
            remaining -= 1

    con.commit()

    summary = {
        "evaluated": len(fps),
        "promoted": sum(1 for a in actions if a["action"] == "promote"),
        "demoted": sum(1 for a in actions if a["action"] == "demote"),
        "daily_changes_used": MAX_DAILY_CHANGES - remaining,
        "actions": actions,
    }

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps({"summary": summary, "generated_at": now},
                      ensure_ascii=False, indent=2), encoding="utf-8")

    con.close()
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--report",
                   default=str(HERE / "reports" / "promotion-report.json"))
    args = p.parse_args()
    result = run_promote_demote(args.db, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
