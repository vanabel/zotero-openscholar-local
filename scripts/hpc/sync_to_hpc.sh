#!/usr/bin/env bash
# Mac → 超算：同步仓库 / 数据 / PDF / MinerU 权重 / OpenScholar 模型 / .env.hpc
# 用法：scripts/hpc/sync_to_hpc.sh {code|data|pdfs|mineru-models|models|env|all|help}
# 配置：复制 scripts/hpc/sync_to_hpc.env.example → sync_to_hpc.local.env
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_ENV="${REPO_ROOT}/scripts/hpc/sync_to_hpc.local.env"
if [[ -f "${LOCAL_ENV}" ]]; then
  # shellcheck disable=SC1090
  source "${LOCAL_ENV}"
fi

: "${HPC_SSH:=swu3}"
: "${LOCAL_MODELS_ROOT:=${HOME}/models}"
: "${SYNC_RERANKER:=0}"
: "${SYNC_HF_CACHE:=0}"
: "${LOCAL_HF_CACHE:=${HOME}/.cache/huggingface}"
: "${LOCAL_ZOTERO_STORAGE:=${HOME}/Zotero/storage}"
: "${LOCAL_MINERU_MODELS:=${REPO_ROOT}/apps/api/data/mineru-models}"
: "${LOCAL_MINERU_CONFIG:=${HOME}/mineru.json}"
: "${REMOTE_MINERU_VLM_NAME:=MinerU2.5-Pro-2604-1.2B}"
: "${REMOTE_MINERU_PIPELINE_NAME:=PDF-Extract-Kit-1.0}"
: "${SYNC_RSYNC_PROGRESS:=1}"

# Mac 传入 LANG=C.UTF-8 时，超算未装该 locale 会导致 perl（rsync 远端）告警
_HPC_SH_PREFIX='export LC_ALL=C LANG=C; unset LANGUAGE 2>/dev/null || true;'
HPC_RSYNC_RSH="${REPO_ROOT}/scripts/hpc/hpc_rsync_rsh.sh"

_init_rsync() {
  if [[ ! -x "${HPC_RSYNC_RSH}" ]]; then
    echo "缺少可执行 ${HPC_RSYNC_RSH}（chmod +x）" >&2
    exit 1
  fi
  local args=(-az)
  if [[ "${SYNC_RSYNC_PROGRESS}" == "1" ]]; then
    # rsync 3.1+：单行总进度 + 速度；旧版（含 macOS 自带）回退 --progress
    if rsync --info=progress2 --dry-run -a /dev/null /dev/null >/dev/null 2>&1; then
      args+=(--info=progress2 --stats)
    else
      args+=(--progress --stats)
    fi
  fi
  RSYNC=(rsync "${args[@]}" -e "${HPC_RSYNC_RSH}")
}
_init_rsync

_hpc_ssh() {
  ssh "${HPC_SSH}" "${_HPC_SH_PREFIX} $*"
}

_resolve_remote_home() {
  if [[ -n "${HPC_REMOTE_HOME:-}" ]]; then
    printf '%s' "${HPC_REMOTE_HOME}"
    return
  fi
  ssh "${HPC_SSH}" "${_HPC_SH_PREFIX} sh -c 'printf %s \"\$HOME\"'"
}

_remote_repo() {
  local home
  home="$(_resolve_remote_home)"
  if [[ -n "${REPO_REMOTE:-}" ]]; then
    case "${REPO_REMOTE}" in
      "~/"*) printf '%s/%s' "${home}" "${REPO_REMOTE#~/}" ;;
      /*) printf '%s' "${REPO_REMOTE}" ;;
      *) printf '%s/%s' "${home}" "${REPO_REMOTE}" ;;
    esac
    return
  fi
  printf '%s/zotero-openscholar-local' "${home}"
}

_remote_models_root() {
  local home
  home="$(_resolve_remote_home)"
  if [[ -n "${REMOTE_MODELS_ROOT:-}" ]]; then
    case "${REMOTE_MODELS_ROOT}" in
      "~/"*) printf '%s/%s' "${home}" "${REMOTE_MODELS_ROOT#~/}" ;;
      /*) printf '%s' "${REMOTE_MODELS_ROOT}" ;;
      *) printf '%s/%s' "${home}" "${REMOTE_MODELS_ROOT}" ;;
    esac
    return
  fi
  printf '%s/models' "${home}"
}

_remote_hf_home() {
  local home
  home="$(_resolve_remote_home)"
  if [[ -n "${REMOTE_HF_HOME:-}" ]]; then
    case "${REMOTE_HF_HOME}" in
      "~/"*) printf '%s/%s' "${home}" "${REMOTE_HF_HOME#~/}" ;;
      /*) printf '%s' "${REMOTE_HF_HOME}" ;;
      *) printf '%s/%s' "${home}" "${REMOTE_HF_HOME}" ;;
    esac
    return
  fi
  printf '%s/.cache/huggingface' "${home}"
}

_model_dir_ok() {
  local d="$1"
  [[ -d "${d}" ]] || return 1
  [[ -f "${d}/config.json" ]] || return 1
  [[ -f "${d}/model.safetensors" || -f "${d}/pytorch_model.bin" ]] && return 0
  compgen -G "${d}/model-*-of-*.safetensors" >/dev/null 2>&1
}

_sync_model_subdir() {
  local name="$1"
  local src="${LOCAL_MODELS_ROOT}/${name}"
  local dst_root
  dst_root="$(_remote_models_root)"
  if ! _model_dir_ok "${src}"; then
    echo "跳过 ${name}：未找到有效 HF 目录 ${src}" >&2
    return 0
  fi
  echo "=== rsync ${name} → ${HPC_SSH}:${dst_root}/${name}/ ==="
  _hpc_ssh "mkdir -p '${dst_root}/${name}'"
  "${RSYNC[@]}" "${src}/" "${HPC_SSH}:${dst_root}/${name}/"
}

_sync_code() {
  local remote
  remote="$(_remote_repo)"
  echo "=== rsync 仓库 → ${HPC_SSH}:${remote}/ ==="
  _hpc_ssh "mkdir -p '${remote}'"
  "${RSYNC[@]}" \
    --exclude '.venv' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude 'apps/api/data' \
    --exclude '.git/objects' \
    "${REPO_ROOT}/" "${HPC_SSH}:${remote}/"
}

_remote_zotero_storage() {
  local remote
  remote="$(_remote_repo)"
  if [[ -n "${REMOTE_ZOTERO_STORAGE:-}" ]]; then
    case "${REMOTE_ZOTERO_STORAGE}" in
      "~/"*) printf '%s/%s' "$(_resolve_remote_home)" "${REMOTE_ZOTERO_STORAGE#~/}" ;;
      /*) printf '%s' "${REMOTE_ZOTERO_STORAGE}" ;;
      *) printf '%s/%s' "$(_resolve_remote_home)" "${REMOTE_ZOTERO_STORAGE}" ;;
    esac
    return
  fi
  printf '%s/apps/api/data/zotero-storage' "${remote}"
}

_sync_data() {
  local remote data_dir
  remote="$(_remote_repo)"
  data_dir="${remote}/apps/api/data"
  echo "=== rsync app.sqlite + parsed/ → ${HPC_SSH}:${data_dir}/ ==="
  _hpc_ssh "mkdir -p '${data_dir}/parsed'"
  if [[ -f "${REPO_ROOT}/apps/api/data/app.sqlite" ]]; then
    "${RSYNC[@]}" "${REPO_ROOT}/apps/api/data/app.sqlite" "${HPC_SSH}:${data_dir}/"
  else
    echo "警告：本地无 apps/api/data/app.sqlite" >&2
  fi
  if [[ -d "${REPO_ROOT}/apps/api/data/parsed" ]]; then
    "${RSYNC[@]}" "${REPO_ROOT}/apps/api/data/parsed/" "${HPC_SSH}:${data_dir}/parsed/"
  fi
}

_sync_pdfs() {
  local remote_storage
  remote_storage="$(_remote_zotero_storage)"
  if [[ ! -d "${LOCAL_ZOTERO_STORAGE}" ]]; then
    echo "跳过 pdfs：本地无 ${LOCAL_ZOTERO_STORAGE}" >&2
    exit 1
  fi
  echo "=== rsync Zotero storage → ${HPC_SSH}:${remote_storage}/ ==="
  echo "（仅 PDF；体积大时可多次增量同步）"
  _hpc_ssh "mkdir -p '${remote_storage}'"
  "${RSYNC[@]}" \
    --include '*/' \
    --include '*.pdf' \
    --include '*.PDF' \
    --exclude '*' \
    "${LOCAL_ZOTERO_STORAGE}/" "${HPC_SSH}:${remote_storage}/"
  echo ""
  echo "请在 apps/api/.env.hpc 中设置："
  echo "  ZOTERO_STORAGE_PATH=${remote_storage}"
}

_mineru_models_from_config() {
  local cfg="$1"
  if [[ ! -f "${cfg}" ]]; then
    return 1
  fi
  MINERU_CFG="${cfg}" python3 - <<'PY'
import json, os, shlex
from pathlib import Path
cfg = Path(os.environ["MINERU_CFG"])
data = json.loads(cfg.read_text(encoding="utf-8"))
models = data.get("models-dir") or {}
vlm = (models.get("vlm") or "").strip()
pipe = (models.get("pipeline") or "").strip()
if vlm:
    print(f"MINERU_VLM_SRC={shlex.quote(vlm)}")
if pipe:
    print(f"MINERU_PIPE_SRC={shlex.quote(pipe)}")
PY
}

_sync_one_mineru_model_dir() {
  local src="$1" remote_name="$2" data_dir="$3"
  if [[ -z "${src}" ]] || [[ ! -d "${src}" ]]; then
    echo "跳过 ${remote_name}：本地目录不存在: ${src:-<empty>}" >&2
    return 1
  fi
  echo "  ${src} → ${data_dir}/${remote_name}/"
  _hpc_ssh "mkdir -p '${data_dir}/${remote_name}'"
  "${RSYNC[@]}" "${src}/" "${HPC_SSH}:${data_dir}/${remote_name}/"
}

_sync_mineru_models() {
  local remote data_dir cfg_remote
  remote="$(_remote_repo)"
  data_dir="${remote}/apps/api/data/mineru-models"
  cfg_remote="${remote}/apps/api/config/mineru.hpc.json"
  _hpc_ssh "mkdir -p '${data_dir}'"

  local use_repo_models=0
  local vlm_local="${LOCAL_MINERU_MODELS}/${REMOTE_MINERU_VLM_NAME}"
  # Mac 上 pnpm download:mineru-models --link 会得到指向本机 ModelScope 的符号链接，不可 rsync 到超算
  if [[ -L "${vlm_local}" ]]; then
    echo "注意：${vlm_local} 为符号链接，改从 ${LOCAL_MINERU_CONFIG} 同步实体文件" >&2
  elif [[ -f "${LOCAL_MINERU_MODELS}/config.json" ]]; then
    use_repo_models=1
  elif [[ -e "${vlm_local}/config.json" ]]; then
    use_repo_models=1
  fi
  if [[ "${use_repo_models}" == "1" ]]; then
    echo "=== rsync MinerU 权重（仓库 data/mineru-models，实体目录）→ ${HPC_SSH}:${data_dir}/ ==="
    "${RSYNC[@]}" "${LOCAL_MINERU_MODELS}/" "${HPC_SSH}:${data_dir}/"
  else
    local cfg="${LOCAL_MINERU_CONFIG}"
    echo "=== rsync MinerU 权重（${cfg} models-dir）→ ${HPC_SSH}:${data_dir}/ ==="
    if [[ ! -f "${cfg}" ]]; then
      echo "跳过 mineru-models：无 ${LOCAL_MINERU_MODELS} 且无 ${cfg}" >&2
      echo "  可选: pnpm run download:mineru-models" >&2
      echo "  或配置 LOCAL_MINERU_CONFIG 指向 ~/mineru.json（见 sync_to_hpc.env.example）" >&2
      exit 1
    fi
    # shellcheck disable=SC1090
    eval "$(_mineru_models_from_config "${cfg}")"
    if [[ -z "${MINERU_VLM_SRC:-}" ]] && [[ -z "${MINERU_PIPE_SRC:-}" ]]; then
      echo "跳过：${cfg} 中 models-dir 无 vlm/pipeline 路径" >&2
      exit 1
    fi
    local ok=0
    if [[ -n "${MINERU_VLM_SRC:-}" ]]; then
      _sync_one_mineru_model_dir "${MINERU_VLM_SRC}" "${REMOTE_MINERU_VLM_NAME}" "${data_dir}" && ok=1
    fi
    if [[ -n "${MINERU_PIPE_SRC:-}" ]]; then
      _sync_one_mineru_model_dir "${MINERU_PIPE_SRC}" "${REMOTE_MINERU_PIPELINE_NAME}" "${data_dir}" && ok=1
    fi
    if [[ "${ok}" -eq 0 ]]; then
      exit 1
    fi
  fi

  echo ""
  echo "建议在超算 apps/api/config/mineru.hpc.json（models-dir 示例）："
  echo "  \"vlm\": \"${data_dir}/${REMOTE_MINERU_VLM_NAME}\""
  echo "  \"pipeline\": \"${data_dir}/${REMOTE_MINERU_PIPELINE_NAME}\""
  echo ""
  echo "apps/api/.env.hpc："
  echo "  MINERU_MODEL_SOURCE=local"
  echo "  MINERU_TOOLS_CONFIG_JSON=${cfg_remote}"
  echo "  MINERU_CLI=${remote}/apps/api/.venv/bin/mineru   # 超算 Linux venv，勿 rsync Mac MinerU/.venv"
  if [[ -n "${LOCAL_MINERU_CLI:-}" ]]; then
    echo ""
    echo "（Mac 本机 CLI 参考: ${LOCAL_MINERU_CLI}）"
  fi
}

_sync_models() {
  echo "本地模型根：${LOCAL_MODELS_ROOT}"
  echo "超算模型根：$(_remote_models_root) （请在 apps/api/.env.hpc 中配置 OPENSCHOLAR_RETRIEVER_MODEL）"
  _sync_model_subdir "openscholar-retriever"
  if [[ "${SYNC_RERANKER}" == "1" ]]; then
    _sync_model_subdir "openscholar-reranker"
  fi
  if [[ "${SYNC_HF_CACHE}" == "1" ]]; then
    local hf_remote
    hf_remote="$(_remote_hf_home)"
    if [[ -d "${LOCAL_HF_CACHE}" ]]; then
      echo "=== rsync Hugging Face 缓存 → ${HPC_SSH}:${hf_remote}/ ==="
      _hpc_ssh "mkdir -p '${hf_remote}'"
      "${RSYNC[@]}" "${LOCAL_HF_CACHE}/" "${HPC_SSH}:${hf_remote}/"
    else
      echo "跳过 HF 缓存：本地无 ${LOCAL_HF_CACHE}" >&2
    fi
  fi
  local home models_root
  home="$(_resolve_remote_home)"
  models_root="$(_remote_models_root)"
  echo ""
  echo "建议在 apps/api/.env.hpc 中设置："
  echo "  OPENSCHOLAR_RETRIEVER_MODEL=${models_root}/openscholar-retriever"
  if [[ "${SYNC_RERANKER}" == "1" ]]; then
    echo "  OPENSCHOLAR_RERANKER_MODEL=${models_root}/openscholar-reranker"
  fi
  if [[ "${SYNC_HF_CACHE}" == "1" ]]; then
    echo "  HF_HOME=$(_remote_hf_home)"
  fi
  echo "  DATA_DIR=$(_remote_repo)/apps/api/data"
}

_sync_env() {
  local remote env_src
  remote="$(_remote_repo)"
  env_src="${REPO_ROOT}/apps/api/.env.hpc"
  if [[ ! -f "${env_src}" ]]; then
    echo "缺少 ${env_src}，请先：cp apps/api/.env.hpc.example apps/api/.env.hpc" >&2
    exit 1
  fi
  echo "=== scp .env.hpc → ${HPC_SSH}:${remote}/apps/api/ ==="
  scp "${env_src}" "${HPC_SSH}:${remote}/apps/api/.env.hpc"
}

_usage() {
  cat <<EOF
用法: $(basename "$0") <code|data|pdfs|mineru-models|models|env|all|help>

  code          同步仓库（排除 .venv、data、node_modules）
  data          同步 app.sqlite 与 data/parsed/
  pdfs          同步 Zotero storage 下 PDF（见 LOCAL_ZOTERO_STORAGE）
  mineru-models 同步 MinerU 权重（data/mineru-models 或 ~/mineru.json models-dir）
  models        同步 openscholar-retriever（SYNC_RERANKER=1 时含 reranker）
  env           上传 apps/api/.env.hpc（勿提交 git）
  all           依次 code → data → pdfs → mineru-models → models → env

配置: ${LOCAL_ENV}（见 sync_to_hpc.env.example）
SSH:  HPC_SSH=${HPC_SSH}
EOF
}

cmd="${1:-help}"
case "${cmd}" in
  code) _sync_code ;;
  data) _sync_data ;;
  pdfs) _sync_pdfs ;;
  mineru-models) _sync_mineru_models ;;
  models) _sync_models ;;
  env) _sync_env ;;
  all)
    _sync_code
    _sync_data
    _sync_pdfs
    _sync_mineru_models
    _sync_models
    _sync_env
    ;;
  help | -h | --help) _usage ;;
  *)
    echo "未知子命令: ${cmd}" >&2
    _usage
    exit 1
    ;;
esac

echo "=== 完成: ${cmd} ==="
