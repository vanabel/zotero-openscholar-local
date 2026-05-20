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
# 登录节点默认 gcc 4.8 且无 g++，须只用 wheel，勿编译 pandas 等
BINARY=(--only-binary=:all:)

echo "--- 预装 wheel（避免 mineru 依赖源码编译）---"
"${PIP[@]}" "${TSINGHUA[@]}" "${BINARY[@]}" pandas pydantic scikit-image scipy \
  albumentations matplotlib seaborn opencv-python-headless psutil py-cpuinfo thop \
  accelerate aiofiles httpx-retries av cobble 2>/dev/null || true
# doclayout-yolo 需要 torchvision；从 PyTorch cu121 源装 wheel，并 --no-deps 避免重装 torch/numpy。
"${PIP[@]}" --index-url https://download.pytorch.org/whl/cu121 --no-deps torchvision 2>/dev/null || true

echo "--- mineru 3.x (no-deps；依赖在下面按 SWU 可用 wheel/纯 Python 补齐）---"
if ! "${PIP[@]}" "${TSINGHUA[@]}" --no-deps "mineru>=3.0,<4"; then
  echo "mineru>=3 失败，回退 mineru>=2.0（无 api_client，wrapper 仅转发 CLI）…"
  "${PIP[@]}" "${TSINGHUA[@]}" "${BINARY[@]}" "mineru>=2.0,<3" || {
    echo "mineru 安装失败；勿用 magic-pdf[full]（易触发 numpy 编译）" >&2
    exit 1
  }
fi

echo "--- mineru 3.x VLM/core deps (avoid onnxruntime pipeline dep) ---"
"${PIP[@]}" "${TSINGHUA[@]}" "${BINARY[@]}" "transformers>=4.57.3,<5" "huggingface-hub<1" || true
"${PIP[@]}" "${TSINGHUA[@]}" --no-deps \
  pylatexenc magika mineru-vl-utils qwen-vl-utils python-docx pypptx-with-oxml \
  mammoth openpyxl ftfy dill omegaconf pyclipper shapely lxml || true

# MinerU pipeline 模式会 import doclayout_yolo；mineru 依赖声明未必拉齐该包。
# doclayout_yolo 运行时还会 import ultralytics；显式安装以避免 GPU 作业才暴露缺包。
echo "--- doclayout-yolo (pipeline layout) ---"
"${PIP[@]}" "${TSINGHUA[@]}" "${BINARY[@]}" ultralytics
"${PIP[@]}" "${TSINGHUA[@]}" --no-deps doclayout-yolo

echo "--- verify ---"
if [[ -x .venv/bin/mineru ]]; then
  PYTHONPATH="${REPO}/apps/api/scripts/mineru_shims:${PYTHONPATH:-}" \
    .venv/bin/mineru --version 2>/dev/null || true
else
  echo "警告: .venv/bin/mineru 未找到，请手动安装 MinerU CLI" >&2
fi

echo "=== done $(date -Is) ==="
echo "下一步: Mac 上 ./scripts/hpc/sync_to_hpc.sh mineru-models"
echo "  （若 Mac 已有 MinerU + ~/mineru.json，会从 models-dir 同步，无需 download:mineru-models）"
