#!/usr/bin/env bash
# rsync -e 远程 shell（Mac openrsync 只接受单一可执行文件，不能写 "ssh host env ..."）
# rsync 会调用：本脚本 <ssh-host> rsync --server ...
export LC_ALL=C
export LANG=C
unset LANGUAGE 2>/dev/null || true
exec ssh "$@"
