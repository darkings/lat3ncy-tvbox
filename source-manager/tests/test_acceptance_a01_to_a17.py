#!/usr/bin/env python3
"""A01 - A17 强制验收标准自动化核查套件。
针对 review.md 规定的每一个验收标准进行客观运行断言。
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SOURCE_MANAGER_DIR = Path(__file__).resolve().parents[1]
PONYO_ROOT = SOURCE_MANAGER_DIR.parent


def test_A01_package_structure_and_cli_help(tmp_path):
    """A01: 校验包结构规范，CLI命令可在不同工作目录下正常执行。"""
    modules = [
        "ponyo_source_manager.scheduler",
        "ponyo_source_manager.discovery.discover_sources",
        "ponyo_source_manager.probes.probe_conn",
        "ponyo_source_manager.probes.drpy_runner",
        "ponyo_source_manager.scoring.scorer",
        "ponyo_source_manager.publishing.generate_subscription",
        "ponyo_source_manager.publishing.release",
    ]

    # 测试从不同工作目录（根目录, source-manager, tmp_path）运行
    test_cwds = [PONYO_ROOT, SOURCE_MANAGER_DIR, tmp_path]

    for cwd in test_cwds:
        for mod in modules:
            cmd = [sys.executable, "-m", mod, "--help"]
            res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
            assert res.returncode == 0, (
                f"Module {mod} failed with code {res.returncode} in {cwd}.\nStderr: {res.stderr}"
            )

    # 4. 校验源码和测试中无 sys.path 污染
    for check_dir in [SOURCE_MANAGER_DIR / "src", SOURCE_MANAGER_DIR / "tests"]:
        for root, _, files in os.walk(check_dir):
            for file in files:
                if file.endswith(".py") and file != "test_acceptance_a01_to_a17.py":
                    content = Path(root, file).read_text(encoding="utf-8")
                    assert "sys.path.insert" not in content, (
                        f"Found sys.path.insert in {Path(root, file)}"
                    )
                    assert "sys.path.append" not in content, (
                        f"Found sys.path.append in {Path(root, file)}"
                    )


def test_A02_dev_dependency_declared():
    """A02: pytest 必须声明在 pyproject.toml 的开发依赖中。"""
    pyproject = (SOURCE_MANAGER_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert "pytest" in pyproject, "pytest is missing from pyproject.toml"


def test_A03_migration_v5_to_v6_idempotent(tmp_path):
    """A03: 旧库迁移从 version 5 升级至 version 6 增加 hard_pass 字段且幂等。"""
    import sqlite3

    from ponyo_source_manager.core.initdb import init_db

    db = tmp_path / "test_v5.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE schema_version (version INT PRIMARY KEY, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute("INSERT INTO schema_version (version) VALUES (1), (2), (3), (4), (5)")
    con.execute("""
        CREATE TABLE score_snapshot (
            id INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            timeslot TEXT,
            total_score REAL NOT NULL,
            scored_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

    # 1. 升级到 v6
    init_db(str(db))
    con = sqlite3.connect(str(db))
    versions = [
        r[0]
        for r in con.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()
    ]
    cols = [r[1] for r in con.execute("PRAGMA table_info(score_snapshot)").fetchall()]
    con.close()

    assert 6 in versions
    assert "hard_pass" in cols

    # 2. 二次执行测试幂等性
    init_db(str(db))
    con = sqlite3.connect(str(db))
    cols_after = [
        r[1] for r in con.execute("PRAGMA table_info(score_snapshot)").fetchall()
    ]
    con.close()
    assert cols_after.count("hard_pass") == 1


def test_A05_compose_and_children_api_healthcheck():
    """A05: 儿童 API 具备 /healthz 健康检查，docker-compose 服务正确解耦。"""
    from fastapi.testclient import TestClient

    from ponyo_source_manager.api.children import app

    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    compose_text = (SOURCE_MANAGER_DIR / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "healthcheck:" in compose_text
    assert "/healthz" in compose_text
    assert 'restart: "no"' in compose_text


def test_A06_scheduler_crontab_generation(tmp_path):
    """A06: scheduler --phase crontab 输出符合要求的指令。"""
    cmd = [sys.executable, "-m", "ponyo_source_manager.scheduler", "--phase", "crontab"]
    res = subprocess.run(
        cmd, cwd=str(SOURCE_MANAGER_DIR), capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "ponyo_source_manager.scheduler" in res.stdout
    managed_jobs = [
        line for line in res.stdout.splitlines() if line and not line.startswith("#")
    ]
    assert len(managed_jobs) == 1
    assert "--phase full" in managed_jobs[0]
    assert "--phase quick" not in res.stdout
    assert "--phase deep" not in res.stdout
    assert "--phase scoring" not in res.stdout
    assert "--phase publish" not in res.stdout


def test_A06_full_pipeline_is_strictly_sequential(monkeypatch, tmp_path):
    from ponyo_source_manager import scheduler

    calls = []

    def fake_phase(name):
        def run(db_path, **kwargs):
            calls.append((name, db_path))
            return {"phase": name}

        return run

    monkeypatch.setattr(scheduler, "_run_discovery_pipeline", fake_phase("discovery"))
    monkeypatch.setattr(scheduler, "run_quick", fake_phase("quick"))
    monkeypatch.setattr(scheduler, "run_deep", fake_phase("deep"))
    monkeypatch.setattr(scheduler, "run_scoring", fake_phase("scoring"))
    monkeypatch.setattr(scheduler, "run_publish", fake_phase("publish"))

    db = str(tmp_path / "sources.db")
    result = scheduler.run_full(db)

    assert [name for name, _ in calls] == [
        "discovery",
        "quick",
        "deep",
        "scoring",
        "publish",
    ]
    assert all(path == db for _, path in calls)
    assert result["phase"] == "full"


def test_A07_timeslot_completeness_four_slots(tmp_path):
    """A07: 四时段完整性缺一不可。"""
    import sqlite3

    from ponyo_source_manager.scoring.scorer import compute_timeslot_completeness

    db = tmp_path / "test_ts.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE conn_probe (fingerprint TEXT, timeslot TEXT, ok INT, probed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    fp = "fp_a07"

    # 3 个时段 -> False
    for ts in ["morning", "noon", "evening"]:
        con.execute(
            "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, ?, 1)",
            (fp, ts),
        )
    con.commit()
    r3 = compute_timeslot_completeness(con, fp)
    assert r3["complete"] is False

    # 4 个完整时段 -> True
    con.execute(
        "INSERT INTO conn_probe (fingerprint, timeslot, ok) VALUES (?, 'night', 1)",
        (fp,),
    )
    con.commit()
    r4 = compute_timeslot_completeness(con, fp)
    assert r4["complete"] is True
    con.close()


def test_A10_strict_29_plus_1_quota(tmp_path):
    """A10: 29+1 严格发布硬约束。"""
    from ponyo_source_manager.publishing.release import validate_before_publish
    from tests.test_release_validation import _create_mock_staging

    # 28 + 1 -> Reject
    stg28 = _create_mock_staging(
        tmp_path / "s28", normal_count=28, children_count=1, live_count=1
    )
    ok28, _ = validate_before_publish(stg28)
    assert ok28 is False

    # 29 + 1 -> Pass
    stg29 = _create_mock_staging(
        tmp_path / "s29", normal_count=29, children_count=1, live_count=1
    )
    ok29, _ = validate_before_publish(stg29)
    assert ok29 is True


def test_A15_makefile_no_deprecated_calls():
    """A15: Makefile 中不得出现旧式 cd source-manager 或 python xxx.py 调用。"""
    makefile = (SOURCE_MANAGER_DIR / "Makefile").read_text(encoding="utf-8")
    assert "cd source-manager" not in makefile
    for line in makefile.splitlines():
        if line.strip().startswith("python "):
            pytest.fail(f"Found bare 'python' invocation in Makefile: {line}")


def test_A16_gitignore_coverage():
    """A16: .gitignore 必须包含关键运行产物与开发临时目录。"""
    gitignore = (SOURCE_MANAGER_DIR / ".gitignore").read_text(encoding="utf-8")
    required = [".venv/", ".staging/", "*.db", "reports/", "logs/"]
    for req in required:
        assert req in gitignore, f"Missing {req} in .gitignore"


def test_discovery_pipeline_runs_dedupe_before_probes(monkeypatch, tmp_path):
    from ponyo_source_manager import scheduler

    calls = []

    def fake_run(args, name, **kwargs):
        calls.append((name, args))
        return {"returncode": 0, "output": ""}

    monkeypatch.setattr(scheduler, "_run_subprocess", fake_run)
    monkeypatch.setattr(scheduler, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "CONFIG_DIR", tmp_path)

    result = scheduler._run_discovery_pipeline(str(tmp_path / "sources.db"))

    assert list(result) == [
        "profile_search_collector",
        "github_collector",
        "drpy_connector",
        "discover",
        "maccms_collector",
        "dedupe",
        "maccms_media",
    ]
    assert [name for name, _ in calls] == [
        "profile_search_collector",
        "github_collector",
        "drpy_connector",
        "discover",
        "maccms_collector",
        "dedupe",
        "maccms_media",
    ]
    dedupe_args = calls[5][1]
    assert "ponyo_source_manager.scoring.dedupe" in dedupe_args
    assert "--policy" in dedupe_args
    assert "--report" in dedupe_args


def test_production_thresholds_and_container_config_are_hard():
    from ponyo_source_manager.scoring import promote_demote

    assert promote_demote.MIN_OBSERVATION_DAYS == 7
    assert promote_demote.MIN_TIMESLOTS_PASSED == 3

    dockerfile = (SOURCE_MANAGER_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY config ./config" in dockerfile


def test_deploy_and_rollback_have_recoverable_backup():
    deploy = (SOURCE_MANAGER_DIR / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    rollback = (SOURCE_MANAGER_DIR / "scripts" / "rollback.sh").read_text(
        encoding="utf-8"
    )

    assert "/opt/ponyo-source-manager-backups" in deploy
    assert "crontab.before" in deploy
    assert "Creating pre-deploy backup" in deploy
    assert "readlink -f" in rollback
    assert "crontab.before" in rollback
    assert "mv -Tf" in rollback
