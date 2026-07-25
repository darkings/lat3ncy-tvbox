#!/usr/bin/env python3
"""多时段调度器：编排快速/深度检测任务，对应 PLAN §八。

快速检测：每 6 小时（08:00/13:00/20:00/23:00）
深度检测：每天一次（凌晨 03:00）
评分+晋降级：每天一次（04:00）

本脚本生成 crontab 条目或 systemd timer 配置，
也可直接作为入口运行指定阶段的全部任务。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_schedule(path: str | None = None) -> dict:
    p = Path(path) if path else HERE / "config" / "schedule.json"
    return json.loads(p.read_text(encoding="utf-8"))


def current_timeslot() -> str:
    hour = datetime.now().hour
    if 6 <= hour < 11:
        return "morning"
    if 11 <= hour < 15:
        return "noon"
    if 15 <= hour < 21:
        return "evening"
    return "night"


def run_quick(db_path: str) -> dict:
    """快速检测：连通性探测 + 基础响应时间。"""
    results = {}
    timeslot = current_timeslot()

    # 1. 连通性探测
    r = subprocess.run(
        [sys.executable, str(HERE / "probe_conn.py"),
         "--db", db_path, "--timeslot", timeslot,
         "--report", str(HERE / "reports" / f"conn-{timeslot}.json")],
        capture_output=True, text=True)
    results["probe_conn"] = {
        "returncode": r.returncode,
        "output": r.stdout.strip()[:500],
    }

    # 2. 安全扫描（每次快速检测也做一遍静态扫描）
    r = subprocess.run(
        [sys.executable, str(HERE / "scan_security.py"),
         "--db", db_path,
         "--report", str(HERE / "reports" / "security-report.json")],
        capture_output=True, text=True)
    results["scan_security"] = {
        "returncode": r.returncode,
        "output": r.stdout.strip()[:500],
    }

    return {"phase": "quick", "timeslot": timeslot, "results": results}


def run_deep(db_path: str) -> dict:
    """深度检测：drpy2 功能链测试 + ffprobe 媒体质量抽测。"""
    results = {}

    # 1. drpy2 业务功能测试
    r = subprocess.run(
        [sys.executable, str(HERE / "drpy_runner.py"),
         "--db", db_path,
         "--report", str(HERE / "reports" / "drpy-test-report.json")],
        capture_output=True, text=True)
    results["drpy_test"] = {
        "returncode": r.returncode,
        "output": r.stdout.strip()[:500],
    }

    return {"phase": "deep", "results": results}


def run_scoring(db_path: str) -> dict:
    """评分 + 晋降级。"""
    results = {}
    timeslot = current_timeslot()

    # 1. 综合评分
    r = subprocess.run(
        [sys.executable, str(HERE / "scorer.py"),
         "--db", db_path, "--timeslot", timeslot,
         "--report", str(HERE / "reports" / "scoring-report.json")],
        capture_output=True, text=True)
    results["scorer"] = {
        "returncode": r.returncode,
        "output": r.stdout.strip()[:500],
    }

    # 2. 晋级/淘汰
    r = subprocess.run(
        [sys.executable, str(HERE / "promote_demote.py"),
         "--db", db_path,
         "--report", str(HERE / "reports" / "promotion-report.json")],
        capture_output=True, text=True)
    results["promote_demote"] = {
        "returncode": r.returncode,
        "output": r.stdout.strip()[:500],
    }

    return {"phase": "scoring", "results": results}


def generate_crontab(db_path: str, python: str = "python3") -> str:
    """生成 crontab 条目。"""
    base = f"cd {HERE} && {python}"
    lines = [
        f"# Ponyo 源管理定时任务",
        f"# 快速检测：08:00 / 13:00 / 20:00 / 23:00",
        f"0 8 * * * {base} scheduler.py --phase quick --db {db_path} >> logs/scheduler.log 2>&1",
        f"0 13 * * * {base} scheduler.py --phase quick --db {db_path} >> logs/scheduler.log 2>&1",
        f"0 20 * * * {base} scheduler.py --phase quick --db {db_path} >> logs/scheduler.log 2>&1",
        f"0 23 * * * {base} scheduler.py --phase quick --db {db_path} >> logs/scheduler.log 2>&1",
        f"# 深度检测：每天 03:00",
        f"0 3 * * * {base} scheduler.py --phase deep --db {db_path} >> logs/scheduler.log 2>&1",
        f"# 评分+晋降级：每天 04:00",
        f"0 4 * * * {base} scheduler.py --phase scoring --db {db_path} >> logs/scheduler.log 2>&1",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--phase", choices=["quick", "deep", "scoring", "crontab"],
                   required=True)
    args = p.parse_args()

    if args.phase == "crontab":
        print(generate_crontab(args.db))
        return

    dispatch = {"quick": run_quick, "deep": run_deep, "scoring": run_scoring}
    result = dispatch[args.phase](args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
