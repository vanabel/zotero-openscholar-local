#!/bin/bash
# SWU：GPU 上 MinerU CLI 冒烟（生成最小 PDF → parse_one → 检查 document.md）
#SBATCH --job-name=zos-mineru-test
#SBATCH --output=zos_mineru_test_%j.log
#SBATCH --error=zos_mineru_test_%j.err
#SBATCH --partition=gpu_4090
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G

set -euo pipefail

REPO_ROOT_EARLY="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
# shellcheck disable=SC1091
source "${REPO_ROOT_EARLY}/scripts/hpc/swu_modules.sh"

: "${REPO_ROOT:=${HOME}/zotero-openscholar-local}"
: "${ENV_FILE:=${REPO_ROOT}/apps/api/.env.hpc}"
: "${RUN_MINERU_API:=0}"

export REPO_ROOT
cd "${REPO_ROOT}/apps/api"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export MINERU_MODE="${MINERU_MODE:-cli}"
export MINERU_CLI="${MINERU_CLI:-${REPO_ROOT}/apps/api/.venv/bin/mineru}"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"
export MINERU_TOOLS_CONFIG_JSON="${MINERU_TOOLS_CONFIG_JSON:-${REPO_ROOT}/apps/api/config/mineru.hpc.json}"
export MINERU_API_URL="${MINERU_API_URL:-}"
# SWU Python 3.12 / CentOS7 无 onnxruntime wheel；测试默认走 VLM 后端，避开 pipeline。
export MINERU_CLI_EXTRA_ARGS="${MINERU_CLI_EXTRA_ARGS:---backend vlm-auto-engine --source local}"
if [[ "${MINERU_CLI_EXTRA_ARGS}" == *"vlm-auto-engine"* ]]; then
  export MINERU_API_URL=""
  RUN_MINERU_API=0
fi
export DATA_DIR="${DATA_DIR:-${REPO_ROOT}/apps/api/data}"

echo "=== zos mineru GPU test partition=${SLURM_JOB_PARTITION:-?} ==="
nvidia-smi -L || true

if [[ "${RUN_MINERU_API}" == "1" ]]; then
  bash "${REPO_ROOT}/scripts/hpc/start_mineru_api_hpc.sh"
fi

TEST_DIR="${DATA_DIR}/_mineru_smoke"
PDF="${TEST_DIR}/smoke.pdf"
OUT="${DATA_DIR}/parsed/_mineru_smoke_test"
mkdir -p "${TEST_DIR}" "${OUT}"

# 手写 PDF 常缺字体资源 → MinerU 失败；用 reportlab 生成标准可提取文本 PDF
.venv/bin/python -c "
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

pdf = Path('${PDF}')
pdf.parent.mkdir(parents=True, exist_ok=True)
c = canvas.Canvas(str(pdf), pagesize=A4)
c.setFont('Helvetica', 14)
c.drawString(72, 750, 'MinerU GPU smoke: Helvetica text for MinerU and pypdf.')
c.drawString(72, 720, 'Second line to exceed minimum markdown length.')
c.save()
print('wrote', pdf, pdf.stat().st_size, 'bytes')
"

export DATA_DIR
.venv/bin/python -c "
from pathlib import Path
from app.pipeline_logging import setup_logging
from app.services.pdf_parse import clear_parsed_output_dir, parse_one, load_parsed_markdown

setup_logging()
pid = '_mineru_smoke_test'
pdf = Path('${PDF}')
out = Path('${OUT}')
out.mkdir(parents=True, exist_ok=True)
clear_parsed_output_dir(out)
md, meta = parse_one(pid, pdf, out, force_reparse=True)
(out / 'document.md').write_text(md, encoding='utf-8')
mode = str(meta.get('mode') or '')
print('parse_one mode=', mode, 'mineru=', meta.get('mineru'), 'chars=', len(md))
if 'pypdf_fallback' in mode:
    err = (meta.get('mineru_error') or meta.get('mineru_log_tail') or '')[:2000]
    print('MinerU 未成功（见 .err 或 parse 日志）。mineru_error 节选:', err)
    raise SystemExit(2)
if mode != 'mineru':
    print('WARN: 非预期 mode=', mode)
loaded = load_parsed_markdown(out)
if loaded is None or len(loaded[0]) < 10:
    raise SystemExit('document.md 过短或缺失')
print('preview:', loaded[0][:200].replace(chr(10), ' '))
"

echo "=== MinerU GPU 冒烟成功（mode=mineru，非 pypdf 降级）==="
