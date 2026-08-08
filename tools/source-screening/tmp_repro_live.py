#!/usr/bin/env python3
"""复现 live.py probe_live_channel 对四川电信的探测。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "/opt/ponyo-source-manager/src")

from ponyo_source_manager.probes import playback
from ponyo_source_manager.probes.live import probe_live_channel

URL = (
    "http://222.214.208.34:59901/tsfile/live/0001_1.m3u8?key=txiptv&playlive=1&authid=0"
)

print("== playback.verify_playback ==")
r = playback.verify_playback(URL, mode="fast")
print(json.dumps(r, ensure_ascii=False, indent=1)[:800])
