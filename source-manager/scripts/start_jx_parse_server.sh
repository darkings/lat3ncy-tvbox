#!/bin/bash
# 启动 VIP 解析服务（host 常驻；children-api 通过 172.19.0.1:8001 反向代理）
# 依赖：host .venv 已装 playwright，/opt/ponyo-source-manager/chromium/ 有 chrome-linux/chrome
set -e
cd "$(dirname "$0")/.."
if pgrep -f jx_parse_server.py > /dev/null; then
    echo "jx_parse_server already running (pid $(pgrep -f jx_parse_server.py))"
    exit 0
fi
nohup setsid .venv/bin/python scripts/jx_parse_server.py > /tmp/jx.log 2>&1 < /dev/null &
echo "started pid=$!"
sleep 2
curl -s -m 3 http://127.0.0.1:8001/healthz && echo
