#!/usr/bin/env python3
"""PipelineRecorder 单元测试：run_id、阶段状态、耗时、report 文件。"""

import json

from ponyo_source_manager import scheduler


def test_pipeline_recorder_records_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "REPORT_DIR", tmp_path)

    rec = scheduler.PipelineRecorder("run-001", "full", "morning", "/db/sources.db")
    rec.begin("discover")
    rec.finish("discover", 0)
    rec.begin("scorer")
    rec.finish("scorer", 1, error="boom")

    report = rec.write_report()

    assert report["run_id"] == "run-001"
    assert report["phase"] == "full"
    assert report["timeslot"] == "morning"
    assert report["summary"] == {"total": 2, "ok": 1, "failed": 1}
    stages = report["stages"]
    assert stages[0]["name"] == "discover"
    assert stages[0]["status"] == "ok"
    assert stages[0]["returncode"] == 0
    assert stages[0]["duration_ms"] is not None
    assert stages[1]["name"] == "scorer"
    assert stages[1]["status"] == "failed"
    assert stages[1]["error"] == "boom"

    # report 文件可读且结构一致
    saved = json.loads((tmp_path / "pipeline-run-run-001.json").read_text())
    assert saved["run_id"] == "run-001"
    assert saved["summary"] == report["summary"]


def test_run_subprocess_does_not_abort_on_failure(tmp_path, monkeypatch):
    """失败阶段不中断流水线（修复 materialize 失败导致 publish 中断的问题）。"""
    import subprocess as _sp

    class FakeProc:
        returncode = 1

        def communicate(self, timeout=None):
            return ("", "boom")

    monkeypatch.setattr(_sp, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(scheduler, "REPORT_DIR", tmp_path)

    rec = scheduler.PipelineRecorder("run-002", "full", "night", "/db/x.db")
    # 失败阶段后继续执行后续阶段（不抛异常、不 sys.exit）
    r1 = scheduler._run_subprocess(["x"], "materialize", recorder=rec)
    r2 = scheduler._run_subprocess(["x"], "release", recorder=rec)

    assert r1["returncode"] == 1
    assert r2["returncode"] == 1
    report = rec.write_report()
    assert report["summary"] == {"total": 2, "ok": 0, "failed": 2}
    assert report["stages"][0]["error"] == "boom"
