#!/usr/bin/env bash
# 释放 pnpm dev 占用的端口（macOS / Linux：lsof）。
# 用法：pnpm run kill:dev
#       pnpm run kill:dev -- 8000 3000
set -euo pipefail

PORTS=(8000 3000 8001)
if [[ $# -gt 0 ]]; then
  PORTS=("$@")
fi

killed=0
for port in "${PORTS[@]}"; do
  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "端口 ${port}：空闲"
    continue
  fi
  echo "端口 ${port}：结束进程 ${pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 0.5
  still="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$still" ]]; then
    echo "端口 ${port}：强制结束 ${still//$'\n'/ }"
    # shellcheck disable=SC2086
    kill -9 ${still} 2>/dev/null || true
  fi
  killed=1
done

if [[ "$killed" -eq 0 ]]; then
  echo "未发现监听中的 dev 端口。"
fi
