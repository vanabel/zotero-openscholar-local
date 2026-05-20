#!/usr/bin/env bash
# 查看 SWU parse 分片进度、ETA 与近期错误。
# 用法：
#   cd ~/zotero-openscholar-local
#   bash scripts/hpc/parse_progress.swu.sh
#   WATCH=30 bash scripts/hpc/parse_progress.swu.sh
set -euo pipefail

REPO="${REPO_ROOT:-${HOME}/zotero-openscholar-local}"
API="${REPO}/apps/api"
: "${LOG_DIRS:=${API}:${REPO}}"
: "${JOBS:=}"       # 可选：逗号分隔 job id，只看指定作业
: "${RUN_DIR:=}"    # 可选：只看某次 data/hpc_shards/parse_<时间>
: "${WATCH:=0}"     # 秒；0 表示只跑一次
: "${ERROR_LINES:=8}"

export LC_ALL=C LANG=C
unset LANGUAGE 2>/dev/null || true

_run_once() {
  LOG_DIRS="${LOG_DIRS}" JOBS="${JOBS}" RUN_DIR="${RUN_DIR}" ERROR_LINES="${ERROR_LINES}" python3 - <<'PY'
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


LOG_DIRS = [Path(p).expanduser() for p in os.environ.get("LOG_DIRS", "").split(":") if p]
JOBS = {j.strip() for j in os.environ.get("JOBS", "").split(",") if j.strip()}
RUN_DIR = os.environ.get("RUN_DIR", "").strip()
ERROR_LINES = int(os.environ.get("ERROR_LINES", "8"))

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})")
JOB_RE = re.compile(r"zos_parse_(\d+)\.(?:log|err)$")
PAPERS_RE = re.compile(r"parse_batch papers=(\d+)")
SHARD_RE = re.compile(r"shard=([^ ]+) .* ids=(\d+)")
PAPER_IDS_FILE_RE = re.compile(r"PAPER_IDS_FILE=([^ ]+)")
START_RE = re.compile(r"parse_batch paper_id=([0-9a-f]+)")
DONE_RE = re.compile(r"parse_only 完成 paper_id=([0-9a-f]+)")
MINERU_DONE_RE = re.compile(r"parse_one 完成 mode=([^ ]+) md_chars=(\d+)")
CURRENT_CMD_RE = re.compile(r"parse_one 开始 paper_id=([0-9a-f]+)")
ERROR_PATTERNS = (
    "Traceback",
    "OperationalError",
    "database is locked",
    "CUDA out of memory",
    "Name or service not known",
    "ModuleNotFoundError",
    "No module named",
    "退出码=1",
    "退出码=2",
    "ERROR",
    "失败",
)


def parse_ts(line: str) -> datetime | None:
    m = TS_RE.match(line)
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)}.{m.group(2)}", "%Y-%m-%d %H:%M:%S.%f")


def fmt_td(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 0:
        seconds = 0
    return str(timedelta(seconds=int(seconds)))


def discover_logs() -> dict[str, dict[str, Path]]:
    jobs: dict[str, dict[str, Path]] = {}
    for d in LOG_DIRS:
        if not d.is_dir():
            continue
        for p in d.glob("zos_parse_*.log"):
            m = JOB_RE.search(p.name)
            if m and (not JOBS or m.group(1) in JOBS):
                jobs.setdefault(m.group(1), {})["log"] = p
        for p in d.glob("zos_parse_*.err"):
            m = JOB_RE.search(p.name)
            if m and (not JOBS or m.group(1) in JOBS):
                jobs.setdefault(m.group(1), {})["err"] = p
    return jobs


def read_lines(path: Path | None) -> list[str]:
    if not path or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def squeue_states(job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    try:
        out = subprocess.check_output(
            ["squeue", "-h", "-j", ",".join(job_ids), "-o", "%i|%T|%M|%R"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {}
    states: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            states[parts[0].strip()] = f"{parts[1].strip()} {parts[2].strip()} {parts[3].strip()}"
    return states


@dataclass
class Summary:
    job: str
    target: int | None = None
    shard: str = ""
    shard_ids: int | None = None
    started: int = 0
    done: int = 0
    mineru_done: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    current_pid: str = ""
    errors: list[str] | None = None
    log: Path | None = None
    err: Path | None = None
    run_dir: str = ""

    @property
    def remaining(self) -> int | None:
        if self.target is None:
            return None
        return max(self.target - self.done, 0)

    @property
    def eta_seconds(self) -> float | None:
        if not self.first_ts or not self.last_ts or not self.target or self.done <= 0:
            return None
        elapsed = (self.last_ts - self.first_ts).total_seconds()
        rate = self.done / elapsed if elapsed > 0 else 0
        if rate <= 0:
            return None
        return (self.target - self.done) / rate


def summarize(job: str, paths: dict[str, Path]) -> Summary:
    lines = read_lines(paths.get("log")) + read_lines(paths.get("err"))
    s = Summary(job=job, errors=[], log=paths.get("log"), err=paths.get("err"))
    started_ids: list[str] = []
    done_ids: list[str] = []
    error_hits: list[str] = []

    for line in lines:
        ts = parse_ts(line)
        if ts:
            s.first_ts = ts if s.first_ts is None else min(s.first_ts, ts)
            s.last_ts = ts if s.last_ts is None else max(s.last_ts, ts)

        if m := PAPERS_RE.search(line):
            s.target = int(m.group(1))
        if m := SHARD_RE.search(line):
            s.shard = m.group(1)
            s.shard_ids = int(m.group(2))
        if m := PAPER_IDS_FILE_RE.search(line):
            shard_file = Path(m.group(1))
            if shard_file.parent.name.startswith("parse_"):
                s.run_dir = str(shard_file.parent)
        if m := START_RE.search(line):
            started_ids.append(m.group(1))
            s.current_pid = m.group(1)
        if m := CURRENT_CMD_RE.search(line):
            s.current_pid = m.group(1)
        if m := DONE_RE.search(line):
            done_ids.append(m.group(1))
        if MINERU_DONE_RE.search(line):
            s.mineru_done += 1
        if any(p in line for p in ERROR_PATTERNS):
            error_hits.append(line.strip())

    s.started = len(set(started_ids))
    s.done = len(set(done_ids))
    done_set = set(done_ids)
    for pid in reversed(started_ids):
        if pid not in done_set:
            s.current_pid = pid
            break
    s.errors = error_hits[-ERROR_LINES:]
    return s


def main() -> None:
    jobs = discover_logs()
    if not jobs:
        print("未找到 zos_parse_*.log/.err；默认扫描：", ":".join(str(p) for p in LOG_DIRS))
        return

    all_summaries = [summarize(job, paths) for job, paths in sorted(jobs.items())]
    selected_run_dir = RUN_DIR
    if not selected_run_dir:
        run_dirs = sorted({s.run_dir for s in all_summaries if s.run_dir})
        selected_run_dir = run_dirs[-1] if run_dirs else ""
    summaries = [
        s for s in all_summaries
        if (not selected_run_dir or s.run_dir == selected_run_dir)
    ]
    states = squeue_states([s.job for s in summaries])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== parse progress {now} ===")
    if selected_run_dir:
        print(f"RUN_DIR={selected_run_dir}")
    print(f"{'JOB':>8} {'STATE':<28} {'SHARD':<7} {'DONE/TOTAL':>11} {'START':>5} {'ETA':>10} CURRENT")

    total_target = total_done = total_started = 0
    active_first: datetime | None = None
    active_last: datetime | None = None
    for s in summaries:
        target = s.target or 0
        total_target += target
        total_done += s.done
        total_started += s.started
        if s.first_ts:
            active_first = s.first_ts if active_first is None else min(active_first, s.first_ts)
        if s.last_ts:
            active_last = s.last_ts if active_last is None else max(active_last, s.last_ts)
        done_total = f"{s.done}/{s.target if s.target is not None else '?'}"
        state = states.get(s.job, "not in squeue")
        print(
            f"{s.job:>8} {state:<28.28} {s.shard or '-':<7} "
            f"{done_total:>11} {s.started:>5} {fmt_td(s.eta_seconds):>10} {s.current_pid or '-'}"
        )

    agg_eta = None
    if active_first and active_last and total_done > 0 and total_target > 0:
        elapsed = (active_last - active_first).total_seconds()
        rate = total_done / elapsed if elapsed > 0 else 0
        if rate > 0:
            agg_eta = (total_target - total_done) / rate
    print(
        f"\nTOTAL done={total_done}/{total_target or '?'} started={total_started} "
        f"remaining={(total_target - total_done) if total_target else '?'} eta={fmt_td(agg_eta)}"
    )

    print("\n=== recent errors ===")
    any_error = False
    for s in summaries:
        if not s.errors:
            continue
        any_error = True
        print(f"== {s.job} ==")
        for line in s.errors:
            print(line)
    if not any_error:
        print("未发现匹配的错误关键字。")

    print("\n提示：WATCH=30 bash scripts/hpc/parse_progress.swu.sh 可每 30 秒刷新。")


if __name__ == "__main__":
    main()
PY
}

if [[ "${WATCH}" == "0" ]]; then
  _run_once
else
  while true; do
    clear 2>/dev/null || true
    _run_once
    sleep "${WATCH}"
  done
fi
