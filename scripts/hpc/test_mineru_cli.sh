#!/usr/bin/env bash
# 在 swu3 上检查 MinerU 本地 CLI 是否就绪（登录节点）；GPU 实测请 sbatch submit_test_mineru.swu.slurm
# 用法：cd ~/zotero-openscholar-local && bash scripts/hpc/test_mineru_cli.sh
set -euo pipefail

REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
API="${REPO}/apps/api"
ENV_FILE="${ENV_FILE:-${API}/.env.hpc}"
CFG="${API}/config/mineru.hpc.json"
VLM="${API}/data/mineru-models/MinerU2.5-Pro-2604-1.2B"
PIPE="${API}/data/mineru-models/PDF-Extract-Kit-1.0"

export LC_ALL=C LANG=C
export PYTHONPATH="${API}/scripts/mineru_shims:${PYTHONPATH:-}"
unset LANGUAGE 2>/dev/null || true

echo "=== MinerU CLI 检查 $(date -Is) ==="
echo "REPO=${REPO}"

if [[ -f "${REPO}/scripts/hpc/swu_modules.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO}/scripts/hpc/swu_modules.sh"
  echo "module: python + cuda loaded"
else
  echo "WARN: 无 swu_modules.sh"
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  echo "sourced ${ENV_FILE}"
else
  echo "WARN: 无 ${ENV_FILE}（可复制 .env.hpc.example）"
fi

_fail=0
_ok() { echo "  OK  $*"; }
_warn() { echo "  WARN $*"; _fail=1; }
_note() { echo "  NOTE $*"; }
_die() { echo "  FAIL $*"; _fail=1; }

# 1) 权重目录（勿 rsync Mac 上 --link 的断链；用 sync_to_hpc.sh mineru-models）
if [[ -L "${VLM}" ]] && ! [[ -e "${VLM}" ]]; then
  _die "VLM 为断链 $(readlink "${VLM}" 2>/dev/null) → 请 Mac 执行 ./scripts/hpc/sync_to_hpc.sh mineru-models"
fi
if [[ -L "${PIPE}" ]] && ! [[ -e "${PIPE}" ]]; then
  _die "PIPE 为断链 $(readlink "${PIPE}" 2>/dev/null) → 请 Mac 执行 ./scripts/hpc/sync_to_hpc.sh mineru-models"
fi
[[ -d "${VLM}" ]] && _ok "VLM  ${VLM}" || _die "缺 VLM  ${VLM}（Mac: sync_to_hpc.sh mineru-models）"
[[ -d "${PIPE}" ]] && _ok "PIPE ${PIPE}" || _die "缺 PIPE ${PIPE}"
[[ -f "${VLM}/config.json" ]] && _ok "VLM config.json" || _warn "VLM 无 config.json"
[[ -d "${PIPE}/models" ]] && _ok "PIPE models/" || _warn "PIPE 无 models/（ModelScope 布局）"

# 2) mineru.hpc.json
if [[ ! -f "${CFG}" ]]; then
  _warn "无 ${CFG}，正在从 example 生成…"
  mkdir -p "${API}/config"
  sed "s|<账号>|${USER}|g" "${REPO}/scripts/hpc/mineru.json.hpc.example" >"${CFG}"
fi
_ok "config ${CFG}"

# 3) venv / mineru
if [[ ! -d "${API}/.venv" ]]; then
  _die "无 .venv → bash scripts/hpc/swu_pip_install.sh"
fi
MINERU_BIN="${API}/.venv/bin/mineru"
API_BIN="${API}/.venv/bin/mineru-api"
if [[ ! -x "${MINERU_BIN}" ]]; then
  _die "无 ${MINERU_BIN} → bash scripts/hpc/swu_pip_install_mineru.sh"
else
  _ok "mineru $( "${MINERU_BIN}" --version 2>/dev/null || "${MINERU_BIN}" -h 2>&1 | head -1 )"
fi
[[ -x "${API_BIN}" ]] && _ok "mineru-api" || _warn "无 mineru-api（作业里 start_mineru_api_hpc.sh 会失败）"

# 4) 环境变量（供 parse_batch）
export MINERU_MODE="${MINERU_MODE:-cli}"
export MINERU_CLI="${MINERU_CLI:-${MINERU_BIN}}"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"
export MINERU_TOOLS_CONFIG_JSON="${MINERU_TOOLS_CONFIG_JSON:-${CFG}}"
export MINERU_CLI_EXTRA_ARGS="${MINERU_CLI_EXTRA_ARGS:---backend vlm-auto-engine --source local}"
if [[ "${MINERU_CLI_EXTRA_ARGS}" == *"vlm-auto-engine"* ]]; then
  export MINERU_API_URL=""
else
  export MINERU_API_URL="${MINERU_API_URL:-http://127.0.0.1:8001}"
fi
_ok "MINERU_MODE=${MINERU_MODE} MINERU_CLI=${MINERU_CLI}"
_ok "MINERU_TOOLS_CONFIG_JSON=${MINERU_TOOLS_CONFIG_JSON}"

# 5) 登录节点 GPU（通常无卡，仅提示）
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L 2>/dev/null | grep -q GPU; then
  _ok "登录节点可见 GPU: $(nvidia-smi -L | head -1)"
else
  _note "登录节点无 GPU（正常）；解析请在 GPU 作业里测: sbatch scripts/hpc/submit_test_mineru.swu.slurm"
fi

# 6) 可选：启动 mineru-api 并 curl
if [[ "${RUN_MINERU_API_SMOKE:-0}" == "1" ]] && [[ -x "${API_BIN}" ]]; then
  echo "--- mineru-api 冒烟 ---"
  export REPO_ROOT="${REPO}" ENV_FILE="${ENV_FILE}"
  bash "${REPO}/scripts/hpc/start_mineru_api_hpc.sh" || _die "mineru-api 启动失败"
fi

echo ""
if [[ "${_fail}" -eq 0 ]]; then
  echo "=== 登录节点检查通过；GPU 解析实测："
  echo "  export PATH=/opt/gridview/slurm/bin:\$PATH"
  echo "  cd ${REPO} && sbatch scripts/hpc/submit_test_mineru.swu.slurm"
  exit 0
fi
echo "=== 存在 FAIL，请先按提示安装/同步 ==="
exit 1
