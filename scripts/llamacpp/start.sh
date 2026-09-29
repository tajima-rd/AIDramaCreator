#!/usr/bin/env bash
# 生成AI(core/genai/openai_compatible)の検証用に、llama.cppのllama-serverをバックグラウンドで起動する。
# 停止は scripts/llamacpp/stop.sh を使う。
#
# 既定値は開発機(RX 7900 XTX + ROCm、~/Temp/Genai 以下にllama.cppとモデル)に合わせてある。
# 別の環境では以下の環境変数で上書きする:
#   AIDC_LLAMA_SERVER_BIN   llama-serverの実行ファイル
#   AIDC_LLAMA_MODEL        本体モデル(gguf)
#   AIDC_LLAMA_DRAFT_MODEL  MTPの下書きモデル(gguf)。空にするかファイルが無ければ使わない
#   AIDC_LLAMA_GPU_LAYERS   GPUに載せるレイヤー数(99 = 全レイヤー)
#   AIDC_LLAMA_CTX_SIZE     コンテキスト長
#   AIDC_LLAMA_HOST / AIDC_LLAMA_PORT
#   AIDC_LLAMA_API_KEY      AIDCの接続先の設定(Project > Preferences)に同じ値を入れる
#   ROCM_PATH               ROCmの所在(存在すればライブラリパスに加える)
#   AIDC_LLAMA_OPEN_BROWSER 1ならllama-serverのWeb UIをブラウザで開く

set -eu

GENAI_DIR="$HOME/Temp/Genai"
AIDC_LLAMA_SERVER_BIN="${AIDC_LLAMA_SERVER_BIN:-$GENAI_DIR/llama.cpp/build/bin/llama-server}"
AIDC_LLAMA_MODEL="${AIDC_LLAMA_MODEL:-$GENAI_DIR/models/Qwen3.8-27B-Q4_0.gguf}"
AIDC_LLAMA_DRAFT_MODEL="${AIDC_LLAMA_DRAFT_MODEL-$GENAI_DIR/models/mtp-Qwen3.8-27B-Q4_0.gguf}"
AIDC_LLAMA_GPU_LAYERS="${AIDC_LLAMA_GPU_LAYERS:-99}"
AIDC_LLAMA_CTX_SIZE="${AIDC_LLAMA_CTX_SIZE:-49152}"
AIDC_LLAMA_HOST="${AIDC_LLAMA_HOST:-127.0.0.1}"
AIDC_LLAMA_PORT="${AIDC_LLAMA_PORT:-8080}"
AIDC_LLAMA_API_KEY="${AIDC_LLAMA_API_KEY:-1234}"
AIDC_LLAMA_OPEN_BROWSER="${AIDC_LLAMA_OPEN_BROWSER:-1}"
ROCM_PATH="${ROCM_PATH:-/opt/rocm-7.2.0}"
PID_FILE="/tmp/llama-server.pid"

# RX 7900 XTX は gfx1100 としてネイティブ対応しているため HSA_OVERRIDE_GFX_VERSION は不要
if [ -d "$ROCM_PATH" ]; then
  export ROCM_PATH
  export PATH="$ROCM_PATH/bin:$PATH"
  export LD_LIBRARY_PATH="$ROCM_PATH/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

if [ ! -x "$AIDC_LLAMA_SERVER_BIN" ]; then
  echo "エラー: $AIDC_LLAMA_SERVER_BIN が見つかりません。ビルドを確認するか AIDC_LLAMA_SERVER_BIN を指定してください。" >&2
  exit 1
fi

if [ ! -f "$AIDC_LLAMA_MODEL" ]; then
  echo "エラー: 本体モデルが見つかりません: $AIDC_LLAMA_MODEL(AIDC_LLAMA_MODEL で指定できます)" >&2
  exit 1
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "既にllama-serverが起動しています (PID: $(cat "$PID_FILE"))。停止するには scripts/llamacpp/stop.sh を実行してください。"
  exit 0
fi

# MTPを使わない単体モデル(例: Qwen3-Coder-Next-Q4_K_M.gguf、48GBでVRAM 24GBに載らない)の場合は
# AIDC_LLAMA_DRAFT_MODEL= を空にし、AIDC_LLAMA_GPU_LAYERS を下げること
draft_args=()
if [ -n "$AIDC_LLAMA_DRAFT_MODEL" ] && [ -f "$AIDC_LLAMA_DRAFT_MODEL" ]; then
  draft_args=(-md "$AIDC_LLAMA_DRAFT_MODEL" -ngld 99)
fi

"$AIDC_LLAMA_SERVER_BIN" \
  -m "$AIDC_LLAMA_MODEL" \
  "${draft_args[@]}" \
  -ngl "$AIDC_LLAMA_GPU_LAYERS" \
  -fa on \
  -np 1 \
  -c "$AIDC_LLAMA_CTX_SIZE" \
  -ctk q8_0 -ctv q8_0 \
  --reasoning-budget 8192 \
  --reasoning-budget-message "Okay, I have thought enough. Now I will write the final answer." \
  -n 16384 \
  --top-k 20 --min-p 0 \
  --host "$AIDC_LLAMA_HOST" \
  --port "$AIDC_LLAMA_PORT" \
  --api-key "$AIDC_LLAMA_API_KEY" &
echo $! > "$PID_FILE"

if [ "$AIDC_LLAMA_OPEN_BROWSER" = "1" ]; then
  (sleep 5 && xdg-open "http://$AIDC_LLAMA_HOST:$AIDC_LLAMA_PORT" > /dev/null 2>&1) &
fi

echo "llama-serverを起動しました (PID: $(cat "$PID_FILE"))"
echo "  URL: http://$AIDC_LLAMA_HOST:$AIDC_LLAMA_PORT/v1"
