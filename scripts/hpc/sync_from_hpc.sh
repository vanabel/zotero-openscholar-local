#!/usr/bin/env bash
# 超算 → Mac：拉回 app.sqlite / parsed/ / lance/（带 rsync 进度）
# 用法：scripts/hpc/sync_from_hpc.sh {parsed|sqlite|lance|all|help}
# 配置：与上行相同，复制 scripts/hpc/sync_to_hpc.env.example → sync_to_hpc.local.env
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_ENV="${REPO_ROOT}/scripts/hpc/sync_to_hpc.local.env"
if [[ -f "${LOCAL_ENV}" ]]; then
  # shellcheck disable=SC1090
  source "${LOCAL_ENV}"
fi

: "${HPC_SSH:=swu3}"
: "${SYNC_RSYNC_PROGRESS:=1}"
: "${RSYNC_BIN:=}"

HPC_RSYNC_RSH="${REPO_ROOT}/scripts/hpc/hpc_rsync_rsh.sh"
LOCAL_DATA="${REPO_ROOT}/apps/api/data"

_rsync_bin() {
  if [[ -n "${RSYNC_BIN}" && -x "${RSYNC_BIN}" ]]; then
    printf '%s' "${RSYNC_BIN}"
    return
  fi
  if [[ -x /opt/homebrew/bin/rsync ]]; then
    printf '%s' /opt/homebrew/bin/rsync
    return
  fi
  command -v rsync
}

_init_rsync() {
  local bin
  bin="$(_rsync_bin)"
  if [[ ! -x "${HPC_RSYNC_RSH}" ]]; then
    echo "缺少可执行 ${HPC_RSYNC_RSH}（chmod +x）" >&2
    exit 1
  fi
  local args=(-avz)
  if [[ "${SYNC_RSYNC_PROGRESS}" == "1" ]]; then
    if "${bin}" --info=progress2 --dry-run -a /dev/null /dev/null >/dev/null 2>&1; then
      args+=(--info=progress2 --stats)
    else
      args+=(--progress --stats)
      if [[ "${bin}" == /usr/bin/rsync ]]; then
        echo "提示：/usr/bin/rsync（openrsync）无 --info=progress2；可 brew install rsync 后重试（脚本会优先 /opt/homebrew/bin/rsync）" >&2
      fi
    fi
  fi
  RSYNC=("${bin}" "${args[@]}" -e "${HPC_RSYNC_RSH}")
}

_resolve_remote_home() {
  if [[ -n "${HPC_REMOTE_HOME:-}" ]]; then
    printf '%s' "${HPC_REMOTE_HOME}"
    return
  fi
  ssh "${HPC_SSH}" 'printf %s "$HOME"'
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

_remote_data_dir() {
  local repo
  repo="$(_remote_repo)"
  if [[ -n "${DATA_DIR_REMOTE:-}" ]]; then
    case "${DATA_DIR_REMOTE}" in
      "~/"*)
        local home
        home="$(_resolve_remote_home)"
        printf '%s/%s' "${home}" "${DATA_DIR_REMOTE#~/}"
        ;;
      /*) printf '%s' "${DATA_DIR_REMOTE}" ;;
      *) printf '%s/%s' "${repo}" "${DATA_DIR_REMOTE}" ;;
    esac
    return
  fi
  printf '%s/apps/api/data' "${repo}"
}

_cmd_parsed() {
  local remote
  remote="$(_remote_data_dir)"
  mkdir -p "${LOCAL_DATA}/parsed"
  echo "=== rsync parsed/ ← ${HPC_SSH}:${remote}/parsed/ ==="
  "${RSYNC[@]}" "${HPC_SSH}:${remote}/parsed/" "${LOCAL_DATA}/parsed/"
}

_cmd_sqlite() {
  local remote
  remote="$(_remote_data_dir)"
  mkdir -p "${LOCAL_DATA}"
  echo "=== rsync app.sqlite ← ${HPC_SSH}:${remote}/app.sqlite ==="
  "${RSYNC[@]}" "${HPC_SSH}:${remote}/app.sqlite" "${LOCAL_DATA}/app.sqlite"
}

_cmd_lance() {
  local remote
  remote="$(_remote_data_dir)"
  mkdir -p "${LOCAL_DATA}/lance"
  echo "=== rsync lance/ ← ${HPC_SSH}:${remote}/lance/ ==="
  "${RSYNC[@]}" "${HPC_SSH}:${remote}/lance/" "${LOCAL_DATA}/lance/"
}

_usage() {
  cat <<EOF
用法: $(basename "$0") {parsed|sqlite|lance|all|help}

  超算 → Mac 拉回数据（默认 ${HPC_SSH}，见 sync_to_hpc.local.env）

  parsed   parsed/ 目录（解析产物 document.md 等）
  sqlite   app.sqlite
  lance    lance/ 向量库目录
  all      以上三项

Mac rsync：优先 /opt/homebrew/bin/rsync（支持 --info=progress2）；
  否则回退系统 openrsync 的 --progress。可设 RSYNC_BIN= 覆盖。

仓库根目录: pnpm run hpc:pull:parsed
EOF
}

main() {
  local cmd="${1:-help}"
  _init_rsync
  case "${cmd}" in
    parsed) _cmd_parsed ;;
    sqlite) _cmd_sqlite ;;
    lance) _cmd_lance ;;
    all)
      _cmd_sqlite
      _cmd_parsed
      _cmd_lance
      ;;
    help | -h | --help) _usage ;;
    *)
      echo "未知子命令: ${cmd}" >&2
      _usage >&2
      exit 1
      ;;
  esac
}

main "$@"
