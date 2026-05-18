#!/bin/bash
#SBATCH --job-name=zos-vectors
#SBATCH --output=zos_vectors_%j.log
#SBATCH --error=zos_vectors_%j.err
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
# 按集群修改：#SBATCH --partition=gpu  #SBATCH --gres=gpu:1

set -euo pipefail

# 本地只解析 → 同步 parsed/ + app.sqlite → 本作业：分块 → API 嵌入 → OpenScholar GPU 嵌入
: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${DATA_DIR:=${REPO_ROOT}/apps/api/data}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${HF_HOME:=${SCRATCH:-/tmp}/${USER}/hf_cache}"
: "${RUN_CHUNK:=1}"
: "${RUN_EMBED:=1}"
: "${RUN_SCHOLAR:=1}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"

mkdir -p "${HF_HOME}"
export HF_HOME

cd "${REPO_ROOT}/apps/api"
if [[ ! -d .venv ]]; then
  echo "缺少 .venv：pip install -e '.[openscholar,lance]'" >&2
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

COMMON=(--all)
[[ "${MISSING_ONLY}" == "1" ]] && COMMON+=(--missing-only)
[[ "${FORCE}" == "1" ]] && COMMON+=(--force)

echo "=== zos vectors batch ==="
echo "DATA_DIR=${DATA_DIR} EMBED_PROVIDER=${EMBED_PROVIDER} OPENSCHOLAR_DEVICE=${OPENSCHOLAR_DEVICE}"

if [[ "${RUN_CHUNK}" == "1" ]]; then
  echo "--- chunk_batch ---"
  .venv/bin/python scripts/chunk_batch.py "${COMMON[@]}"
fi

if [[ "${RUN_EMBED}" == "1" ]]; then
  if [[ "${EMBED_PROVIDER}" != "openai" ]] || [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "embed 需要 EMBED_PROVIDER=openai 与 OPENAI_API_KEY（集群无 Ollama）" >&2
    exit 1
  fi
  echo "--- embed_batch (OpenAI 兼容 API) ---"
  .venv/bin/python scripts/embed_batch.py "${COMMON[@]}"
fi

if [[ "${RUN_SCHOLAR}" == "1" ]]; then
  echo "--- scholar_embed_batch ---"
  .venv/bin/python scripts/scholar_embed_batch.py "${COMMON[@]}"
fi

echo "=== 完成；rsync 回 Mac: app.sqlite 与 lance/ ==="
