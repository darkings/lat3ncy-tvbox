#!/usr/bin/env python3
"""源级公平时段覆盖调度器（方案A）。

背景
----
原 probe_conn 的增量窗口以「URL 在 24h 内是否成功」为跳过依据，
而四个时段（morning/noon/evening/night）的 cron 间隔仅 3-9h，
全部小于 24h 窗口。这导致：

  * evening 距同名前次运行恰好 24h，每轮全量重探（约 4000 URL）；
  * morning/noon/night 距前一时段仅 3-9h，绝大多数 URL 被跳过，
    只探测 hash%4 分片的 1/4（约 900 URL）；
  * 结果：evening 吞占约 80% 探测预算，其他时段覆盖严重不足；
  * 实测 7 天内 4371 个源只覆盖 1 个时段，无法满足
    scorer 的 MIN_SLOTS_REQUIRED=3，hard_pass 恒为 0。

本模块改为「以源（fingerprint）为调度单位」，按覆盖缺口分配预算：

  P0 当前时段未覆盖 且 总覆盖 < 3   -> 补缺口（最高优先）
  P1 当前时段未覆盖 且 总覆盖 >= 3  -> 冲 full_coverage
  P2 当前时段已覆盖 且 总覆盖 < 3   -> 低频复测
  P3 当前时段已覆盖 且 总覆盖 >= 3  -> 最低频

评分口径保持一致：与 scorer.compute_timeslot_completeness 相同，
同一 (fingerprint, timeslot, probed_at) 批次 MIN(ok)=1 才算该时段达标。
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

# 四个时段，顺序与 cron 执行顺序一致
SLOTS = ("morning", "noon", "evening", "night")

# 与 scorer.MIN_SLOTS_REQUIRED 保持一致，不得降低
MIN_SLOTS_REQUIRED = 3

# 覆盖统计窗口（天），与 scorer 默认 days=7 一致
COVERAGE_WINDOW_DAYS = 7

# 优先级桶编号（数字越小越优先）
PRIO_FILL_GAP = 0      # 当前时段未覆盖 且 总覆盖 < 3
PRIO_FULL_COVERAGE = 1  # 当前时段未覆盖 且 总覆盖 >= 3
PRIO_RETEST_LOW = 2     # 当前时段已覆盖 且 总覆盖 < 3
PRIO_RETEST_HIGH = 3    # 当前时段已覆盖 且 总覆盖 >= 3


def load_coverage(
    con: sqlite3.Connection,
    *,
    days: int = COVERAGE_WINDOW_DAYS,
) -> dict[str, set[str]]:
    """读取每个源近 N 天已成功覆盖的时段集合。

    口径与 scorer.compute_timeslot_completeness 完全一致：
    按 (fingerprint, timeslot, probed_at) 分组，批次内 MIN(ok)=1 才算达标。
    这样调度目标与评分目标严格对齐，避免「调度认为覆盖了、评分不认」。
    """
    rows = con.execute(
        "SELECT fingerprint, timeslot, probed_at, MIN(ok) AS batch_ok "
        "FROM conn_probe WHERE probed_at >= datetime('now', ?) "
        "GROUP BY fingerprint, timeslot, probed_at",
        (f"-{days} days",),
    ).fetchall()

    covered: dict[str, set[str]] = defaultdict(set)
    for fp, slot, _probed_at, batch_ok in rows:
        if batch_ok == 1 and slot:
            covered[fp].add(slot)
    return covered


def classify_priority(
    covered_slots: set[str],
    timeslot: str,
) -> int:
    """判定单个源在本轮的优先级桶。"""
    n_covered = len(covered_slots)
    has_current = timeslot in covered_slots

    if not has_current and n_covered < MIN_SLOTS_REQUIRED:
        return PRIO_FILL_GAP
    if not has_current and n_covered >= MIN_SLOTS_REQUIRED:
        return PRIO_FULL_COVERAGE
    if has_current and n_covered < MIN_SLOTS_REQUIRED:
        return PRIO_RETEST_LOW
    return PRIO_RETEST_HIGH


def plan_round(
    covered: dict[str, set[str]],
    all_fingerprints: list[str],
    timeslot: str,
    *,
    budget: int,
) -> dict:
    """为本轮挑选要探测的源。

    参数
    ----
    covered : 每源已覆盖时段集合（load_coverage 的返回值）
    all_fingerprints : 全部待调度源
    timeslot : 当前时段
    budget : 本轮最多探测多少个源（按源计数，非 URL）

    返回
    ----
    dict，含 selected（选中的源列表）与各桶规模，便于报告与诊断。
    """
    buckets: dict[int, list[str]] = defaultdict(list)
    for fp in all_fingerprints:
        prio = classify_priority(covered.get(fp, set()), timeslot)
        buckets[prio].append(fp)

    selected: list[str] = []
    for prio in sorted(buckets):
        for fp in buckets[prio]:
            if len(selected) >= budget:
                break
            selected.append(fp)
        if len(selected) >= budget:
            break

    return {
        "timeslot": timeslot,
        "budget": budget,
        "selected": selected,
        "bucket_sizes": {k: len(v) for k, v in sorted(buckets.items())},
        "selected_by_bucket": {
            k: sum(1 for fp in selected if classify_priority(
                covered.get(fp, set()), timeslot) == k)
            for k in sorted(buckets)
        },
    }


def coverage_distribution(
    covered: dict[str, set[str]],
    all_fingerprints: list[str],
) -> dict[int, int]:
    """统计覆盖时段数分布，用于报告与回归验证。"""
    dist: dict[int, int] = defaultdict(int)
    for fp in all_fingerprints:
        dist[len(covered.get(fp, set()))] += 1
    return dict(sorted(dist.items()))
