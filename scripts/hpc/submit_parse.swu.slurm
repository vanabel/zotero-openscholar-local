#!/bin/bash
# 西南大学超算：MinerU 批量解析（GPU 节点）
#SBATCH --job-name=zos-parse
#SBATCH --output=zos_parse_%j.log
#SBATCH --error=zos_parse_%j.err
#SBATCH --partition=gpu_4090
#SBATCH --gres=gpu:1
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G

set -euo pipefail

REPO_ROOT_EARLY="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
# shellcheck disable=SC1091
source "${REPO_ROOT_EARLY}/scripts/hpc/swu_modules.sh"

: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${DATA_DIR:=${REPO_ROOT}/apps/api/data}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${RUN_MINERU_API:=0}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"
: "${PAPER_IDS_FILE:=}"

export REPO_ROOT DATA_DIR

cd "${REPO_ROOT}/apps/api"
if [[ ! -d .venv ]]; then
  echo "缺少 .venv：先 bash scripts/hpc/swu_pip_install.sh && swu_pip_install_mineru.sh" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export MINERU_MODE="${MINERU_MODE:-cli}"
export MINERU_CLI="${MINERU_CLI:-${REPO_ROOT}/apps/api/.venv/bin/mineru}"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"
export MINERU_TOOLS_CONFIG_JSON="${MINERU_TOOLS_CONFIG_JSON:-${REPO_ROOT}/apps/api/config/mineru.hpc.json}"
export MINERU_CLI_EXTRA_ARGS="${MINERU_CLI_EXTRA_ARGS:---backend vlm-auto-engine --source local}"
# SWU 计算节点无外网 DNS；本地 MinerU 解析时不要触发低分云端重试。
export PARSE_QUALITY_RETRY_ENABLED="${PARSE_QUALITY_RETRY_ENABLED:-0}"
if [[ "${MINERU_CLI_EXTRA_ARGS}" == *"vlm-auto-engine"* ]] || [[ "${MINERU_CLI_EXTRA_ARGS}" == *"hybrid-auto-engine"* ]]; then
  export MINERU_API_URL=""
  RUN_MINERU_API=0
else
  export MINERU_API_URL="${MINERU_API_URL:-http://127.0.0.1:8001}"
fi

if [[ "${RUN_MINERU_API}" == "1" ]]; then
  bash "${REPO_ROOT}/scripts/hpc/start_mineru_api_hpc.sh"
fi

if [[ -n "${PAPER_IDS}" ]]; then
  COMMON=()
  IFS=',' read -ra _pids <<< "${PAPER_IDS}"
  for _pid in "${_pids[@]}"; do
    COMMON+=(--paper-id "${_pid}")
  done
  COMMON_IDS_COUNT="${#_pids[@]}"
elif [[ -n "${PAPER_IDS_FILE}" ]]; then
  COMMON=()
  COMMON_IDS_COUNT=0
  while IFS= read -r _pid || [[ -n "${_pid}" ]]; do
    [[ -z "${_pid}" ]] && continue
    COMMON+=(--paper-id "${_pid}")
    (( COMMON_IDS_COUNT += 1 ))
  done < "${PAPER_IDS_FILE}"
else
  COMMON=(--all)
  [[ "${MISSING_ONLY}" == "1" ]] && COMMON+=(--missing-only)
  COMMON_IDS_COUNT="all"
fi
[[ "${FORCE}" == "1" ]] && COMMON+=(--force)

echo "=== zos parse (SWU) partition=${SLURM_JOB_PARTITION:-?} DATA_DIR=${DATA_DIR} ==="
if [[ -n "${PAPER_IDS_FILE}" ]]; then
  echo "shard=${PARSE_SHARD_INDEX:-?}/${PARSE_SHARD_COUNT:-?} PAPER_IDS_FILE=${PAPER_IDS_FILE} ids=${COMMON_IDS_COUNT}"
fi

.venv/bin/python scripts/parse_batch.py "${COMMON[@]}"

echo "=== 完成；向量: sbatch scripts/hpc/submit_vectors.swu.slurm ==="
