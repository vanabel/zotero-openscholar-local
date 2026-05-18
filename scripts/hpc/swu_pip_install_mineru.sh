#!/bin/bash
# 在 swu3 登录节点执行（在 swu_pip_install.sh 之后）：
#   bash scripts/hpc/swu_pip_install_mineru.sh
# 日志：~/zos_pip_install_mineru.log
set -euo pipefail

LOG="${HOME}/zos_pip_install_mineru.log"
REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"

exec > >(tee -a "${LOG}") 2>&1
echo "=== swu_pip_install_mineru $(date -Is) ==="

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
export PIP_CONFIG_FILE=/dev/null

source "${REPO}/scripts/hpc/swu_modules.sh"
cd "${REPO}/apps/api"

PIP=(.venv/bin/pip install --default-timeout=1000 --retries=10 --no-cache-dir)
TSINGHUA=(--index-url https://pypi.tuna.tsinghua.edu.cn/simple
  --trusted-host pypi.tuna.tsinghua.edu.cn)

echo "--- mineru (PyPI 包名以官方为准；失败时请按 docs/HPC_PARSE.md 手动安装) ---"
if ! "${PIP[@]}" "${TSINGHUA[@]}" "mineru>=2.0" 2>/dev/null; then
  echo "尝试 magic-pdf 包名…"
  "${PIP[@]}" "${TSINGHUA[@]}" "magic-pdf[full]" || true
fi

echo "--- verify ---"
if [[ -x .venv/bin/mineru ]]; then
  .venv/bin/mineru --version 2>/dev/null || .venv/bin/mineru -h 2>/dev/null | head -3 || true
else
  echo "警告: .venv/bin/mineru 未找到，请手动安装 MinerU CLI" >&2
fi

echo "=== done $(date -Is) ==="
echo "下一步: Mac 上 pnpm run download:mineru-models，再 ./scripts/hpc/sync_to_hpc.sh mineru-models"
