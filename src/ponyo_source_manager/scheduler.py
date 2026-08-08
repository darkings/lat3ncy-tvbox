#!/usr/bin/env python3
"""多时段调度器：编排快速/深度检测任务。
支持文件锁，子进程阻断，并在发布时要求 scoring 成功。

可观测性（计划 B）：
- 每轮生成 run_id。
- 每阶段记录状态、退出码、耗时。
- 任一阶段失败不中断后续阶段，统一写入 pipeline run report。
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import platform
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import (
    CODE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOG_DIR,
    PONYO_ROOT,
    REPORT_DIR,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineRecorder:
    """每轮流水线的阶段状态记录器。"""

    def __init__(self, run_id: str, phase: str, timeslot: str, db_path: str):
        self.run_id = run_id
        self.phase = phase
        self.timeslot = timeslot
        self.db_path = db_path
        self.started_at = _utc_now()
        self.stages: dict[str, dict] = {}
        self._order: list[str] = []

    def begin(self, name: str) -> None:
        self.stages[name] = {
            "name": name,
            "status": "running",
            "started_at": _utc_now(),
            "duration_ms": None,
            "returncode": None,
            "error": None,
        }
        self._order.append(name)

    def finish(self, name: str, returncode: int, error: str | None = None) -> None:
        stage = self.stages.get(name)
        if not stage:
            return
        started = datetime.fromisoformat(stage["started_at"])
        stage["duration_ms"] = int(
            (datetime.now(timezone.utc) - started).total_seconds() * 1000
        )
        stage["status"] = "ok" if returncode == 0 else "failed"
        stage["returncode"] = returncode
        stage["error"] = (error or "")[:500] or None

    def write_report(self) -> dict:
        report = {
            "run_id": self.run_id,
            "phase": self.phase,
            "timeslot": self.timeslot,
            "db_path": self.db_path,
            "started_at": self.started_at,
            "finished_at": _utc_now(),
            "stages": [self.stages[n] for n in self._order],
            "summary": {
                "total": len(self._order),
                "ok": sum(1 for n in self._order if self.stages[n]["status"] == "ok"),
                "failed": sum(
                    1 for n in self._order if self.stages[n]["status"] == "failed"
                ),
            },
        }
        path = REPORT_DIR / f"pipeline-run-{self.run_id}.json"
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report


def load_schedule(path: str | None = None) -> dict:
    p = Path(path) if path else CONFIG_DIR / "schedule.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


_lock_fd = None


def acquire_lock():
    global _lock_fd
    lock_path = DATA_DIR / "scheduler.lock"
    try:
        _lock_fd = open(lock_path, "w")
        if platform.system() == "Windows":
            import msvcrt

            msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[Error] Another scheduler is running.")
        sys.exit(1)


def check_env() -> None:
    """检查必要的运行环境。"""
    missing = []
    import shutil

    if not shutil.which("node"):
        missing.append("Node.js (node)")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe (ffmpeg)")
    if missing:
        print(f"[Error] 缺少必要的依赖环境: {', '.join(missing)}")
        sys.exit(1)


def current_timeslot() -> str:
    hour = datetime.now().hour
    if 6 <= hour < 11:
        return "morning"
    if 11 <= hour < 15:
        return "noon"
    if 15 <= hour < 21:
        return "evening"
    return "night"


# 阶段看门狗：单个流水线阶段超过该时限即杀进程组，防止不可达 IP 拖死整轮。
STAGE_TIMEOUT_SECONDS = 1800.0


def _run_subprocess(
    args,
    name,
    recorder: PipelineRecorder | None = None,
    timeout_seconds: float = STAGE_TIMEOUT_SECONDS,
):
    print(f"Running {name}...")
    if recorder:
        recorder.begin(name)
    started = time.monotonic()
    # start_new_session（POSIX）：阶段超时时可 killpg 清理 node/ffprobe 等后代进程。
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        returncode = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        # 阶段看门狗：超过时限后杀掉整个进程组（含 node/ffprobe 等后代），
        # 防止 scan_security/probe_conn 等阶段被不可达 IP 拖死整条流水线。
        timed_out = True
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass
        stdout, stderr = proc.communicate()
        returncode = -9
        print(f"{name} TIMEOUT after {timeout_seconds}s, killed")
    duration_ms = int((time.monotonic() - started) * 1000)
    error = None
    if timed_out:
        error = f"stage timeout after {int(timeout_seconds)}s; process group killed"
    elif returncode != 0:
        error = (stderr.strip() or stdout.strip())[-500:]
        print(f"{name} failed with code {returncode}:\n{error}")
    if recorder:
        recorder.finish(name, returncode, error)
    print(f"{name} done in {duration_ms}ms (exit {returncode})")
    return {
        "returncode": returncode,
        "output": stdout.strip()[:500],
        "duration_ms": duration_ms,
        "error": error,
    }


def _run_discovery_pipeline(
    db_path: str, recorder: PipelineRecorder | None = None
) -> dict:
    """Discover/import sources, then rebuild dedup groups before probing."""
    results = {}
    results["profile_search_collector"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.profile_search_collector",
            "--db",
            db_path,
        ],
        "profile_search_collector",
        recorder=recorder,
    )
    results["github_collector"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.github_collector",
            "--db",
            db_path,
        ],
        "github_collector",
        recorder=recorder,
    )
    results["drpy_connector"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.drpy_connector",
            "--db",
            db_path,
        ],
        "drpy_connector",
        recorder=recorder,
    )
    results["discover"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.discover_sources",
            "--db",
            db_path,
        ],
        "discover",
        recorder=recorder,
    )
    results["maccms_collector"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.maccms_collector",
            "--db",
            db_path,
        ],
        "maccms_collector",
        recorder=recorder,
    )
    results["dedupe"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.scoring.dedupe",
            "--db",
            db_path,
            "--policy",
            str(CONFIG_DIR / "policy.json"),
            "--report",
            str(REPORT_DIR / "dedupe-report.json"),
        ],
        "dedupe",
        recorder=recorder,
    )
    # MacCMS quick probes expose playback candidates, but only this post-dedupe
    # bridge owns real media/segment/ffprobe evidence keyed by fingerprint.
    results["maccms_media"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.probes.maccms_media",
            "--db",
            db_path,
            "--limit",
            "70",
            "--report",
            str(REPORT_DIR / "maccms-media-report.json"),
        ],
        "maccms_media",
        recorder=recorder,
    )
    return results


def run_quick(
    db_path: str,
    *,
    run_discovery: bool = True,
    recorder: PipelineRecorder | None = None,
) -> dict:
    """快速检测：连通性探测 + 基础响应时间。"""
    results = {}
    timeslot = current_timeslot()

    # 1. 执行源采集/发现
    if run_discovery:
        results.update(_run_discovery_pipeline(db_path, recorder))

    results["probe_conn"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.probes.probe_conn",
            "--db",
            db_path,
            "--timeslot",
            timeslot,
            "--report",
            str(REPORT_DIR / f"conn-{timeslot}.json"),
        ],
        "probe_conn",
        recorder,
    )

    results["scan_security"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.probes.scan_security",
            "--db",
            db_path,
            "--report",
            str(REPORT_DIR / "security-report.json"),
        ],
        "scan_security",
        recorder,
    )

    return {"phase": "quick", "timeslot": timeslot, "results": results}


def run_deep(
    db_path: str,
    *,
    run_discovery: bool = True,
    recorder: PipelineRecorder | None = None,
) -> dict:
    """深度检测：drpy2 功能链测试 + ffprobe 媒体质量抽测。"""
    check_env()
    results = {}

    if run_discovery:
        results.update(_run_discovery_pipeline(db_path, recorder))

    results["drpy_test"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.probes.drpy_runner",
            "--db",
            db_path,
            "--report",
            str(REPORT_DIR / "drpy-test-report.json"),
        ],
        "drpy_test",
        recorder,
    )

    return {"phase": "deep", "results": results}


def run_scoring(db_path: str, recorder: PipelineRecorder | None = None) -> dict:
    """评分 + 晋降级。"""
    results = {}
    timeslot = current_timeslot()

    results["classify_capabilities"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.discovery.classify_capabilities",
            "--db",
            db_path,
            "--report",
            str(REPORT_DIR / "capability-report.json"),
        ],
        "classify_capabilities",
        recorder,
    )

    results["scorer"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.scoring.scorer",
            "--db",
            db_path,
            "--timeslot",
            timeslot,
            "--report",
            str(REPORT_DIR / "scoring-report.json"),
        ],
        "scorer",
        recorder,
    )

    results["promote_demote"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.scoring.promote_demote",
            "--db",
            db_path,
            "--report",
            str(REPORT_DIR / "promotion-report.json"),
        ],
        "promote_demote",
        recorder,
    )

    # 写入成功标记供 publish 检查 (A18 要求包含 run_id 和 db_version)
    marker_data = {
        "timestamp": _utc_now(),
        "run_id": datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "db_version": get_db_version(db_path),
    }
    (DATA_DIR / "scoring_success.marker").write_text(
        json.dumps(marker_data), encoding="utf-8"
    )

    return {"phase": "scoring", "results": results}


def get_db_version(db_path: str) -> int:
    try:
        with sqlite3.connect(db_path) as conn:
            return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    except Exception:
        return 0


def run_publish(db_path: str, recorder: PipelineRecorder | None = None) -> dict:
    """生成订阅与发布。依赖本轮 scoring 成功。"""
    marker = DATA_DIR / "scoring_success.marker"
    if not marker.exists():
        print(
            "[Error] scoring_success.marker not found. Scoring must succeed before publish."
        )
        return {"phase": "publish", "results": {}, "error": "marker missing"}

    # 读取 JSON 并校验
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if "timestamp" not in data or "run_id" not in data or "db_version" not in data:
            print("[Error] scoring_success.marker missing required fields.")
            return {"phase": "publish", "results": {}, "error": "marker invalid"}

        dt = datetime.fromisoformat(data["timestamp"])
        if dt.tzinfo is None:
            print("[Error] scoring_success.marker timestamp must be timezone-aware.")
            return {"phase": "publish", "results": {}, "error": "marker naive"}

        if (datetime.now(timezone.utc) - dt).total_seconds() > 3600 * 24:
            print("[Error] scoring_success.marker is older than 24 hours.")
            marker.unlink()
            return {"phase": "publish", "results": {}, "error": "marker expired"}

        expected_version = get_db_version(db_path)
        if data["db_version"] != expected_version:
            print(
                f"[Error] DB version mismatch. Marker has {data['db_version']}, "
                f"current is {expected_version}."
            )
            return {"phase": "publish", "results": {}, "error": "db version mismatch"}

    except (ValueError, json.JSONDecodeError) as e:
        print(f"[Error] Invalid scoring_success.marker format: {e}")
        marker.unlink(missing_ok=True)
        return {"phase": "publish", "results": {}, "error": f"marker parse: {e}"}
    except Exception as e:
        print(f"[Error] Failed to read scoring_success.marker: {e}")
        return {"phase": "publish", "results": {}, "error": str(e)[:200]}

    results = {}

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    staging_dir = PONYO_ROOT / "subscription" / ".staging" / run_id

    results["children_aggregate"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.publishing.children_aggregate",
            "--db",
            db_path,
        ],
        "children_aggregate",
        recorder,
    )
    results["live_manager"] = _run_subprocess(
        [sys.executable, "-m", "ponyo_source_manager.probes.live", "--db", db_path],
        "live_manager",
        recorder,
    )
    results["materialize_approved_assets"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.publishing.materialize_approved_assets",
            "--db",
            db_path,
        ],
        "materialize_approved_assets",
        recorder,
    )
    results["generate_subscription"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.publishing.generate_subscription",
            "--db",
            db_path,
            "--output",
            str(staging_dir),
        ],
        "generate_subscription",
        recorder,
    )
    results["release"] = _run_subprocess(
        [
            sys.executable,
            "-m",
            "ponyo_source_manager.publishing.release",
            "--staging",
            str(staging_dir),
        ],
        "release",
        recorder,
    )

    if results["release"]["returncode"] == 0:
        # A18: 发布成功后必须消费该标记
        marker.unlink(missing_ok=True)

    return {"phase": "publish", "results": results}


def run_full(db_path: str) -> dict:
    """Run one complete timeslot pipeline under a single scheduler lock.

    Deep probing can take longer than the old fixed 30 minute cron gap.  Keeping
    all phases in one process prevents scoring/publishing from being skipped by
    the overlap lock and guarantees that publish uses the scoring result from
    this exact run.
    """
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    timeslot = current_timeslot()
    recorder = PipelineRecorder(run_id, "full", timeslot, db_path)

    phases = {
        "discovery": _run_discovery_pipeline(db_path, recorder=recorder),
        "quick": run_quick(db_path, run_discovery=False, recorder=recorder),
        "deep": run_deep(db_path, run_discovery=False, recorder=recorder),
        "scoring": run_scoring(db_path, recorder=recorder),
        "publish": run_publish(db_path, recorder=recorder),
    }
    recorder.write_report()
    return {"phase": "full", "timeslot": timeslot, "run_id": run_id, "results": phases}


def generate_crontab(db_path: str, python: str = None) -> str:
    """生成 crontab 条目。"""
    python_exe = python or sys.executable
    drpy_adapter = PONYO_ROOT / "drpy2" / "drpys-http-adapter.js"
    runtime = (
        f"PONYO_ROOT={PONYO_ROOT} CHILDREN_API_URL=https://api.ponyo.fun "
        f"DRPY2_ADAPTER={drpy_adapter} DRPY2_BASE_URL=http://127.0.0.1:5757 "
        f"DRPY2_CONFIG_URL=http://127.0.0.1:5757/config/1?pwd=ponyo-local-drpy "
        f"{python_exe} -m ponyo_source_manager.scheduler"
    )
    base = f"cd {PONYO_ROOT} && {runtime}"
    lines = [
        "# BEGIN PONYO MANAGED",
        f"# Ponyo 源管理定时任务: 每天四个时段 (morning, noon, evening, night) 执行完整流水线",
        f"0 8,13,20,23 * * * {base} --phase full --db {db_path} >> {LOG_DIR}/scheduler.log 2>&1",
        "# END PONYO MANAGED",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument(
        "--phase",
        choices=["quick", "deep", "scoring", "publish", "full", "crontab"],
        required=True,
    )
    args = p.parse_args()

    if args.phase == "crontab":
        print(generate_crontab(args.db))
        return

    acquire_lock()
    if args.phase == "full":
        result = run_full(args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    recorder = PipelineRecorder(run_id, args.phase, current_timeslot(), args.db)
    dispatch = {
        "quick": run_quick,
        "deep": run_deep,
        "scoring": run_scoring,
        "publish": run_publish,
    }
    result = dispatch[args.phase](args.db, recorder)
    recorder.write_report()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
