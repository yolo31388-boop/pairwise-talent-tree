"""历史入口：实现已迁移到数据驱动的 talent.tree，此处仅做兼容导出。"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from talent.tree import (  # noqa: F401
    DEFAULT_RESET_COOLDOWN,
    POINT_SOURCES,
    TalentError,
    TalentNode,
    TalentTree,
)
