#!/usr/bin/env bash
# 在 SLURM 计算节点后台启动 mineru-api（供 parse_batch / MinerU CLI --api-url 使用）。
# 由 submit_parse*.slurm 在 source .env.hpc 之后调用；勿在登录节点长时间运行。
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
API_DIR="${REPO_ROOT}/apps/api"
ENV_FILE="${ENV_FILE:-${API_DIR}/.env.hpc}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

MINERU_MODE_VAL="$(printf '%s' "${MINERU_MODE:-cli}" | tr '[:upper:]' '[:lower:]')"
if [[ "${MINERU_MODE_VAL}" == "cloud" ]]; then
  echo "MINERU_MODE=cloud，跳过 mineru-api"
  exit 0
fi

MINERU_CLI_VAL="${MINERU_CLI:-mineru}"
if [[ "${MINERU_CLI_VAL}" != /* ]]; then
  MINERU_CLI_VAL="${API_DIR}/.venv/bin/${MINERU_CLI_VAL}"
fi
if [[ ! -x "${MINERU_CLI_VAL}" ]]; then
  echo "找不到 MinerU: ${MINERU_CLI_VAL}（请先 bash scripts/hpc/swu_pip_install_mineru.sh）" >&2
  exit 1
fi

API_BIN="$(dirname "${MINERU_CLI_VAL}")/mineru-api"
if [[ ! -x "${API_BIN}" ]]; then
  echo "缺少 mineru-api: ${API_BIN}" >&2
  exit 1
fi

HOST="${MINERU_API_BIND:-127.0.0.1}"
PORT="${MINERU_API_PORT:-8001}"
export MINERU_API_URL="${MINERU_API_URL:-http://${HOST}:${PORT}}"

if curl -sf "${MINERU_API_URL}/docs" >/dev/null 2>&1 || curl -sf "${MINERU_API_URL}/" >/dev/null 2>&1; then
  echo "mineru-api 已在运行: ${MINERU_API_URL}"
  exit 0
fi

LOG="${MINERU_API_LOG:-${HOME}/zos_mineru_api.log}"
echo "启动 mineru-api → ${MINERU_API_URL} 日志 ${LOG}"
nohup "${API_BIN}" --host "${HOST}" --port "${PORT}" >>"${LOG}" 2>&1 &
apid=$!

for _ in $(seq 1 120); do
  if curl -sf "${MINERU_API_URL}/docs" >/dev/null 2>&1 || curl -sf "${MINERU_API_URL}/" >/dev/null 2>&1; then
    echo "mineru-api ready pid=${apid}"
    exit 0
  fi
  sleep 2
done

echo "mineru-api 启动超时，见 ${LOG}" >&2
exit 1
