#!/usr/bin/env bash
# scripts/llamacpp/start.sh で起動したllama-serverを停止する。
# PIDファイルが無い場合は、llama-serverという名前のプロセスを探して停止する。

set -eu

PID_FILE="/tmp/llama-server.pid"

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "llama-serverを停止しました (PID: $pid)"
  else
    echo "PID $pid のプロセスは既に存在しません。PIDファイルを削除しました。"
  fi
  exit 0
fi

pids="$(pgrep -x llama-server || true)"
if [ -n "$pids" ]; then
  kill $pids
  echo "llama-serverを停止しました (PID: $pids)"
else
  echo "llama-serverは起動していません"
fi
