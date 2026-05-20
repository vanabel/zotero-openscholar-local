# 西南大学超算：避免 perl/rsync「Setting locale failed」（Mac 常传入未安装的 C.UTF-8）
# 用法：source scripts/hpc/swu_locale.sh
# swu_modules.sh 已自动 source。登录节点 ~/.bashrc 须加存在判断（先 sync code 再有文件）：
#   [ -f ~/zotero-openscholar-local/scripts/hpc/swu_locale.sh ] && \
#     source ~/zotero-openscholar-local/scripts/hpc/swu_locale.sh

export LC_ALL=C
export LANG=C
unset LANGUAGE 2>/dev/null || true
