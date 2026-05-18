#!/bin/bash
# 在 swu3 登录节点执行：bash scripts/hpc/swu_pip_install.sh
# 日志：~/zos_pip_install.log
set -euo pipefail

LOG="${HOME}/zos_pip_install.log"
REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"

exec > >(tee -a "${LOG}") 2>&1
echo "=== swu_pip_install $(date -Is) ==="

# 禁用一切代理（含 git global proxy）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY no_proxy NO_PROXY
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.proxy
export GIT_CONFIG_VALUE_0=

source "${REPO}/scripts/hpc/swu_modules.sh"
cd "${REPO}/apps/api"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# 覆盖站点/用户 pip.conf 里的 extra-index-url（否则会落到 mirrors.aliyun 超大 wheel 超时）
export PIP_CONFIG_FILE=/dev/null
PIP=(.venv/bin/pip install --default-timeout=1000 --retries=10 --no-cache-dir)
TSINGHUA=(--index-url https://pypi.tuna.tsinghua.edu.cn/simple
  --trusted-host pypi.tuna.tsinghua.edu.cn)

.venv/bin/pip install -U pip wheel setuptools

# 1) PyTorch CUDA（仅 torch；勿装 torchvision，否则会从 pytorch index 拉 numpy 源码）
echo "--- torch (pytorch.org cu121 only) ---"
"${PIP[@]}" --index-url https://download.pytorch.org/whl/cu121 torch

# 2) 二进制 wheel（避免在 pytorch index 下编译 numpy/pyarrow）
echo "--- numpy / pyarrow wheels ---"
"${PIP[@]}" "${TSINGHUA[@]}" --only-binary=:all: "numpy>=1.26" "pyarrow>=15.0.0"

# 3) 其余依赖（仅清华源）
echo "--- project deps ---"
"${PIP[@]}" "${TSINGHUA[@]}" \
  "transformers>=4.40" sentencepiece protobuf \
  "lancedb>=0.17.0"

"${PIP[@]}" "${TSINGHUA[@]}" -e ".[openscholar,lance]" --no-deps

"${PIP[@]}" "${TSINGHUA[@]}" \
  fastapi "uvicorn[standard]" httpx pydantic-settings pypdf python-multipart

"${PIP[@]}" "${TSINGHUA[@]}" --only-binary=:all: "pysqlite3-binary>=0.5.0"

echo "--- verify ---"
.venv/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
.venv/bin/pip show zotero-openscholar-api | head -2
echo "=== done $(date -Is) ==="
