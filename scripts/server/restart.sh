#!/usr/bin/env bash
# AIDC APIサーバーを再起動する(stop.sh + start.sh)。
# --reloadなしで起動しているため、コード変更を反映するにはこの再起動が必要。

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/stop.sh"
"$SCRIPT_DIR/start.sh"
