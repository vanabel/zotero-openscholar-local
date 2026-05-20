#!/usr/bin/env bash
# 在 swu3 登录节点把待解析 paper_id 切片，并提交多个单 GPU 解析作业。
# 默认按 gpu_4090 当前空闲卡数提交，最多 8 片；每个作业申请 1 张卡。
set -euo pipefail

REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
API="${REPO}/apps/api"
ENV_FILE="${ENV_FILE:-${API}/.env.hpc}"

: "${PARTITION:=gpu_4090}"
: "${MAX_SHARDS:=8}"
: "${PARSE_SHARDS:=auto}"      # auto 或 1..8
: "${GPUS_PER_JOB:=1}"
: "${CPUS_PER_TASK:=8}"
: "${MEM:=48G}"
: "${TIME:=48:00:00}"
: "${MISSING_ONLY:=1}"
: "${FORCE:=0}"
: "${PAPER_IDS:=}"             # 可选：逗号分隔，只切这些 id
: "${DRY_RUN:=0}"

export LC_ALL=C LANG=C
unset LANGUAGE 2>/dev/null || true

# shellcheck disable=SC1091
source "${REPO}/scripts/hpc/swu_modules.sh"
export PATH=/opt/gridview/slurm/bin:${PATH}

cd "${API}"
if [[ ! -d .venv ]]; then
  echo "缺少 ${API}/.venv；请先运行 scripts/hpc/swu_pip_install.sh / swu_pip_install_mineru.sh" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export REPO_ROOT="${REPO}"
export DATA_DIR="${DATA_DIR:-${API}/data}"
export ENV_FILE
export MISSING_ONLY FORCE PAPER_IDS

_free_gpus_in_partition() {
  local total=0 node show cfg alloc
  while IFS= read -r node; do
    [[ -z "${node}" ]] && continue
    show="$(scontrol show node "${node}")"
    cfg="$(printf '%s\n' "${show}" | sed -n 's/.*CfgTRES=.*gres\/gpu=\([0-9][0-9]*\).*/\1/p' | head -1)"
    alloc="$(printf '%s\n' "${show}" | sed -n 's/.*AllocTRES=.*gres\/gpu=\([0-9][0-9]*\).*/\1/p' | head -1)"
    cfg="${cfg:-0}"
    alloc="${alloc:-0}"
    (( total += cfg > alloc ? cfg - alloc : 0 ))
  done < <(sinfo -p "${PARTITION}" -N -h -o "%N" 2>/dev/null | sort -u)
  printf '%s\n' "${total}"
}

if [[ "${PARSE_SHARDS}" == "auto" ]]; then
  free_gpus="$(_free_gpus_in_partition)"
  if (( free_gpus < 1 )); then
    shards=1
  elif (( free_gpus > MAX_SHARDS )); then
    shards="${MAX_SHARDS}"
  else
    shards="${free_gpus}"
  fi
else
  shards="${PARSE_SHARDS}"
fi

if ! [[ "${shards}" =~ ^[0-9]+$ ]] || (( shards < 1 || shards > MAX_SHARDS )); then
  echo "PARSE_SHARDS 必须是 auto 或 1..${MAX_SHARDS}，当前=${PARSE_SHARDS}" >&2
  exit 1
fi

run_dir="${RUN_DIR:-${DATA_DIR}/hpc_shards/parse_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "${run_dir}"
export SHARD_DIR="${run_dir}"
export SHARDS="${shards}"

.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

from app.config import settings
from app.db import get_db, init_db
from app.services.hpc_pdf_path import resolve_pdf_path


def has_existing_markdown(out_dir: Path) -> bool:
    p = out_dir / "document.md"
    return p.is_file() and p.stat().st_size >= 100


def parsed_pdf_sha256_fast(out_dir: Path) -> str | None:
    p = out_dir / "meta.json"
    if not p.is_file():
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = meta.get("pdf_sha256")
    return str(value) if value else None

init_db()
shards = int(os.environ["SHARDS"])
out_dir = Path(os.environ["SHARD_DIR"])
paper_ids_raw = os.environ.get("PAPER_IDS", "").strip()
if paper_ids_raw:
    ids = [p.strip() for p in paper_ids_raw.split(",") if p.strip()]
else:
    missing_only = os.environ.get("MISSING_ONLY", "1") == "1"
    ids = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, pdf_path, sha256
            FROM papers
            WHERE deleted = 0
              AND pdf_path IS NOT NULL
              AND TRIM(pdf_path) != ''
            ORDER BY id
            """
        ).fetchall()
    for row in rows:
        pid = str(row["id"])
        if resolve_pdf_path(str(row["pdf_path"] or "")) is None:
            continue
        if missing_only:
            out_dir_for_paper = settings.parsed_dir / pid
            if has_existing_markdown(out_dir_for_paper):
                pdf_sha = str(row["sha256"] or "").strip()
                stored_sha = parsed_pdf_sha256_fast(out_dir_for_paper)
                if not (pdf_sha and stored_sha and stored_sha != pdf_sha):
                    continue
        ids.append(pid)

seen: set[str] = set()
deduped: list[str] = []
for pid in ids:
    if pid in seen:
        continue
    seen.add(pid)
    deduped.append(pid)

for idx in range(shards):
    (out_dir / f"shard_{idx + 1:02d}.txt").write_text("", encoding="utf-8")

for n, pid in enumerate(deduped):
    shard = n % shards
    with (out_dir / f"shard_{shard + 1:02d}.txt").open("a", encoding="utf-8") as f:
        f.write(pid + "\n")

(out_dir / "all_ids.txt").write_text("\n".join(deduped) + ("\n" if deduped else ""), encoding="utf-8")
print(f"待解析 paper_id={len(deduped)} shards={shards} out={out_dir}", flush=True)
for idx in range(shards):
    p = out_dir / f"shard_{idx + 1:02d}.txt"
    count = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    print(f"  shard {idx + 1:02d}: {count}", flush=True)
PY

echo "=== submit parse shards partition=${PARTITION} gpus/job=${GPUS_PER_JOB} cpus=${CPUS_PER_TASK} mem=${MEM} time=${TIME} ==="
submitted=0
for shard_file in "${run_dir}"/shard_*.txt; do
  count="$(grep -cve '^[[:space:]]*$' "${shard_file}" || true)"
  [[ "${count}" == "0" ]] && continue
  idx="$(basename "${shard_file}" .txt | sed 's/shard_//')"
  export_arg="ALL,REPO_ROOT=${REPO},DATA_DIR=${DATA_DIR},ENV_FILE=${ENV_FILE},PAPER_IDS_FILE=${shard_file},MISSING_ONLY=0,FORCE=${FORCE},PARSE_SHARD_INDEX=${idx},PARSE_SHARD_COUNT=${shards},PARSE_QUALITY_RETRY_ENABLED=0"
  echo "shard ${idx}: ids=${count} file=${shard_file}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "  DRY_RUN sbatch --partition=${PARTITION} --gres=gpu:${GPUS_PER_JOB} --cpus-per-task=${CPUS_PER_TASK} --mem=${MEM} --time=${TIME} --export=${export_arg} scripts/hpc/submit_parse.swu.slurm"
  else
    jobid="$(
      sbatch --parsable \
        --job-name="zos-parse-${idx}" \
        --partition="${PARTITION}" \
        --gres="gpu:${GPUS_PER_JOB}" \
        --cpus-per-task="${CPUS_PER_TASK}" \
        --mem="${MEM}" \
        --time="${TIME}" \
        --export="${export_arg}" \
        "${REPO}/scripts/hpc/submit_parse.swu.slurm"
    )"
    echo "  submitted job=${jobid}"
    (( submitted += 1 ))
  fi
done

echo "=== submitted=${submitted} run_dir=${run_dir} ==="
echo "查看: squeue -u \$USER"
