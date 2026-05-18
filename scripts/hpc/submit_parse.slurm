#!/bin/bash
# 通用 SLURM：MinerU 批量解析 PDF → parsed/document.md
# 前置：Mac rsync app.sqlite + Zotero storage；见 docs/HPC_PARSE.md
#SBATCH --job-name=zos-parse
#SBATCH --output=zos_parse_%j.log
#SBATCH --error=zos_parse_%j.err
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
# 按集群修改：#SBATCH --partition=gpu  #SBATCH --gres=gpu:1

set -euo pipefail

: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${DATA_DIR:=${REPO_ROOT}/apps/api/data}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${RUN_MINERU_API:=1}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"

cd "${REPO_ROOT}/apps/api"
if [[ ! -d .venv ]]; then
  echo "缺少 .venv" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export DATA_DIR
export REPO_ROOT

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

echo "=== zos parse batch ==="
echo "DATA_DIR=${DATA_DIR} PAPER_IDS=${PAPER_IDS:-<all>} MINERU_MODE=${MINERU_MODE:-cli}"

.venv/bin/python scripts/parse_batch.py "${COMMON[@]}"

echo "=== 解析完成；下一步: sbatch submit_vectors.slurm 或 rsync parsed/ 回 Mac ==="
