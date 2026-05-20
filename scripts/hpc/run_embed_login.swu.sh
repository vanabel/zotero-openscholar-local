#!/usr/bin/env bash
# 在 swu3 登录节点运行普通 embedding_json（OpenAI 兼容 HTTP API）。
# 计算节点可能无外网 DNS；GPU 作业负责 chunk/scholar，本脚本只跑 scripts/embed_batch.py。
set -euo pipefail

REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
API="${REPO}/apps/api"
ENV_FILE="${ENV_FILE:-${API}/.env.hpc}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"
: "${BATCH_SIZE:=8}"

export LC_ALL=C LANG=C
unset LANGUAGE 2>/dev/null || true

if [[ -f "${REPO}/scripts/hpc/swu_modules.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO}/scripts/hpc/swu_modules.sh"
fi

cd "${API}"
if [[ ! -d .venv ]]; then
  echo "缺少 ${API}/.venv；请先运行 scripts/hpc/swu_pip_install.sh" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "缺少 ${ENV_FILE}" >&2
  exit 1
fi

export DATA_DIR="${DATA_DIR:-${API}/data}"
export EMBED_PROVIDER="${EMBED_PROVIDER:-openai}"

if [[ "${EMBED_PROVIDER}" != "openai" ]] || [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "embed 需要 EMBED_PROVIDER=openai 与 OPENAI_API_KEY" >&2
  exit 1
fi

.venv/bin/python - <<'PY'
import socket
from urllib.parse import urlparse

from app.config import settings

host = urlparse(settings.openai_api_base).hostname
if not host:
    raise SystemExit("OPENAI_API_BASE 无有效 host")
print("OPENAI_API_BASE host:", host)
socket.getaddrinfo(host, 443)
print("DNS OK")
PY

if [[ -n "${PAPER_IDS}" ]]; then
  COMMON=()
  IFS=',' read -ra _pids <<<"${PAPER_IDS}"
  for _pid in "${_pids[@]}"; do
    COMMON+=(--paper-id "${_pid}")
  done
else
  COMMON=(--all)
  [[ "${MISSING_ONLY}" == "1" ]] && COMMON+=(--missing-only)
fi
[[ "${FORCE}" == "1" ]] && COMMON+=(--force)

echo "=== run embed on login node DATA_DIR=${DATA_DIR} PAPER_IDS=${PAPER_IDS:-<all>} ==="
.venv/bin/python scripts/embed_batch.py "${COMMON[@]}" --batch-size "${BATCH_SIZE}"
