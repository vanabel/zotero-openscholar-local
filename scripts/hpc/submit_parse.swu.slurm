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
: "${RUN_MINERU_API:=1}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"

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

if [[ "${RUN_MINERU_API}" == "1" ]]; then
  bash "${REPO_ROOT}/scripts/hpc/start_mineru_api_hpc.sh"
fi

if [[ -n "${PAPER_IDS}" ]]; then
  COMMON=()
  IFS=',' read -ra _pids <<< "${PAPER_IDS}"
  for _pid in "${_pids[@]}"; do
    COMMON+=(--paper-id "${_pid}")
  done
else
  COMMON=(--all)
  [[ "${MISSING_ONLY}" == "1" ]] && COMMON+=(--missing-only)
fi
[[ "${FORCE}" == "1" ]] && COMMON+=(--force)

echo "=== zos parse (SWU) partition=${SLURM_JOB_PARTITION:-?} DATA_DIR=${DATA_DIR} ==="

.venv/bin/python scripts/parse_batch.py "${COMMON[@]}"

echo "=== 完成；向量: sbatch scripts/hpc/submit_vectors.swu.slurm ==="
