#!/usr/bin/env bash
# 随 pnpm dev / npm run dev 启动 mineru-api；与 apps/api/.env 中 MINERU_CLI、MINERU_API_URL 对齐。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/apps/api/.env"

get_env_val() {
  local key="$1"
  local file="$2"
  [[ -f "$file" ]] || return 1
  local line
  line="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -1)" || return 1
  local val="${line#*=}"
  val="${val%$'\r'}"
  val="${val#\"}"
  val="${val%\"}"
  val="${val#\'}"
  val="${val%\'}"
  printf '%s' "$val"
}

MINERU_CLI_VAL="${MINERU_CLI:-}"
if [[ -z "$MINERU_CLI_VAL" ]]; then
  MINERU_CLI_VAL="$(get_env_val MINERU_CLI "$ENV_FILE" 2>/dev/null || true)"
fi
MINERU_CLI_VAL="${MINERU_CLI_VAL:-mineru}"

resolve_mineru() {
  local c="$1"
  if [[ "$c" = /* ]] && [[ -x "$c" ]]; then
    printf '%s' "$c"
    return 0
  fi
  if command -v "$c" >/dev/null 2>&1; then
    command -v "$c"
    return 0
  fi
  return 1
}

MINERU_PATH="$(resolve_mineru "$MINERU_CLI_VAL" || true)"
if [[ -z "${MINERU_PATH:-}" ]]; then
  echo "dev-mineru-api: 找不到 MinerU 可执行文件（请在 apps/api/.env 设置 MINERU_CLI 为 mineru 的绝对路径）: $MINERU_CLI_VAL" >&2
  exit 1
fi

BIN_DIR="$(dirname "$MINERU_PATH")"
API_BIN="$BIN_DIR/mineru-api"
if [[ ! -x "$API_BIN" ]]; then
  echo "dev-mineru-api: 缺少 mineru-api（与 mineru 同目录）: $API_BIN" >&2
  exit 1
fi

MINERU_API_URL_VAL="${MINERU_API_URL:-}"
if [[ -z "$MINERU_API_URL_VAL" ]]; then
  MINERU_API_URL_VAL="$(get_env_val MINERU_API_URL "$ENV_FILE" 2>/dev/null || true)"
fi

HOST="${MINERU_API_BIND:-127.0.0.1}"
PORT="${MINERU_API_PORT:-8001}"
if [[ -n "$MINERU_API_URL_VAL" ]]; then
  if [[ "$MINERU_API_URL_VAL" =~ //([^/:]+):([0-9]+)(/|$|\?) ]]; then
    HOST="${BASH_REMATCH[1]}"
    PORT="${BASH_REMATCH[2]}"
  elif [[ "$MINERU_API_URL_VAL" =~ //([^/:]+)(/|$|\?) ]]; then
    HOST="${BASH_REMATCH[1]}"
  fi
fi

# 解析在 mineru-api 进程内加载权重，须与 apps/api/.env 一致（仅传给 mineru CLI 不够）
for _key in MINERU_MODEL_SOURCE MINERU_TOOLS_CONFIG_JSON; do
  _val="${!_key:-}"
  if [[ -z "$_val" ]]; then
    _val="$(get_env_val "$_key" "$ENV_FILE" 2>/dev/null || true)"
  fi
  if [[ -n "$_val" ]]; then
    export "$_key=$_val"
  fi
done

if [[ -n "${MINERU_MODEL_SOURCE:-}" ]] || [[ -n "${MINERU_TOOLS_CONFIG_JSON:-}" ]]; then
  echo "dev-mineru-api: MINERU_MODEL_SOURCE=${MINERU_MODEL_SOURCE:-<unset>} MINERU_TOOLS_CONFIG_JSON=${MINERU_TOOLS_CONFIG_JSON:-<unset>}" >&2
fi

echo "dev-mineru-api: $API_BIN --host $HOST --port $PORT" >&2
exec "$API_BIN" --host "$HOST" --port "$PORT"
