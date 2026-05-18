#!/bin/bash
# 仅 OpenScholar scholar 向量。本地只解析 + 双嵌入请用 submit_vectors.slurm
#SBATCH --job-name=zos-scholar
#SBATCH --output=scholar_embed_%j.log
#SBATCH --error=scholar_embed_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
# 按集群分区与 GPU 资源修改下一行，例如：#SBATCH --partition=gpu  #SBATCH --gres=gpu:1

set -euo pipefail

# ── 提交前在登录节点编辑（或通过 sbatch --export=ALL,VAR=... 覆盖）────────
: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${DATA_DIR:=${REPO_ROOT}/apps/api/data}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${HF_HOME:=${SCRATCH:-/tmp}/${USER}/hf_cache}"
: "${MISSING_ONLY:=1}"   # 1=仅补缺失 scholar 向量；0=处理全部有 chunk 的文献
: "${FORCE:=0}"          # 1=强制重算已有 scholar 向量

mkdir -p "${HF_HOME}"
export HF_HOME
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-0}"

cd "${REPO_ROOT}/apps/api"

if [[ ! -d .venv ]]; then
  echo "缺少 .venv，请在登录节点执行: cd apps/api && python3 -m venv .venv && .venv/bin/pip install -e '.[openscholar,lance]'" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export DATA_DIR
export OPENSCHOLAR_DEVICE="${OPENSCHOLAR_DEVICE:-cuda}"
export OPENSCHOLAR_RETRIEVER_ENABLED="${OPENSCHOLAR_RETRIEVER_ENABLED:-1}"
export OPENSCHOLAR_RERANKER_ENABLED="${OPENSCHOLAR_RERANKER_ENABLED:-0}"

ARGS=(--all)
[[ "${MISSING_ONLY}" == "1" ]] && ARGS+=(--missing-only)
[[ "${FORCE}" == "1" ]] && ARGS+=(--force)

echo "=== scholar_embed_batch ==="
echo "REPO_ROOT=${REPO_ROOT}"
echo "DATA_DIR=${DATA_DIR}"
echo "HF_HOME=${HF_HOME}"
echo "OPENSCHOLAR_DEVICE=${OPENSCHOLAR_DEVICE}"
echo "ARGS=${ARGS[*]}"

.venv/bin/python scripts/scholar_embed_batch.py "${ARGS[@]}"

echo "=== 完成；请将 ${DATA_DIR}/app.sqlite 与 ${DATA_DIR}/lance/ 同步回本地 ==="
