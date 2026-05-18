#!/bin/bash
# 西南大学超算（GridView SLURM，登录节点 admin03 / ssh swu3）
#SBATCH --job-name=zos-vectors
#SBATCH --output=zos_vectors_%j.log
#SBATCH --error=zos_vectors_%j.err
#SBATCH --partition=gpu_4090
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G

set -euo pipefail

REPO_ROOT_EARLY="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
# shellcheck disable=SC1091
source "${REPO_ROOT_EARLY}/scripts/hpc/swu_modules.sh"

: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${DATA_DIR:=${REPO_ROOT}/apps/api/data}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${HF_HOME:=${HOME}/.cache/huggingface}"
: "${RUN_CHUNK:=1}"
: "${RUN_EMBED:=1}"
: "${RUN_SCHOLAR:=1}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"

mkdir -p "${HF_HOME}"
export HF_HOME

cd "${REPO_ROOT}/apps/api"
if [[ ! -d .venv ]]; then
  echo "缺少 .venv：module load apps/python/3.12.3 && pip install -e '.[openscholar,lance]'" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export DATA_DIR
export EMBED_PROVIDER="${EMBED_PROVIDER:-openai}"
export OPENSCHOLAR_DEVICE="${OPENSCHOLAR_DEVICE:-cuda}"
export OPENSCHOLAR_RETRIEVER_ENABLED="${OPENSCHOLAR_RETRIEVER_ENABLED:-1}"
export OPENSCHOLAR_RERANKER_ENABLED="${OPENSCHOLAR_RERANKER_ENABLED:-0}"

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

echo "=== zos vectors (SWU) ==="
echo "partition=${SLURM_JOB_PARTITION:-?} DATA_DIR=${DATA_DIR} PAPER_IDS=${PAPER_IDS:-<all>}"

if [[ "${RUN_CHUNK}" == "1" ]]; then
  echo "--- chunk_batch ---"
  .venv/bin/python scripts/chunk_batch.py "${COMMON[@]}"
fi

if [[ "${RUN_EMBED}" == "1" ]]; then
  if [[ "${EMBED_PROVIDER}" != "openai" ]] || [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "embed 需要 EMBED_PROVIDER=openai 与 OPENAI_API_KEY" >&2
    exit 1
  fi
  echo "--- embed_batch ---"
  .venv/bin/python scripts/embed_batch.py "${COMMON[@]}"
fi

if [[ "${RUN_SCHOLAR}" == "1" ]]; then
  echo "--- scholar_embed_batch ---"
  .venv/bin/python scripts/scholar_embed_batch.py "${COMMON[@]}"
fi

echo "=== 完成；Mac: rsync swu3:${DATA_DIR}/app.sqlite apps/api/data/ ==="
