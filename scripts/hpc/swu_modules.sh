# 西南大学 GridView 超算：登录/计算节点统一加载模块
# 用法：source scripts/hpc/swu_modules.sh
# 查看可用：module avail apps/python apps/cuda

_SWU_MOD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck disable=SC1091
source "${_SWU_MOD_DIR}/swu_locale.sh"

# SLURM（admin03 / ssh swu3；admin01 无 sbatch）
export PATH=/opt/gridview/slurm/bin:${PATH}

# 与 submit_vectors.swu.slurm 保持一致
module load apps/python/3.12.3
module load apps/cuda/12.2

# 可选：编译扩展时
# module load compiler/gcc/12.2.0
