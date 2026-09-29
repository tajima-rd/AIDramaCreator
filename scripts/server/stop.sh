#!/usr/bin/env bash
# scripts/server/start.sh で起動したAIDC APIサーバーを停止する。

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PID_FILE="$REPO_ROOT/server.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "PIDファイルが見つかりません ($PID_FILE)。サーバーは起動していないようです。"
  exit 0
fi

pid="$(cat "$PID_FILE")"

if ! kill -0 "$pid" 2>/dev/null; then
  echo "PID $pid のプロセスは既に存在しません。PIDファイルを削除します。"
  rm -f "$PID_FILE"
  exit 0
fi

kill "$pid"
for _ in $(seq 1 10); do
  if ! kill -0 "$pid" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

if kill -0 "$pid" 2>/dev/null; then
  echo "通常終了しなかったため強制終了します (PID: $pid)"
  kill -9 "$pid" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "サーバーを停止しました (PID: $pid)"
