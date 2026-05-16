"""pytest：将 tests 目录加入 import 路径以便引用 p0_helpers 等模块。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
