# 场景样本加载辅助模块。
# 本模块负责磁盘查找和 JSON 解析，让 LangGraph 节点专注控制流和状态流转。

from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict

from state import AgentState


# 承载样本及其来源信息，后续用于 trace 摘要。
@dataclass(frozen=True)
class LoadedSceneSample:
    sample: Dict[str, Any]
    source: str
    source_path: Path | None = None


# 当命中的样本文件存在但不能安全使用时抛出。
class SceneSampleLoadError(ValueError):
    # 将路径和原因分开保存，便于节点错误暴露结构化数据。
    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


# 从配置的样本目录加载预处理后的 SceneTensorSample。
def load_scene_sample_from_disk(state: AgentState, sample_dir: Path) -> LoadedSceneSample | None:
    # scene_id 是主查找键；sample_id 作为早期 demo 命名不稳定时的兼容兜底。
    candidates = [
        sample_dir / f"{state['scene_id']}.json",
        sample_dir / f"{state['sample_id']}.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    sample = json.load(handle)
            except JSONDecodeError as exc:
                raise SceneSampleLoadError(path, f"invalid JSON: {exc.msg}") from exc

            # 如果命中的文件损坏，就直接失败，避免静默回退 demo 并掩盖数据问题。
            if not isinstance(sample, dict):
                raise SceneSampleLoadError(path, "sample root must be a JSON object")

            # 在保留上游预处理字段的同时，补齐 agent 链路需要的默认元数据。
            sample.setdefault("sample_id", state["sample_id"])
            sample.setdefault(
                "text",
                state["selected_program"].get("source_text", state["task_text"]),
            )
            sample.setdefault("program", state["selected_program"])
            return LoadedSceneSample(sample=sample, source="disk", source_path=path)
    return None
