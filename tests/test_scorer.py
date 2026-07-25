#!/usr/bin/env python3
import json
import sqlite3
import pytest
from scorer import score_fingerprint, check_hard_thresholds


def test_check_hard_thresholds():
    metrics_pass = {
        "func": {"rate": 0.95},
        "play": {"rate": 0.90},
        "quality": {"hd_ratio": 0.85},
        "consecutive_fail": 0,
        "speed": {"p50": 1200}
    }
    passed, errs = check_hard_thresholds(metrics_pass)
    assert passed is True
    assert len(errs) == 0

    metrics_fail = {
        "func": {"rate": 0.80},  # < 90%
        "play": {"rate": 0.70},  # < 85%
        "quality": {"hd_ratio": 0.50},
        "consecutive_fail": 4,
        "speed": {"p50": 5000}
    }
    passed, errs = check_hard_thresholds(metrics_fail)
    assert passed is False
    assert len(errs) == 5
