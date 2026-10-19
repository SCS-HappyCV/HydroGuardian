# agent_result 可视化快照构建包。
# 本包集中生成风险工作台需要的轻量视图模型，避免 case_persistence.snapshot 直接拼装复杂字段。
from .builder import build_visualization_snapshot

__all__ = ["build_visualization_snapshot"]
