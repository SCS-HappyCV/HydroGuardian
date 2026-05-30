from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import torch

from .schema import (
    ProgramBundle,
    ProgramLike,
    RelationClause,
    bundle_from_dict,
    program_from_dict,
)


def _as_jsonable(value: Any) -> Any:
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu()
        if tensor.ndim == 0:
            return tensor.item()
        return tensor.tolist()
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return _as_jsonable(value.to_dict())
        return _as_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _as_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_jsonable(item) for item in value]
    if hasattr(value, "to_dict"):
        return _as_jsonable(value.to_dict())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _select_value(value: Any, batch_index: int = 0) -> Any:
    if isinstance(value, torch.Tensor):
        if value.ndim == 0:
            return value
        if value.shape[0] > batch_index:
            return value[batch_index]
        return value
    if isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
        if len(value) > batch_index:
            return value[batch_index]
        return value[-1] if value else None
    return value


def _scalar(value: Any, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu().reshape(-1)
        if tensor.numel() == 0:
            return float(default)
        return float(tensor[0].item())
    try:
        return float(value)
    except Exception:
        return float(default)


def _tensor_1d(value: Any) -> Optional[torch.Tensor]:
    if value is None:
        return None
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu()
        if tensor.ndim == 0:
            tensor = tensor.unsqueeze(0)
        return tensor.float().reshape(-1)
    return torch.as_tensor(value, dtype=torch.float32).reshape(-1)


def _tensor_bool_mask(value: Any, length: Optional[int] = None) -> Optional[torch.Tensor]:
    if value is None:
        return None
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu()
        if tensor.ndim == 0:
            tensor = tensor.unsqueeze(0)
        mask = tensor.bool().reshape(-1)
    else:
        mask = torch.as_tensor(value, dtype=torch.bool).reshape(-1)
    if length is not None:
        if mask.numel() < length:
            pad = torch.zeros(length - mask.numel(), dtype=torch.bool)
            mask = torch.cat([mask, pad], dim=0)
        elif mask.numel() > length:
            mask = mask[:length]
    return mask


def _format_relation(relation: RelationClause) -> str:
    if relation.type in {"near", "adjacent", "along"} and relation.distance_m is not None:
        return f"relation: {relation.type} {relation.reference} within {float(relation.distance_m):.1f}m"
    if relation.type in {"above", "below"} and relation.margin_m is not None:
        return f"relation: {relation.type} {relation.reference} by {float(relation.margin_m):.1f}m"
    return f"relation: {relation.type} {relation.reference}"


def _program_summary(program: ProgramLike) -> List[str]:
    lines = [f"program: {program.to_canonical_text()}"]
    lines.append(f"target: {program.target}")
    for attribute in getattr(program, "attributes", []):
        lines.append(f"attribute: {attribute}")
    for relation in getattr(program, "relations", []):
        lines.append(_format_relation(relation))
    for negative in getattr(program, "negatives", []):
        lines.append(f"negative: not {negative}")
    return lines


def _mask_mean(mask: Optional[torch.Tensor], region_mask: torch.Tensor, fallback_mask: torch.Tensor) -> float:
    if mask is None:
        return 0.0
    values = mask.detach().cpu().float().reshape(-1)
    if values.numel() == 0:
        return 0.0
    region = region_mask.reshape(-1).bool()
    if region.any():
        return float(values[region].mean().item())
    fallback = fallback_mask.reshape(-1).bool()
    if fallback.any():
        return float(values[fallback].mean().item())
    return float(values.mean().item())


def _point_bounds(points_xyz: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    if points_xyz.ndim == 1:
        if points_xyz.numel() == 3:
            points_xyz = points_xyz.view(1, 3)
        else:
            points_xyz = points_xyz.reshape(1, -1)
    elif points_xyz.ndim > 2:
        points_xyz = points_xyz.reshape(points_xyz.shape[0], -1)
    if points_xyz.shape[-1] < 3:
        pad_width = 3 - points_xyz.shape[-1]
        pad = torch.zeros((points_xyz.shape[0], pad_width), dtype=points_xyz.dtype, device=points_xyz.device)
        points_xyz = torch.cat([points_xyz, pad], dim=-1)
    elif points_xyz.shape[-1] > 3:
        points_xyz = points_xyz[:, :3]
    centroid = points_xyz.mean(dim=0)
    centered = points_xyz - centroid
    if points_xyz.shape[0] >= 2:
        covariance = centered.t().mm(centered) / max(points_xyz.shape[0] - 1, 1)
    else:
        covariance = torch.eye(3, dtype=points_xyz.dtype, device=points_xyz.device) * 1e-6
    try:
        eigenvalues, eigenvectors = torch.linalg.eigh(covariance)
        order = torch.argsort(eigenvalues, descending=True)
        eigenvectors = eigenvectors[:, order]
        projected = centered @ eigenvectors[:, :2]
        span = projected.max(dim=0).values - projected.min(dim=0).values
        if span.numel() < 2:
            span = torch.cat([span, span.new_zeros(2 - span.numel())], dim=0)
    except Exception:
        span = points_xyz.max(dim=0).values - points_xyz.min(dim=0).values
        span = span[:2]
        if span.ndim == 0:
            span = span.unsqueeze(0)
        if span.numel() < 2:
            span = torch.cat([span, span.new_zeros(2 - span.numel())], dim=0)
    bbox_min = points_xyz.min(dim=0).values
    bbox_max = points_xyz.max(dim=0).values
    return centroid, bbox_min, bbox_max, span


def _region_summary_text(
    program: ProgramLike,
    point_count: int,
    support: float,
    elongation: float,
    score: float,
    is_no_target: bool,
) -> str:
    prefix = "no-target" if is_no_target else program.target
    return (
        f"{prefix} region: points={point_count}, support={support:.2f}, "
        f"elongation={elongation:.2f}, score={score:.2f}"
    )


def _estimate_radius(points_xyz: torch.Tensor, active_indices: torch.Tensor, scale: float, min_radius: float) -> float:
    active_count = int(active_indices.numel())
    if active_count <= 1:
        extent = points_xyz.max(dim=0).values - points_xyz.min(dim=0).values
        diag = float(extent.norm().item())
        return max(min_radius, diag / max(active_count + 1, 2))

    active_xyz = points_xyz[active_indices].float()
    sample_count = min(active_count, 128)
    sample_positions = torch.linspace(0, active_count - 1, steps=sample_count).long()
    sample_xyz = active_xyz[sample_positions]
    dist = torch.cdist(sample_xyz, sample_xyz)
    dist.fill_diagonal_(float("inf"))
    nearest = dist.min(dim=1).values
    finite = nearest[torch.isfinite(nearest) & (nearest > 0)]
    if finite.numel() > 0:
        median_nn = float(finite.median().item())
    else:
        extent = points_xyz.max(dim=0).values - points_xyz.min(dim=0).values
        median_nn = float(extent.norm().item()) / max(active_count ** (1.0 / 3.0), 1.0)

    extent = points_xyz.max(dim=0).values - points_xyz.min(dim=0).values
    diag = float(extent.norm().item())
    density_radius = diag / max(active_count ** (1.0 / 3.0) * 12.0, 1.0)
    radius = max(min_radius, median_nn * scale, density_radius)
    if not math.isfinite(radius) or radius <= 0:
        radius = max(min_radius, diag / 50.0 if diag > 0 else 1.0)
    return float(radius)


def _cluster_active_points(
    points_xyz: torch.Tensor,
    active_indices: torch.Tensor,
    radius: float,
) -> List[List[int]]:
    active_count = int(active_indices.numel())
    if active_count == 0:
        return []
    if active_count == 1:
        return [[0]]

    active_xyz = points_xyz[active_indices].float()
    base = active_xyz.min(dim=0).values
    voxel_size = max(radius, 1e-6)
    voxel_coords = torch.floor((active_xyz - base) / voxel_size).long()
    voxel_map: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for local_idx, coord in enumerate(voxel_coords.tolist()):
        voxel_map[tuple(int(c) for c in coord)].append(local_idx)

    parent = list(range(active_count))
    rank = [0 for _ in range(active_count)]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            return
        if rank[root_left] < rank[root_right]:
            parent[root_left] = root_right
        elif rank[root_left] > rank[root_right]:
            parent[root_right] = root_left
        else:
            parent[root_right] = root_left
            rank[root_left] += 1

    for local_idx, coord in enumerate(voxel_coords.tolist()):
        coord_tuple = tuple(int(c) for c in coord)
        for offset in itertools.product((-1, 0, 1), repeat=3):
            neighbor = (coord_tuple[0] + offset[0], coord_tuple[1] + offset[1], coord_tuple[2] + offset[2])
            for candidate_idx in voxel_map.get(neighbor, []):
                if candidate_idx <= local_idx:
                    continue
                distance = float(torch.dist(active_xyz[local_idx], active_xyz[candidate_idx]).item())
                if distance <= radius:
                    union(local_idx, candidate_idx)

    groups: Dict[int, List[int]] = defaultdict(list)
    for local_idx in range(active_count):
        groups[find(local_idx)].append(local_idx)
    return list(groups.values())


def _region_stats(
    points_xyz: torch.Tensor,
    mask_values: torch.Tensor,
    valid_mask: torch.Tensor,
    region_local_indices: List[int],
    active_indices: torch.Tensor,
    region_id: str,
    program: ProgramLike,
    selected_verifier_score: float,
    selected_candidate_is_no_target: bool,
    max_points_in_pack: int,
) -> Dict[str, Any]:
    region_global_indices = active_indices[torch.as_tensor(region_local_indices, dtype=torch.long)]
    region_xyz = points_xyz[region_global_indices].float()
    region_mask = mask_values[region_global_indices].float()
    region_valid = valid_mask[region_global_indices].bool()
    if region_valid.any():
        region_xyz = region_xyz[region_valid]
        region_mask = region_mask[region_valid]
        region_global_indices = region_global_indices[region_valid]

    point_count = int(region_xyz.shape[0])
    if region_xyz.ndim == 1:
        region_xyz = region_xyz.view(1, -1)
    if region_mask.ndim == 0:
        region_mask = region_mask.view(1)
    if region_valid.ndim == 0:
        region_valid = region_valid.view(1)

    centroid = region_xyz.mean(dim=0)
    bbox_min = region_xyz.min(dim=0).values
    bbox_max = region_xyz.max(dim=0).values
    span_xyz = bbox_max - bbox_min
    span_xyz = torch.nan_to_num(span_xyz, nan=0.0, posinf=0.0, neginf=0.0)

    centroid_, bbox_min_, bbox_max_, span_pca = _point_bounds(region_xyz)
    length = float(span_pca[0].item()) if span_pca.numel() > 0 else float(span_xyz.max().item())
    width = float(span_pca[1].item()) if span_pca.numel() > 1 else float(span_xyz.min().item())
    length = max(length, 0.0)
    width = max(width, 0.0)
    area = float(length * width)
    thickness = float(span_xyz.min().item()) if span_xyz.numel() > 0 else 0.0
    elongation = float(length / max(width, 1e-6)) if width > 0 else float(length)
    compactness = float(point_count / max(area * max(thickness, 1e-3), 1e-6))
    support = float(region_mask.mean().item()) if region_mask.numel() > 0 else 0.0
    score = float(0.7 * support + 0.3 * selected_verifier_score)
    summary = _region_summary_text(
        program=program,
        point_count=point_count,
        support=support,
        elongation=elongation,
        score=score,
        is_no_target=selected_candidate_is_no_target,
    )
    point_indices = region_global_indices.detach().cpu().tolist()
    if len(point_indices) > max_points_in_pack:
        point_indices = point_indices[:max_points_in_pack]

    return {
        "region_id": region_id,
        "point_count": point_count,
        "score": score,
        "support": support,
        "centroid": centroid_.detach().cpu().tolist(),
        "bbox_min": bbox_min_.detach().cpu().tolist(),
        "bbox_max": bbox_max_.detach().cpu().tolist(),
        "span_xyz": span_xyz.detach().cpu().tolist(),
        "area": area,
        "length": length,
        "width": width,
        "thickness": thickness,
        "elongation": elongation,
        "compactness": compactness,
        "point_indices": point_indices,
        "summary": summary,
    }


@dataclass
class EvidenceCompilerConfig:
    mask_threshold: float = 0.5
    min_region_points: int = 12
    max_regions: int = 5
    max_points_in_region: int = 256
    radius_scale: float = 1.8
    min_radius: float = 1e-3
    review_threshold: float = 0.55
    abstain_threshold: float = 0.55
    no_target_threshold: float = 0.55
    fallback_fraction: float = 0.02
    support_threshold: float = 0.45


@dataclass
class CandidateRegion:
    region_id: str
    point_count: int
    score: float
    support: float
    centroid: List[float]
    bbox_min: List[float]
    bbox_max: List[float]
    span_xyz: List[float]
    area: float
    length: float
    width: float
    thickness: float
    elongation: float
    compactness: float
    point_indices: List[int] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "point_count": int(self.point_count),
            "score": float(self.score),
            "support": float(self.support),
            "centroid": list(self.centroid),
            "bbox_min": list(self.bbox_min),
            "bbox_max": list(self.bbox_max),
            "span_xyz": list(self.span_xyz),
            "area": float(self.area),
            "length": float(self.length),
            "width": float(self.width),
            "thickness": float(self.thickness),
            "elongation": float(self.elongation),
            "compactness": float(self.compactness),
            "point_indices": list(self.point_indices),
            "summary": self.summary,
        }


@dataclass
class EvidencePack:
    status: str
    target_hit: bool
    decision_kind: str
    review_required: bool
    confidence: float
    confidence_components: Dict[str, float]
    selected_candidate_idx: int
    selected_candidate_is_no_target: bool
    selected_candidate_score: float
    selected_candidate_posterior: float
    selected_verifier_score: float
    posterior_no_target_mass: float
    abstain_probability: float
    selected_mask_mass: float
    selected_mask_peak: float
    mask_selection_mode: str
    candidate_regions: List[CandidateRegion] = field(default_factory=list)
    evidence_summary: List[str] = field(default_factory=list)
    clause_support: Dict[str, float] = field(default_factory=dict)
    failure_reason: Optional[str] = None
    sample_id: str = ""
    region_id: str = ""
    area_id: str = ""
    task_type: str = ""
    text: str = ""
    program_text: str = ""
    program_schema_mode: str = ""
    program_version: str = ""
    program_dict: Dict[str, Any] = field(default_factory=dict)
    selected_program_text: str = ""
    selected_program_dict: Dict[str, Any] = field(default_factory=dict)
    raw_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "target_hit": bool(self.target_hit),
            "decision_kind": self.decision_kind,
            "review_required": bool(self.review_required),
            "confidence": float(self.confidence),
            "confidence_components": _as_jsonable(self.confidence_components),
            "selected_candidate_idx": int(self.selected_candidate_idx),
            "selected_candidate_is_no_target": bool(self.selected_candidate_is_no_target),
            "selected_candidate_score": float(self.selected_candidate_score),
            "selected_candidate_posterior": float(self.selected_candidate_posterior),
            "selected_verifier_score": float(self.selected_verifier_score),
            "posterior_no_target_mass": float(self.posterior_no_target_mass),
            "abstain_probability": float(self.abstain_probability),
            "selected_mask_mass": float(self.selected_mask_mass),
            "selected_mask_peak": float(self.selected_mask_peak),
            "mask_selection_mode": self.mask_selection_mode,
            "candidate_regions": [region.to_dict() for region in self.candidate_regions],
            "evidence_summary": list(self.evidence_summary),
            "clause_support": _as_jsonable(self.clause_support),
            "failure_reason": self.failure_reason,
            "sample_id": self.sample_id,
            "region_id": self.region_id,
            "area_id": self.area_id,
            "task_type": self.task_type,
            "text": self.text,
            "program_text": self.program_text,
            "program_schema_mode": self.program_schema_mode,
            "program_version": self.program_version,
            "program_dict": _as_jsonable(self.program_dict),
            "selected_program_text": self.selected_program_text,
            "selected_program_dict": _as_jsonable(self.selected_program_dict),
            "raw_trace": _as_jsonable(self.raw_trace),
        }


class EvidenceCompiler:
    def __init__(self, config: Optional[EvidenceCompilerConfig] = None) -> None:
        self.config = config or EvidenceCompilerConfig()

    def compile(self, sample: Mapping[str, Any], outputs: Mapping[str, Any], batch_index: int = 0) -> EvidencePack:
        try:
            program, selected_program_dict, selected_program_text = self._resolve_program(sample, outputs, batch_index)
        except Exception:
            program = program_from_dict(
                {
                    "program_schema_mode": "field",
                    "program_version": "unknown",
                    "target": "others",
                    "target_label_ids": [],
                    "attributes": [],
                    "relations": [],
                    "negatives": [],
                    "negative_label_ids": [],
                    "evidence": [],
                    "metadata": {},
                    "source_text": "",
                }
            )
            selected_program_dict = program.to_dict()
            selected_program_text = program.to_canonical_text()
        points_xyz = self._sample_tensor(sample, "points_xyz", batch_index)
        valid_mask = self._sample_mask(sample, points_xyz, batch_index)
        selected_mask = self._output_tensor(outputs, "selected_program_mask", batch_index)
        if selected_mask is None:
            selected_mask = self._output_tensor(outputs, "final_program_mask", batch_index)
        if selected_mask is None:
            selected_mask = self._output_tensor(outputs, "program_mask_logits", batch_index)
        if selected_mask is None:
            selected_mask = self._output_tensor(outputs, "mask_logits", batch_index)
        if selected_mask is None or points_xyz is None:
            return self._failure_pack(
                sample=sample,
                program=program,
                selected_program_dict=selected_program_dict,
                selected_program_text=selected_program_text,
                outputs=outputs,
                batch_index=batch_index,
                failure_reason="execution_failed",
            )

        selected_mask = self._mask_to_prob(selected_mask)
        selected_mask = selected_mask.reshape(-1)
        if valid_mask is None:
            valid_mask = torch.ones(selected_mask.shape[0], dtype=torch.bool)
        else:
            valid_mask = valid_mask.reshape(-1).bool()
        valid_mask = valid_mask[: selected_mask.shape[0]]
        if valid_mask.numel() < selected_mask.numel():
            pad = torch.zeros(selected_mask.numel() - valid_mask.numel(), dtype=torch.bool)
            valid_mask = torch.cat([valid_mask, pad], dim=0)

        selected_mask = selected_mask[: valid_mask.numel()]
        valid_points = valid_mask.bool()
        mask_mass = float(selected_mask[valid_points].mean().item()) if valid_points.any() else float(selected_mask.mean().item())
        mask_peak = float(selected_mask[valid_points].max().item()) if valid_points.any() else float(selected_mask.max().item())
        active_mask = (selected_mask >= self.config.mask_threshold) & valid_points
        active_indices = torch.nonzero(active_mask, as_tuple=False).flatten()
        if active_indices.numel() == 0 and valid_points.any():
            fallback_count = max(1, min(int(valid_points.sum().item()), max(self.config.min_region_points, int(valid_points.sum().item() * self.config.fallback_fraction))))
            topk = torch.topk(selected_mask[valid_points], k=fallback_count).indices
            valid_indices = torch.nonzero(valid_points, as_tuple=False).flatten()
            active_indices = valid_indices[topk]
            active_mask = torch.zeros_like(valid_points)
            active_mask[active_indices] = True

        selected_candidate_idx = int(self._scalar_output(outputs, "selected_candidate_idx", batch_index, default=0.0))
        selected_candidate_is_no_target = bool(self._bool_output(outputs, "selected_candidate_is_no_target", batch_index, default=False))
        selected_candidate_score = self._score_from_outputs(outputs, "candidate_scores", batch_index, selected_candidate_idx, default=0.0)
        selected_candidate_posterior = self._score_from_outputs(outputs, "candidate_posterior_scores", batch_index, selected_candidate_idx, default=0.0)
        selected_verifier_score = self._scalar_output(outputs, "selected_verifier_score", batch_index, default=0.0)
        posterior_no_target_mass = self._scalar_output(outputs, "posterior_no_target_mass", batch_index, default=0.0)
        abstain_probability = self._scalar_from_logits(outputs, "abstain_logits", batch_index, default=0.0)
        mask_selection_mode = str(
            _select_value(outputs.get("mask_selection_mode"), batch_index) or "latent_posterior_marginalization"
        )

        candidate_regions = self._build_regions(
            points_xyz=points_xyz,
            selected_mask=selected_mask,
            valid_mask=valid_points,
            active_indices=active_indices,
            program=program,
            outputs=outputs,
            batch_index=batch_index,
            selected_verifier_score=selected_verifier_score,
            selected_candidate_is_no_target=selected_candidate_is_no_target,
        )

        clause_support = self._clause_support(
            outputs=outputs,
            selected_mask=selected_mask,
            valid_mask=valid_points,
            active_mask=active_mask,
            batch_index=batch_index,
        )

        confidence_components = self._confidence_components(
            selected_verifier_score=selected_verifier_score,
            posterior_no_target_mass=posterior_no_target_mass,
            abstain_probability=abstain_probability,
            mask_mass=mask_mass,
            mask_peak=mask_peak,
            clause_support=clause_support,
            selected_candidate_is_no_target=selected_candidate_is_no_target,
            candidate_regions=candidate_regions,
        )

        decision_kind = "no_target" if selected_candidate_is_no_target else "positive"
        confidence = confidence_components["decision_confidence"]
        review_required = (
            abstain_probability >= self.config.abstain_threshold
            or confidence < self.config.review_threshold
            or not candidate_regions
        )
        if selected_candidate_is_no_target and confidence >= self.config.no_target_threshold:
            status = "no_target"
        elif review_required:
            status = "review_required"
        else:
            status = "success"

        target_hit = status == "success" and decision_kind == "positive"
        if selected_candidate_is_no_target and candidate_regions and status == "success":
            target_hit = False

        evidence_summary = self._evidence_summary(
            program=program,
            candidate_regions=candidate_regions,
            selected_candidate_idx=selected_candidate_idx,
            selected_candidate_score=selected_candidate_score,
            selected_candidate_posterior=selected_candidate_posterior,
            selected_verifier_score=selected_verifier_score,
            posterior_no_target_mass=posterior_no_target_mass,
            abstain_probability=abstain_probability,
            selected_candidate_is_no_target=selected_candidate_is_no_target,
            mask_mass=mask_mass,
        )

        sample_id = str(_select_value(sample.get("sample_id"), batch_index) if isinstance(sample, Mapping) and "sample_id" in sample else "")
        region_id = str(_select_value(sample.get("region_id"), batch_index) if isinstance(sample, Mapping) and "region_id" in sample else "")
        area_id = str(_select_value(sample.get("area_id"), batch_index) if isinstance(sample, Mapping) and "area_id" in sample else "")
        task_type = str(_select_value(sample.get("task_type"), batch_index) if isinstance(sample, Mapping) and "task_type" in sample else "")
        text = str(_select_value(sample.get("text"), batch_index) if isinstance(sample, Mapping) and "text" in sample else "")

        raw_trace = self._raw_trace(
            outputs=outputs,
            batch_index=batch_index,
            selected_candidate_idx=selected_candidate_idx,
            selected_candidate_score=selected_candidate_score,
            selected_candidate_posterior=selected_candidate_posterior,
            selected_verifier_score=selected_verifier_score,
            posterior_no_target_mass=posterior_no_target_mass,
            abstain_probability=abstain_probability,
            mask_mass=mask_mass,
            mask_peak=mask_peak,
            active_points=int(active_indices.numel()),
            valid_points=int(valid_points.sum().item()),
            confidence_components=confidence_components,
        )

        return EvidencePack(
            status=status,
            target_hit=target_hit,
            decision_kind=decision_kind,
            review_required=review_required,
            confidence=confidence,
            confidence_components=confidence_components,
            selected_candidate_idx=selected_candidate_idx,
            selected_candidate_is_no_target=selected_candidate_is_no_target,
            selected_candidate_score=selected_candidate_score,
            selected_candidate_posterior=selected_candidate_posterior,
            selected_verifier_score=selected_verifier_score,
            posterior_no_target_mass=posterior_no_target_mass,
            abstain_probability=abstain_probability,
            selected_mask_mass=mask_mass,
            selected_mask_peak=mask_peak,
            mask_selection_mode=mask_selection_mode,
            candidate_regions=candidate_regions,
            evidence_summary=evidence_summary,
            clause_support=clause_support,
            failure_reason=None if status != "review_required" else "low_confidence_or_abstained",
            sample_id=sample_id,
            region_id=region_id,
            area_id=area_id,
            task_type=task_type,
            text=text,
            program_text=program.to_canonical_text(),
            program_schema_mode=str(program.metadata.get("program_schema_mode", "")),
            program_version=str(program.metadata.get("program_version", "")),
            program_dict=program.to_dict() if hasattr(program, "to_dict") else _as_jsonable(selected_program_dict),
            selected_program_text=selected_program_text,
            selected_program_dict=_as_jsonable(selected_program_dict),
            raw_trace=raw_trace,
        )

    def compile_batch(self, batch: Mapping[str, Any], outputs: Mapping[str, Any]) -> List[EvidencePack]:
        batch_size = self._batch_size(batch, outputs)
        return [self.compile(batch, outputs, batch_index=index) for index in range(batch_size)]

    def _build_regions(
        self,
        points_xyz: torch.Tensor,
        selected_mask: torch.Tensor,
        valid_mask: torch.Tensor,
        active_indices: torch.Tensor,
        program: ProgramLike,
        outputs: Mapping[str, Any],
        batch_index: int,
        selected_verifier_score: float,
        selected_candidate_is_no_target: bool,
    ) -> List[CandidateRegion]:
        if active_indices.numel() == 0:
            return []
        radius = _estimate_radius(points_xyz, active_indices, self.config.radius_scale, self.config.min_radius)
        groups = _cluster_active_points(points_xyz, active_indices, radius)
        groups = sorted(groups, key=len, reverse=True)
        groups = [group for group in groups if len(group) >= self.config.min_region_points]
        if not groups and active_indices.numel() > 0:
            groups = [list(range(int(active_indices.numel())))]

        region_mask = torch.zeros_like(valid_mask, dtype=torch.bool)
        regions: List[CandidateRegion] = []
        for region_idx, group in enumerate(groups[: self.config.max_regions]):
            region_mask.zero_()
            region_mask[active_indices[torch.as_tensor(group, dtype=torch.long)]] = True
            stats = _region_stats(
                points_xyz=points_xyz,
                mask_values=selected_mask,
                valid_mask=valid_mask,
                region_local_indices=group,
                active_indices=active_indices,
                region_id=f"r_{region_idx + 1:03d}",
                program=program,
                selected_verifier_score=selected_verifier_score,
                selected_candidate_is_no_target=selected_candidate_is_no_target,
                max_points_in_pack=self.config.max_points_in_region,
            )
            regions.append(
                CandidateRegion(
                    region_id=str(stats["region_id"]),
                    point_count=int(stats["point_count"]),
                    score=float(stats["score"]),
                    support=float(stats["support"]),
                    centroid=list(stats["centroid"]),
                    bbox_min=list(stats["bbox_min"]),
                    bbox_max=list(stats["bbox_max"]),
                    span_xyz=list(stats["span_xyz"]),
                    area=float(stats["area"]),
                    length=float(stats["length"]),
                    width=float(stats["width"]),
                    thickness=float(stats["thickness"]),
                    elongation=float(stats["elongation"]),
                    compactness=float(stats["compactness"]),
                    point_indices=list(stats["point_indices"]),
                    summary=str(stats["summary"]),
                )
            )
        return regions

    def _clause_support(
        self,
        outputs: Mapping[str, Any],
        selected_mask: torch.Tensor,
        valid_mask: torch.Tensor,
        active_mask: torch.Tensor,
        batch_index: int,
    ) -> Dict[str, float]:
        selected_region = active_mask.bool()
        fallback_region = valid_mask.bool()
        if not selected_region.any():
            selected_region = fallback_region
        support = {
            "selected_mask_mass": float(selected_mask[valid_mask].mean().item()) if valid_mask.any() else float(selected_mask.mean().item()),
            "selected_mask_peak": float(selected_mask[selected_region].mean().item()) if selected_region.any() else float(selected_mask.max().item()),
            "class": self._region_mean(outputs, "selected_class_mask", "class_mask", batch_index, selected_region, fallback_region),
            "attribute": self._region_mean(outputs, "selected_attribute_mask", "attribute_mask", batch_index, selected_region, fallback_region),
            "relation": self._region_mean(outputs, "selected_relation_mask", "relation_mask", batch_index, selected_region, fallback_region),
            "negative": self._region_mean(outputs, "selected_negative_mask", "negative_mask", batch_index, selected_region, fallback_region),
            "keep": self._region_mean(outputs, "selected_keep_mask", "keep_mask", batch_index, selected_region, fallback_region),
            "reference": self._region_mean(outputs, "selected_reference_mask", "reference_mask", batch_index, selected_region, fallback_region),
            "attribute_evidence": self._region_mean(outputs, "selected_attribute_evidence_map", "attribute_evidence_map", batch_index, selected_region, fallback_region),
            "relation_evidence": self._region_mean(outputs, "selected_relation_evidence_map", "relation_evidence_map", batch_index, selected_region, fallback_region),
        }
        support["positive_clause_support"] = float(
            0.45 * support["class"]
            + 0.25 * support["attribute"]
            + 0.15 * support["relation"]
            + 0.15 * support["reference"]
        )
        support["negative_clause_conflict"] = float(max(0.0, 1.0 - support["keep"]) * 0.6 + support["negative"] * 0.4)
        return support

    def _confidence_components(
        self,
        selected_verifier_score: float,
        posterior_no_target_mass: float,
        abstain_probability: float,
        mask_mass: float,
        mask_peak: float,
        clause_support: Dict[str, float],
        selected_candidate_is_no_target: bool,
        candidate_regions: Sequence[CandidateRegion],
    ) -> Dict[str, float]:
        region_support = candidate_regions[0].support if candidate_regions else 0.0
        evidence_score = float(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * clause_support["positive_clause_support"]
                    + 0.30 * region_support
                    + 0.15 * mask_peak
                    + 0.10 * clause_support["keep"],
                ),
            )
        )
        consistency_score = float(max(0.0, min(1.0, 1.0 - clause_support["negative_clause_conflict"])))
        positive_confidence = float(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * selected_verifier_score
                    + 0.25 * evidence_score
                    + 0.20 * consistency_score
                    + 0.10 * (1.0 - abstain_probability),
                ),
            )
        )
        no_target_confidence = float(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * posterior_no_target_mass
                    + 0.25 * abstain_probability
                    + 0.20 * (1.0 - mask_mass)
                    + 0.10 * (1.0 - evidence_score),
                ),
            )
        )
        decision_confidence = no_target_confidence if selected_candidate_is_no_target else positive_confidence
        return {
            "evidence_score": evidence_score,
            "consistency_score": consistency_score,
            "positive_confidence": positive_confidence,
            "no_target_confidence": no_target_confidence,
            "decision_confidence": decision_confidence,
        }

    def _evidence_summary(
        self,
        program: ProgramLike,
        candidate_regions: Sequence[CandidateRegion],
        selected_candidate_idx: int,
        selected_candidate_score: float,
        selected_candidate_posterior: float,
        selected_verifier_score: float,
        posterior_no_target_mass: float,
        abstain_probability: float,
        selected_candidate_is_no_target: bool,
        mask_mass: float,
    ) -> List[str]:
        lines = _program_summary(program)
        lines.append(
            f"selection: idx={selected_candidate_idx}, score={selected_candidate_score:.3f}, "
            f"posterior={selected_candidate_posterior:.3f}, verifier={selected_verifier_score:.3f}"
        )
        lines.append(
            f"decision: no_target={str(selected_candidate_is_no_target).lower()}, "
            f"posterior_no_target_mass={posterior_no_target_mass:.3f}, "
            f"abstain_prob={abstain_probability:.3f}, mask_mass={mask_mass:.3f}"
        )
        for region in candidate_regions[: min(len(candidate_regions), 3)]:
            lines.append(f"region {region.region_id}: {region.summary}")
        return lines

    def _raw_trace(
        self,
        outputs: Mapping[str, Any],
        batch_index: int,
        selected_candidate_idx: int,
        selected_candidate_score: float,
        selected_candidate_posterior: float,
        selected_verifier_score: float,
        posterior_no_target_mass: float,
        abstain_probability: float,
        mask_mass: float,
        mask_peak: float,
        active_points: int,
        valid_points: int,
        confidence_components: Dict[str, float],
    ) -> Dict[str, Any]:
        candidate_scores = self._tensor_list(outputs, "candidate_scores", batch_index)
        candidate_posterior_scores = self._tensor_list(outputs, "candidate_posterior_scores", batch_index)
        verification_scores = self._tensor_list(outputs, "verification_scores", batch_index)
        no_target_scores = self._tensor_list(outputs, "no_target_scores", batch_index)
        candidate_program_texts = self._value_list(outputs, "selected_program_texts", batch_index)
        return {
            "selected_candidate_idx": selected_candidate_idx,
            "selected_candidate_score": selected_candidate_score,
            "selected_candidate_posterior": selected_candidate_posterior,
            "selected_verifier_score": selected_verifier_score,
            "posterior_no_target_mass": posterior_no_target_mass,
            "abstain_probability": abstain_probability,
            "mask_mass": mask_mass,
            "mask_peak": mask_peak,
            "active_points": active_points,
            "valid_points": valid_points,
            "confidence_components": confidence_components,
            "candidate_scores": candidate_scores,
            "candidate_posterior_scores": candidate_posterior_scores,
            "verification_scores": verification_scores,
            "no_target_scores": no_target_scores,
            "selected_program_texts": candidate_program_texts,
            "output_keys": sorted(str(key) for key in outputs.keys()),
        }

    def _resolve_program(
        self,
        sample: Mapping[str, Any],
        outputs: Mapping[str, Any],
        batch_index: int,
    ) -> Tuple[ProgramLike, Dict[str, Any], str]:
        selected_program_dict = _select_value(outputs.get("selected_program_dicts"), batch_index)
        if isinstance(selected_program_dict, dict):
            program = program_from_dict(selected_program_dict)
            program_text = str(_select_value(outputs.get("selected_program_texts"), batch_index) or program.to_canonical_text())
            return program, _as_jsonable(selected_program_dict), program_text

        bundle_payload = _select_value(sample.get("program_bundle"), batch_index) if isinstance(sample, Mapping) else None
        if isinstance(bundle_payload, dict):
            try:
                bundle = bundle_from_dict(bundle_payload)
                selected_idx = int(self._scalar_output(outputs, "selected_candidate_idx", batch_index, default=0.0))
                if 0 <= selected_idx < len(bundle.candidates):
                    program = bundle.candidates[selected_idx].program
                else:
                    program = bundle.selected_program()
                program_text = program.to_canonical_text()
                return program, _as_jsonable(program.to_dict()), program_text
            except Exception:
                pass

        program_payload = _select_value(sample.get("program"), batch_index) if isinstance(sample, Mapping) else None
        if isinstance(program_payload, dict):
            program = program_from_dict(program_payload)
            return program, _as_jsonable(program.to_dict()), program.to_canonical_text()

        field_program_payload = _select_value(sample.get("field_program"), batch_index) if isinstance(sample, Mapping) else None
        if isinstance(field_program_payload, dict):
            program = program_from_dict(field_program_payload)
            return program, _as_jsonable(program.to_dict()), program.to_canonical_text()

        raise ValueError("Could not resolve selected program from sample or outputs.")

    def _sample_tensor(self, sample: Mapping[str, Any], key: str, batch_index: int) -> Optional[torch.Tensor]:
        value = sample.get(key) if isinstance(sample, Mapping) else None
        if value is None:
            return None
        if isinstance(value, (list, tuple)) and not isinstance(value, torch.Tensor):
            value = _select_value(value, batch_index)
        if isinstance(value, torch.Tensor):
            return value.detach().cpu()
        return torch.as_tensor(value)

    def _sample_mask(self, sample: Mapping[str, Any], points_xyz: Optional[torch.Tensor], batch_index: int) -> Optional[torch.Tensor]:
        value = sample.get("valid_point_mask") if isinstance(sample, Mapping) else None
        if value is None:
            if points_xyz is None:
                return None
            return torch.ones(points_xyz.shape[0], dtype=torch.bool)
        if isinstance(value, (list, tuple)) and not isinstance(value, torch.Tensor):
            value = _select_value(value, batch_index)
        if isinstance(value, torch.Tensor):
            return value.detach().cpu().bool().reshape(-1)
        return torch.as_tensor(value, dtype=torch.bool).reshape(-1)

    def _mask_to_prob(self, mask: torch.Tensor) -> torch.Tensor:
        tensor = mask.detach().cpu().float().reshape(-1)
        if tensor.numel() == 0:
            return tensor
        if tensor.min().item() < 0.0 or tensor.max().item() > 1.0:
            return torch.sigmoid(tensor)
        return tensor

    def _output_tensor(self, outputs: Mapping[str, Any], key: str, batch_index: int) -> Optional[torch.Tensor]:
        value = outputs.get(key)
        value = _select_value(value, batch_index)
        if value is None:
            return None
        if isinstance(value, torch.Tensor):
            return value.detach().cpu()
        if isinstance(value, (bool, int, float)):
            return torch.as_tensor(value)
        if isinstance(value, (list, tuple)):
            try:
                return torch.as_tensor(value)
            except Exception:
                return None
        return None

    def _scalar_output(self, outputs: Mapping[str, Any], key: str, batch_index: int, default: float = 0.0) -> float:
        value = self._output_tensor(outputs, key, batch_index)
        if value is None:
            raw = outputs.get(key)
            if isinstance(raw, str):
                return default
            return float(default)
        return _scalar(value, default=default)

    def _bool_output(self, outputs: Mapping[str, Any], key: str, batch_index: int, default: bool = False) -> bool:
        value = outputs.get(key)
        value = _select_value(value, batch_index)
        if value is None:
            return bool(default)
        if isinstance(value, torch.Tensor):
            if value.numel() == 0:
                return bool(default)
            return bool(value.detach().cpu().reshape(-1)[0].item())
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "y"}
        return bool(value)

    def _score_from_outputs(
        self,
        outputs: Mapping[str, Any],
        key: str,
        batch_index: int,
        candidate_index: int,
        default: float = 0.0,
    ) -> float:
        value = outputs.get(key)
        value = _select_value(value, batch_index)
        if value is None:
            return float(default)
        if isinstance(value, torch.Tensor):
            tensor = value.detach().cpu().reshape(-1)
            if tensor.numel() == 0:
                return float(default)
            if 0 <= candidate_index < tensor.numel():
                return float(tensor[candidate_index].item())
            return float(tensor[0].item())
        if isinstance(value, (list, tuple)):
            if not value:
                return float(default)
            if 0 <= candidate_index < len(value):
                return float(value[candidate_index])
            return float(value[0])
        try:
            return float(value)
        except Exception:
            return float(default)

    def _tensor_list(self, outputs: Mapping[str, Any], key: str, batch_index: int) -> List[float]:
        value = outputs.get(key)
        value = _select_value(value, batch_index)
        if value is None:
            return []
        if isinstance(value, torch.Tensor):
            return [float(item) for item in value.detach().cpu().reshape(-1).tolist()]
        if isinstance(value, (list, tuple)):
            return [float(item) for item in value]
        return [float(value)]

    def _value_list(self, outputs: Mapping[str, Any], key: str, batch_index: int) -> List[Any]:
        value = outputs.get(key)
        value = _select_value(value, batch_index)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _region_mean(
        self,
        outputs: Mapping[str, Any],
        selected_key: str,
        fallback_key: str,
        batch_index: int,
        region_mask: torch.Tensor,
        fallback_mask: torch.Tensor,
    ) -> float:
        value = self._output_tensor(outputs, selected_key, batch_index)
        if value is None:
            value = self._output_tensor(outputs, fallback_key, batch_index)
        if value is None:
            return 0.0
        return _mask_mean(value, region_mask, fallback_mask)

    def _evidence_summary(
        self,
        program: ProgramLike,
        candidate_regions: Sequence[CandidateRegion],
        selected_candidate_idx: int,
        selected_candidate_score: float,
        selected_candidate_posterior: float,
        selected_verifier_score: float,
        posterior_no_target_mass: float,
        abstain_probability: float,
        selected_candidate_is_no_target: bool,
        mask_mass: float,
    ) -> List[str]:
        lines = _program_summary(program)
        lines.append(
            f"selection: idx={selected_candidate_idx}, score={selected_candidate_score:.3f}, "
            f"posterior={selected_candidate_posterior:.3f}, verifier={selected_verifier_score:.3f}"
        )
        lines.append(
            f"decision: no_target={str(selected_candidate_is_no_target).lower()}, "
            f"posterior_no_target_mass={posterior_no_target_mass:.3f}, "
            f"abstain_prob={abstain_probability:.3f}, mask_mass={mask_mass:.3f}"
        )
        for region in candidate_regions[: min(len(candidate_regions), 3)]:
            lines.append(f"region {region.region_id}: {region.summary}")
        return lines

    def _batch_size(self, batch: Mapping[str, Any], outputs: Mapping[str, Any]) -> int:
        for key in ("selected_candidate_idx", "selected_program_mask", "abstain_logits"):
            value = outputs.get(key)
            if isinstance(value, torch.Tensor) and value.ndim > 0:
                return int(value.shape[0])
        for key in ("sample_id", "text", "program"):
            value = batch.get(key) if isinstance(batch, Mapping) else None
            if isinstance(value, (list, tuple)):
                return len(value)
            if isinstance(value, torch.Tensor) and value.ndim > 0:
                return int(value.shape[0])
        return 1

    def _failure_pack(
        self,
        sample: Mapping[str, Any],
        program: ProgramLike,
        selected_program_dict: Dict[str, Any],
        selected_program_text: str,
        outputs: Mapping[str, Any],
        batch_index: int,
        failure_reason: str,
    ) -> EvidencePack:
        selected_candidate_idx = int(self._scalar_output(outputs, "selected_candidate_idx", batch_index, default=0.0))
        selected_verifier_score = self._scalar_output(outputs, "selected_verifier_score", batch_index, default=0.0)
        posterior_no_target_mass = self._scalar_output(outputs, "posterior_no_target_mass", batch_index, default=0.0)
        abstain_probability = self._scalar_from_logits(outputs, "abstain_logits", batch_index, default=0.0)
        confidence_components = {
            "evidence_score": 0.0,
            "consistency_score": 0.0,
            "positive_confidence": 0.0,
            "no_target_confidence": 0.0,
            "decision_confidence": 0.0,
        }
        raw_trace = {
            "failure_reason": failure_reason,
            "output_keys": sorted(str(key) for key in outputs.keys()),
        }
        sample_id = str(_select_value(sample.get("sample_id"), batch_index) if isinstance(sample, Mapping) and "sample_id" in sample else "")
        region_id = str(_select_value(sample.get("region_id"), batch_index) if isinstance(sample, Mapping) and "region_id" in sample else "")
        area_id = str(_select_value(sample.get("area_id"), batch_index) if isinstance(sample, Mapping) and "area_id" in sample else "")
        task_type = str(_select_value(sample.get("task_type"), batch_index) if isinstance(sample, Mapping) and "task_type" in sample else "")
        text = str(_select_value(sample.get("text"), batch_index) if isinstance(sample, Mapping) and "text" in sample else "")
        return EvidencePack(
            status=failure_reason,
            target_hit=False,
            decision_kind="review" if failure_reason != "execution_failed" else "failed",
            review_required=True,
            confidence=0.0,
            confidence_components=confidence_components,
            selected_candidate_idx=selected_candidate_idx,
            selected_candidate_is_no_target=False,
            selected_candidate_score=0.0,
            selected_candidate_posterior=0.0,
            selected_verifier_score=selected_verifier_score,
            posterior_no_target_mass=posterior_no_target_mass,
            abstain_probability=abstain_probability,
            selected_mask_mass=0.0,
            selected_mask_peak=0.0,
            mask_selection_mode=str(outputs.get("mask_selection_mode", "unknown")),
            candidate_regions=[],
            evidence_summary=[f"status: {failure_reason}"],
            clause_support={},
            failure_reason=failure_reason,
            sample_id=sample_id,
            region_id=region_id,
            area_id=area_id,
            task_type=task_type,
            text=text,
            program_text=program.to_canonical_text(),
            program_schema_mode=str(program.metadata.get("program_schema_mode", "")),
            program_version=str(program.metadata.get("program_version", "")),
            program_dict=program.to_dict() if hasattr(program, "to_dict") else _as_jsonable(selected_program_dict),
            selected_program_text=selected_program_text,
            selected_program_dict=_as_jsonable(selected_program_dict),
            raw_trace=raw_trace,
        )

    def _scalar_from_logits(self, outputs: Mapping[str, Any], key: str, batch_index: int, default: float = 0.0) -> float:
        value = self._output_tensor(outputs, key, batch_index)
        if value is None:
            return float(default)
        tensor = value.detach().cpu().reshape(-1)
        if tensor.numel() == 0:
            return float(default)
        return float(torch.sigmoid(tensor[0]).item())


def compile_evidence(
    sample: Mapping[str, Any],
    outputs: Mapping[str, Any],
    config: Optional[EvidenceCompilerConfig] = None,
    batch_index: int = 0,
) -> EvidencePack:
    return EvidenceCompiler(config=config).compile(sample=sample, outputs=outputs, batch_index=batch_index)
