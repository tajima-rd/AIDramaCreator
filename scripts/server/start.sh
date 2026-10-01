#!/usr/bin/env bash
# AIDC APIサーバーをバックグラウンドで起動する。
# 停止は scripts/server/stop.sh を使う。

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

HOST="${AIDC_SERVER_HOST:-127.0.0.1}"
PORT="${AIDC_SERVER_PORT:-8100}"
PID_FILE="$REPO_ROOT/server.pid"
LOG_FILE="$REPO_ROOT/server.log"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "エラー: $PYTHON_BIN が見つかりません。.venv が作成済みか確認してください。" >&2
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "既にサーバーが起動しています (PID: $existing_pid)。停止するには scripts/server/stop.sh を実行してください。"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

nohup "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT" \
  >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "サーバーの起動に失敗しました。ログを確認してください: $LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi

echo "サーバーを起動しました (PID: $(cat "$PID_FILE"))"
echo "  URL : http://$HOST:$PORT/app/"
echo "  ログ: $LOG_FILE"
