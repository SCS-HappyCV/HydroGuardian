from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import torch
import torch.nn as nn

from .schema import (
    ATTRIBUTE_ALIASES,
    RELATION_ALIASES,
    DEFAULT_EVIDENCE,
    OperatorizedSpatialProgram,
    ProgramBundle,
    ProgramLike,
    ProgramStep,
    RelationClause,
)

MASK_EPS = 1e-4


def _masked_channel_norm(values: torch.Tensor, valid_mask: torch.Tensor) -> torch.Tensor:
    outputs = torch.zeros_like(values)
    for batch_idx in range(values.shape[0]):
        mask = valid_mask[batch_idx]
        if not mask.any():
            continue
        current = values[batch_idx][mask]
        mean = current.mean(dim=0, keepdim=True)
        std = current.std(dim=0, keepdim=True).clamp_min(1e-6)
        outputs[batch_idx][mask] = (current - mean) / std
    return outputs


def _prob_to_logit(values: torch.Tensor, eps: float = MASK_EPS) -> torch.Tensor:
    clipped = values.clamp(eps, 1.0 - eps)
    return torch.log(clipped) - torch.log1p(-clipped)


def _neutral_mask(valid_mask: torch.Tensor) -> torch.Tensor:
    return valid_mask.float()


def _soft_and_masks(masks: Sequence[torch.Tensor], valid_mask: torch.Tensor, eps: float = MASK_EPS) -> torch.Tensor:
    output = _neutral_mask(valid_mask)
    for mask in masks:
        output = output * mask.clamp(eps, 1.0)
    return output * valid_mask.float()


def _soft_or_masks(masks: Sequence[torch.Tensor], valid_mask: torch.Tensor) -> torch.Tensor:
    if not masks:
        return _neutral_mask(valid_mask)
    inverse = _neutral_mask(valid_mask)
    for mask in masks:
        inverse = inverse * (1.0 - mask.clamp(0.0, 1.0))
    return (1.0 - inverse).clamp(0.0, 1.0) * valid_mask.float()


def _weighted_pool(values: torch.Tensor, weights: torch.Tensor, valid_mask: torch.Tensor) -> torch.Tensor:
    weights = weights.clamp_min(0.0) * valid_mask.float()
    denom = weights.sum().clamp_min(1e-6)
    if float(weights.sum().item()) <= 1e-6:
        if valid_mask.any():
            return values[valid_mask].mean(dim=0)
        return values.new_zeros(values.shape[-1])
    normalized = weights / denom
    return (values * normalized.unsqueeze(-1)).sum(dim=0)


def _masked_mean(values: torch.Tensor, valid_mask: torch.Tensor) -> torch.Tensor:
    if valid_mask.any():
        return values[valid_mask].mean(dim=0)
    return values.new_zeros(values.shape[-1])


class ClassMaskExecutor(nn.Module):
    @staticmethod
    def _label_mask(class_probs: torch.Tensor, label_ids: List[int], reduction: str = "mean") -> torch.Tensor:
        if not label_ids:
            return class_probs.new_zeros(class_probs.shape[0])
        valid_ids = [label_id for label_id in label_ids if 0 <= label_id < class_probs.shape[-1]]
        if not valid_ids:
            return class_probs.new_zeros(class_probs.shape[0])
        selected = class_probs[:, valid_ids]
        if reduction == "max":
            return selected.max(dim=-1).values
        return selected.mean(dim=-1)

    def execute_label_mask(
        self,
        class_probs_i: torch.Tensor,
        label_ids: List[int],
        valid_mask_i: torch.Tensor,
        reduction: str = "mean",
    ) -> torch.Tensor:
        return self._label_mask(class_probs_i, label_ids, reduction=reduction) * valid_mask_i.float()

    def forward(
        self,
        class_probs: torch.Tensor,
        programs: Sequence[ProgramLike],
        valid_point_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        masks = []
        active = []
        for batch_idx, program in enumerate(programs):
            mask = self.execute_label_mask(
                class_probs[batch_idx],
                list(program.target_label_ids),
                valid_point_mask[batch_idx],
                reduction="mean",
            )
            masks.append(mask)
            active.append(bool(program.target_label_ids))
        class_mask = torch.stack(masks, dim=0)
        return {
            "class_mask": class_mask,
            "class_mask_logits": _prob_to_logit(class_mask),
            "class_active_mask": torch.tensor(active, dtype=torch.bool, device=valid_point_mask.device),
        }


class ProgramStepEncoder(nn.Module):
    def __init__(self, hidden_dim: int, num_classes: int) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.op_to_idx = {
            "select": 0,
            "filter": 1,
            "relate": 2,
            "exclude": 3,
            "compose": 4,
        }
        self.op_embed = nn.Embedding(len(self.op_to_idx) + 1, hidden_dim)
        self.label_embed = nn.Embedding(num_classes + 1, hidden_dim)
        self.attr_vocab = sorted(set(ATTRIBUTE_ALIASES.values()))
        self.attr_to_idx = {name: idx for idx, name in enumerate(self.attr_vocab)}
        self.attr_embed = nn.Embedding(len(self.attr_vocab) + 1, hidden_dim)
        self.rel_vocab = sorted(set(RELATION_ALIASES.values()))
        self.rel_to_idx = {name: idx for idx, name in enumerate(self.rel_vocab)}
        self.rel_embed = nn.Embedding(len(self.rel_vocab) + 1, hidden_dim)
        self.param_proj = nn.Sequential(
            nn.Linear(2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.fuse = nn.Sequential(
            nn.LayerNorm(hidden_dim * 6),
            nn.Linear(hidden_dim * 6, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def _embed_label_ids(self, label_ids: List[int], device: torch.device) -> torch.Tensor:
        if not label_ids:
            index = torch.tensor([self.label_embed.num_embeddings - 1], device=device, dtype=torch.long)
            return self.label_embed(index)[0]
        indices = torch.tensor(label_ids, device=device, dtype=torch.long).clamp(0, self.label_embed.num_embeddings - 2)
        return self.label_embed(indices).mean(dim=0)

    def _embed_attribute(self, attribute: str | None, device: torch.device) -> torch.Tensor:
        if attribute is None:
            index = self.attr_embed.num_embeddings - 1
        else:
            index = self.attr_to_idx.get(attribute, self.attr_embed.num_embeddings - 1)
        return self.attr_embed.weight[index].to(device)

    def _embed_relation(self, relation: str | None, device: torch.device) -> torch.Tensor:
        if relation is None:
            index = self.rel_embed.num_embeddings - 1
        else:
            index = self.rel_to_idx.get(relation, self.rel_embed.num_embeddings - 1)
        return self.rel_embed.weight[index].to(device)

    def encode_step(self, step: ProgramStep, device: torch.device) -> torch.Tensor:
        op_idx = self.op_to_idx.get(step.op, len(self.op_to_idx))
        op_token = self.op_embed.weight[op_idx].to(device)
        label_token = self._embed_label_ids(list(step.label_ids), device)
        reference_token = self._embed_label_ids(list(step.reference_label_ids), device)
        attr_token = self._embed_attribute(step.attribute, device)
        rel_token = self._embed_relation(step.relation, device)
        param_tensor = torch.tensor(
            [
                float(step.distance_m if step.distance_m is not None else 0.0),
                float(step.margin_m if step.margin_m is not None else 0.0),
            ],
            device=device,
            dtype=op_token.dtype,
        )
        param_token = self.param_proj(param_tensor.unsqueeze(0)).squeeze(0)
        return self.fuse(torch.cat([op_token, label_token, reference_token, attr_token, rel_token, param_token], dim=0))


class EvidenceExtractor(nn.Module):
    def __init__(self, hidden_dim: int, geometry_feature_dim: int) -> None:
        super().__init__()
        self.xyz_proj = nn.Sequential(
            nn.LayerNorm(4),
            nn.Linear(4, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.geometry_proj = nn.Sequential(
            nn.LayerNorm(geometry_feature_dim),
            nn.Linear(geometry_feature_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.evidence_fuse = nn.Sequential(
            nn.LayerNorm(hidden_dim * 4),
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def forward(
        self,
        point_tokens: torch.Tensor,
        geometry_tokens: torch.Tensor,
        ortho_point_tokens: torch.Tensor,
        points_xyz: torch.Tensor,
        geometry_features: torch.Tensor,
        valid_point_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        centered_xyz = points_xyz.clone()
        radial = torch.zeros_like(points_xyz[..., :1])
        for batch_idx in range(points_xyz.shape[0]):
            mask = valid_point_mask[batch_idx]
            if not mask.any():
                continue
            center = points_xyz[batch_idx][mask].mean(dim=0, keepdim=True)
            centered_xyz[batch_idx][mask] = points_xyz[batch_idx][mask] - center
            radial[batch_idx][mask] = torch.norm(centered_xyz[batch_idx][mask, :2], dim=-1, keepdim=True)
        xyz_features = torch.cat([centered_xyz, radial], dim=-1)
        xyz_tokens = self.xyz_proj(xyz_features)
        geometry_context_tokens = self.geometry_proj(geometry_features)
        fused = self.evidence_fuse(torch.cat([point_tokens, geometry_tokens, ortho_point_tokens, xyz_tokens], dim=-1))
        evidence_tokens = (point_tokens + 0.5 * geometry_context_tokens + fused) * valid_point_mask.unsqueeze(-1).float()
        return {
            "evidence_tokens": evidence_tokens,
            "geometry_context_tokens": geometry_context_tokens * valid_point_mask.unsqueeze(-1).float(),
            "ortho_evidence_tokens": ortho_point_tokens * valid_point_mask.unsqueeze(-1).float(),
            "xyz_features": xyz_features * valid_point_mask.unsqueeze(-1).float(),
        }


class ReferenceResolver(nn.Module):
    def __init__(self, hidden_dim: int, num_classes: int, class_executor: ClassMaskExecutor) -> None:
        super().__init__()
        self.class_executor = class_executor
        self.label_embed = nn.Embedding(num_classes + 1, hidden_dim)
        self.ref_gate = nn.Sequential(
            nn.LayerNorm(hidden_dim * 2 + 1),
            nn.Linear(hidden_dim * 2 + 1, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )

    def _label_token(self, label_ids: List[int], device: torch.device) -> torch.Tensor:
        if not label_ids:
            index = torch.tensor([self.label_embed.num_embeddings - 1], device=device, dtype=torch.long)
            return self.label_embed(index)[0]
        indices = torch.tensor(label_ids, device=device, dtype=torch.long).clamp(0, self.label_embed.num_embeddings - 2)
        return self.label_embed(indices).mean(dim=0)

    def forward(
        self,
        evidence_tokens_i: torch.Tensor,
        class_probs_i: torch.Tensor,
        label_ids: List[int],
        valid_mask_i: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        base_reference_mask = self.class_executor.execute_label_mask(
            class_probs_i,
            label_ids,
            valid_mask_i,
            reduction="mean",
        )
        label_token = self._label_token(label_ids, evidence_tokens_i.device)
        label_expand = label_token.unsqueeze(0).expand(evidence_tokens_i.shape[0], -1)
        global_context = _masked_mean(evidence_tokens_i, valid_mask_i).unsqueeze(0).expand(evidence_tokens_i.shape[0], -1)
        gate_logits = self.ref_gate(
            torch.cat([evidence_tokens_i, label_expand + global_context, base_reference_mask.unsqueeze(-1)], dim=-1)
        ).squeeze(-1)
        gate = torch.sigmoid(gate_logits) * valid_mask_i.float()
        reference_mask = (base_reference_mask * gate).clamp(0.0, 1.0) * valid_mask_i.float()
        reference_token = _weighted_pool(evidence_tokens_i, reference_mask, valid_mask_i)
        return {
            "reference_mask": reference_mask,
            "reference_token": reference_token,
            "reference_gate": gate,
        }


class GroundedAttributeOperator(nn.Module):
    def __init__(self, hidden_dim: int, geometry_feature_dim: int) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.geometry_feature_dim = int(geometry_feature_dim)
        self.attr_query_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim * 2),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.attr_mask_head = nn.Sequential(
            nn.LayerNorm(hidden_dim * 4 + 3),
            nn.Linear(hidden_dim * 4 + 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )

    def _heuristic_prior(self, attr_name: str, geometry_features_i: torch.Tensor) -> torch.Tensor:
        z_norm = geometry_features_i[..., 0]
        slope = geometry_features_i[..., 1]
        roughness = geometry_features_i[..., 2]
        density = geometry_features_i[..., 3]

        if attr_name == "low_elevation":
            return torch.sigmoid(-2.0 * z_norm)
        if attr_name == "high_elevation":
            return torch.sigmoid(2.0 * z_norm)
        if attr_name == "flat":
            return torch.sigmoid(-2.5 * slope)
        if attr_name == "steep":
            return torch.sigmoid(2.5 * slope)
        if attr_name == "thin":
            return torch.sigmoid(roughness - density)
        if attr_name == "linear":
            return torch.sigmoid(0.5 * roughness - 0.5 * density)
        if attr_name == "water_related":
            return torch.sigmoid(-z_norm + 0.5 * roughness)
        if attr_name == "vegetated":
            return torch.sigmoid(-roughness + 0.25 * density)
        if attr_name == "bare_ground":
            return torch.sigmoid(roughness - 0.25 * density)
        if attr_name == "built":
            return torch.sigmoid(roughness + 0.5 * density)
        return geometry_features_i.new_full(geometry_features_i.shape[:1], 0.5)

    def execute(
        self,
        evidence_tokens_i: torch.Tensor,
        geometry_tokens_i: torch.Tensor,
        ortho_tokens_i: torch.Tensor,
        geometry_features_i: torch.Tensor,
        input_mask_i: torch.Tensor,
        step_token: torch.Tensor,
        attr_name: str,
        valid_mask_i: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        current_summary = _weighted_pool(evidence_tokens_i, input_mask_i, valid_mask_i)
        attr_query = self.attr_query_proj(torch.cat([step_token, current_summary], dim=0))
        query_expand = attr_query.unsqueeze(0).expand(evidence_tokens_i.shape[0], -1)
        evidence_alignment = torch.sigmoid(
            (evidence_tokens_i * query_expand).sum(dim=-1) / math.sqrt(float(self.hidden_dim))
        ) * valid_mask_i.float()
        heuristic_prior = self._heuristic_prior(attr_name, geometry_features_i).clamp(0.05, 0.95) * valid_mask_i.float()
        features = torch.cat(
            [
                evidence_tokens_i,
                geometry_tokens_i,
                ortho_tokens_i,
                query_expand,
                input_mask_i.unsqueeze(-1),
                evidence_alignment.unsqueeze(-1),
                heuristic_prior.unsqueeze(-1),
            ],
            dim=-1,
        )
        learned_logits = self.attr_mask_head(features).squeeze(-1)
        mask = torch.sigmoid(
            learned_logits
            + 0.35 * _prob_to_logit(evidence_alignment.clamp(0.05, 0.95))
            + 0.35 * _prob_to_logit(heuristic_prior.clamp(0.05, 0.95))
        ) * valid_mask_i.float()
        return {
            "mask": mask,
            "evidence_map": evidence_alignment,
        }


class GroundedRelationOperator(nn.Module):
    def __init__(
        self,
        hidden_dim: int,
        geometry_feature_dim: int,
        num_classes: int,
        class_executor: ClassMaskExecutor,
        point_chunk_size: int = 2048,
        max_reference_points: int = 256,
    ) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.geometry_feature_dim = int(geometry_feature_dim)
        self.point_chunk_size = int(point_chunk_size)
        self.max_reference_points = int(max_reference_points)
        self.reference_resolver = ReferenceResolver(hidden_dim=hidden_dim, num_classes=num_classes, class_executor=class_executor)
        self.rel_query_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim * 3),
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.rel_mask_head = nn.Sequential(
            nn.LayerNorm(hidden_dim * 4 + 8),
            nn.Linear(hidden_dim * 4 + 8, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )

    def _distance_mask(
        self,
        points_xyz: torch.Tensor,
        reference_xy: torch.Tensor,
        threshold: float,
        valid_mask: torch.Tensor,
        alpha_scale: float,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        mask = points_xyz.new_zeros(points_xyz.shape[0])
        min_distance = points_xyz.new_full((points_xyz.shape[0],), float(threshold) * 4.0)
        if reference_xy.numel() == 0:
            return mask, min_distance
        valid_indices = torch.nonzero(valid_mask, as_tuple=False).flatten()
        if valid_indices.numel() == 0:
            return mask, min_distance
        valid_xy = points_xyz[valid_indices, :2]
        outputs = []
        distance_outputs = []
        alpha = max(float(threshold) * alpha_scale, 0.25)
        chunk_size = max(self.point_chunk_size, 1)
        for start in range(0, valid_xy.shape[0], chunk_size):
            query = valid_xy[start : start + chunk_size]
            dist = torch.cdist(query, reference_xy)
            min_dist = dist.min(dim=1).values
            distance_outputs.append(min_dist)
            outputs.append(torch.sigmoid((float(threshold) - min_dist) / alpha))
        mask[valid_indices] = torch.cat(outputs, dim=0)
        min_distance[valid_indices] = torch.cat(distance_outputs, dim=0)
        return mask, min_distance

    def _vertical_features(
        self,
        points_xyz: torch.Tensor,
        reference_weights: torch.Tensor,
        valid_mask: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        z_delta = points_xyz.new_zeros(points_xyz.shape[0])
        score = points_xyz.new_zeros(points_xyz.shape[0])
        valid_weights = reference_weights[valid_mask]
        if valid_weights.numel() == 0 or valid_weights.max() <= 0:
            return z_delta, score
        reference_z = (points_xyz[valid_mask, 2] * valid_weights).sum() / valid_weights.sum().clamp_min(1e-6)
        z_delta = points_xyz[:, 2] - reference_z
        score = torch.sigmoid(z_delta / 0.3)
        score[~valid_mask] = 0.0
        return z_delta, score

    def _along_mask(
        self,
        points_xyz: torch.Tensor,
        reference_xy: torch.Tensor,
        threshold: float,
        valid_mask: torch.Tensor,
    ) -> torch.Tensor:
        mask = points_xyz.new_zeros(points_xyz.shape[0])
        if reference_xy.shape[0] < 2:
            return mask
        ref_center = reference_xy.mean(dim=0, keepdim=True)
        centered = reference_xy - ref_center
        cov = centered.t().mm(centered) / max(reference_xy.shape[0], 1)
        eigvals, eigvecs = torch.linalg.eigh(cov)
        direction = eigvecs[:, int(torch.argmax(eigvals).item())]
        direction = direction / direction.norm().clamp_min(1e-6)
        normal = torch.stack([-direction[1], direction[0]], dim=0)
        valid_indices = torch.nonzero(valid_mask, as_tuple=False).flatten()
        if valid_indices.numel() == 0:
            return mask
        query_xy = points_xyz[valid_indices, :2]
        offset = query_xy - ref_center
        perpendicular_distance = torch.abs(offset.matmul(normal))
        alpha = max(float(threshold) * 0.35, 0.25)
        band_mask = torch.sigmoid((float(threshold) - perpendicular_distance) / alpha)
        mask[valid_indices] = band_mask
        return mask

    def _spatial_fields(
        self,
        points_xyz_i: torch.Tensor,
        reference_mask: torch.Tensor,
        relation: RelationClause,
        valid_mask_i: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        topk = min(self.max_reference_points, int(valid_mask_i.sum().item()))
        if topk <= 0:
            zeros = points_xyz_i.new_zeros(points_xyz_i.shape[0])
            return torch.stack([zeros, zeros, zeros, zeros, zeros], dim=-1), zeros
        top_values, top_indices = torch.topk(reference_mask, k=topk)
        top_indices = top_indices[top_values > 0]
        if top_indices.numel() == 0:
            zeros = points_xyz_i.new_zeros(points_xyz_i.shape[0])
            return torch.stack([zeros, zeros, zeros, zeros, zeros], dim=-1), zeros

        threshold = relation.distance_m if relation.distance_m is not None else 3.0
        near_mask, min_distance = self._distance_mask(
            points_xyz_i,
            points_xyz_i[top_indices, :2],
            threshold=threshold,
            valid_mask=valid_mask_i,
            alpha_scale=0.35,
        )
        along_mask = self._along_mask(
            points_xyz_i,
            points_xyz_i[top_indices, :2],
            threshold=max(float(threshold), 1.0),
            valid_mask=valid_mask_i,
        )
        z_delta, vertical_score = self._vertical_features(
            points_xyz_i,
            reference_mask,
            valid_mask_i,
        )
        above_mask = torch.sigmoid((z_delta - float(relation.margin_m if relation.margin_m is not None else 0.2)) / 0.3)
        below_mask = torch.sigmoid((-z_delta - float(relation.margin_m if relation.margin_m is not None else 0.2)) / 0.3)
        above_mask = above_mask * valid_mask_i.float()
        below_mask = below_mask * valid_mask_i.float()

        if relation.type in {"near", "adjacent"}:
            heuristic_mask = near_mask
        elif relation.type == "along":
            heuristic_mask = (0.6 * near_mask + 0.4 * along_mask).clamp(0.0, 1.0)
        elif relation.type == "above":
            heuristic_mask = above_mask
        else:
            heuristic_mask = below_mask

        distance_score = torch.exp(-min_distance / max(float(threshold), 1e-3)) * valid_mask_i.float()
        fields = torch.stack(
            [
                near_mask,
                along_mask,
                above_mask,
                below_mask,
                distance_score,
            ],
            dim=-1,
        )
        return fields, heuristic_mask

    def execute(
        self,
        evidence_tokens_i: torch.Tensor,
        geometry_tokens_i: torch.Tensor,
        ortho_tokens_i: torch.Tensor,
        class_probs_i: torch.Tensor,
        points_xyz_i: torch.Tensor,
        input_mask_i: torch.Tensor,
        step_token: torch.Tensor,
        relation: RelationClause,
        valid_mask_i: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        reference_outputs = self.reference_resolver(
            evidence_tokens_i=evidence_tokens_i,
            class_probs_i=class_probs_i,
            label_ids=list(relation.reference_label_ids),
            valid_mask_i=valid_mask_i,
        )
        current_summary = _weighted_pool(evidence_tokens_i, input_mask_i, valid_mask_i)
        rel_query = self.rel_query_proj(torch.cat([step_token, current_summary, reference_outputs["reference_token"]], dim=0))
        query_expand = rel_query.unsqueeze(0).expand(evidence_tokens_i.shape[0], -1)
        relation_alignment = torch.sigmoid(
            (evidence_tokens_i * query_expand).sum(dim=-1) / math.sqrt(float(self.hidden_dim))
        ) * valid_mask_i.float()
        spatial_fields, heuristic_mask = self._spatial_fields(
            points_xyz_i=points_xyz_i,
            reference_mask=reference_outputs["reference_mask"],
            relation=relation,
            valid_mask_i=valid_mask_i,
        )
        features = torch.cat(
            [
                evidence_tokens_i,
                geometry_tokens_i,
                ortho_tokens_i,
                query_expand,
                spatial_fields,
                input_mask_i.unsqueeze(-1),
                reference_outputs["reference_mask"].unsqueeze(-1),
                relation_alignment.unsqueeze(-1),
            ],
            dim=-1,
        )
        learned_logits = self.rel_mask_head(features).squeeze(-1)
        mask = torch.sigmoid(
            learned_logits
            + 0.45 * _prob_to_logit(heuristic_mask.clamp(0.05, 0.95))
            + 0.30 * _prob_to_logit(relation_alignment.clamp(0.05, 0.95))
        ) * valid_mask_i.float()
        return {
            "mask": mask,
            "reference_mask": reference_outputs["reference_mask"],
            "evidence_map": relation_alignment,
        }


class NegativeMaskExecutor(nn.Module):
    def __init__(self, class_executor: ClassMaskExecutor) -> None:
        super().__init__()
        self.class_executor = class_executor

    def execute_negative_mask(
        self,
        class_probs_i: torch.Tensor,
        negative_label_ids: List[int],
        valid_mask_i: torch.Tensor,
    ) -> torch.Tensor:
        if not negative_label_ids:
            return class_probs_i.new_zeros(class_probs_i.shape[0]) * valid_mask_i.float()
        return self.class_executor.execute_label_mask(
            class_probs_i,
            negative_label_ids,
            valid_mask_i,
            reduction="max",
        )

    def forward(
        self,
        class_probs: torch.Tensor,
        programs: Sequence[ProgramLike],
        valid_point_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        negative_masks = []
        keep_masks = []
        active = []
        for batch_idx, program in enumerate(programs):
            negative_mask = self.execute_negative_mask(
                class_probs[batch_idx],
                list(program.negative_label_ids),
                valid_point_mask[batch_idx],
            )
            if program.negative_label_ids:
                keep_mask = (1.0 - negative_mask).clamp(0.0, 1.0) * valid_point_mask[batch_idx].float()
                active.append(True)
            else:
                keep_mask = _neutral_mask(valid_point_mask[batch_idx])
                active.append(False)
            negative_masks.append(negative_mask)
            keep_masks.append(keep_mask)

        negative_mask = torch.stack(negative_masks, dim=0)
        keep_mask = torch.stack(keep_masks, dim=0)
        return {
            "negative_mask": negative_mask,
            "negative_mask_logits": _prob_to_logit(negative_mask),
            "keep_mask": keep_mask,
            "keep_mask_logits": _prob_to_logit(keep_mask),
            "negative_active_mask": torch.tensor(active, dtype=torch.bool, device=valid_point_mask.device),
        }


class MaskComposer(nn.Module):
    def __init__(self, eps: float = MASK_EPS) -> None:
        super().__init__()
        self.eps = float(eps)

    def forward(
        self,
        class_mask: torch.Tensor,
        attribute_mask: torch.Tensor,
        relation_mask: torch.Tensor,
        keep_mask: torch.Tensor,
        valid_point_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        final_program_mask = class_mask.clamp(self.eps, 1.0 - self.eps)
        final_program_mask = final_program_mask * attribute_mask.clamp(self.eps, 1.0)
        final_program_mask = final_program_mask * relation_mask.clamp(self.eps, 1.0)
        final_program_mask = final_program_mask * keep_mask.clamp(self.eps, 1.0)
        final_program_mask = final_program_mask * valid_point_mask.float()
        program_mask_logits = _prob_to_logit(final_program_mask) * valid_point_mask.float()
        return {
            "final_program_mask": final_program_mask,
            "program_mask_logits": program_mask_logits,
        }


class LatentCandidateSelector(nn.Module):
    def __init__(self, hidden_dim: int, stats_dim: int = 8) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.stats_dim = int(stats_dim)
        self.stats_proj = nn.Sequential(
            nn.LayerNorm(self.stats_dim),
            nn.Linear(self.stats_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_dim * 4),
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(
        self,
        query_hidden: torch.Tensor,
        scene_summary: torch.Tensor,
        program_token: torch.Tensor,
        stats: torch.Tensor,
    ) -> torch.Tensor:
        stats_token = self.stats_proj(stats.unsqueeze(0)).squeeze(0)
        features = torch.cat([query_hidden, scene_summary, program_token, stats_token], dim=0)
        return self.head(features).squeeze(-1)


class ProgramExecutor(nn.Module):
    def __init__(self, hidden_dim: int, geometry_feature_dim: int, num_classes: int, point_chunk_size: int = 2048) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.geometry_feature_dim = int(geometry_feature_dim)
        self.num_classes = int(num_classes)
        self.step_encoder = ProgramStepEncoder(hidden_dim=hidden_dim, num_classes=num_classes)
        self.class_executor = ClassMaskExecutor()
        self.evidence_extractor = EvidenceExtractor(hidden_dim=hidden_dim, geometry_feature_dim=geometry_feature_dim)
        self.attribute_operator = GroundedAttributeOperator(hidden_dim=hidden_dim, geometry_feature_dim=geometry_feature_dim)
        self.relation_operator = GroundedRelationOperator(
            hidden_dim=hidden_dim,
            geometry_feature_dim=geometry_feature_dim,
            num_classes=num_classes,
            class_executor=self.class_executor,
            point_chunk_size=point_chunk_size,
        )
        self.negative_executor = NegativeMaskExecutor(class_executor=self.class_executor)
        self.mask_composer = MaskComposer()
        self.verifier = CandidateVerifier()
        self.latent_selector = LatentCandidateSelector(hidden_dim=hidden_dim)

    def _attribute_step(self, attr_name: str) -> ProgramStep:
        return ProgramStep(id=f"attr_{attr_name}", op="filter", attribute=attr_name, evidence=list(DEFAULT_EVIDENCE.get(attr_name, [])))

    def _relation_step(self, relation: RelationClause) -> ProgramStep:
        return ProgramStep(
            id=f"rel_{relation.type}_{relation.reference}",
            op="relate",
            relation=relation.type,
            reference_label=relation.reference,
            reference_label_ids=list(relation.reference_label_ids),
            distance_m=relation.distance_m,
            margin_m=relation.margin_m,
            evidence=list(relation.evidence),
        )

    def _exclude_step(self, label_name: str, label_ids: List[int]) -> ProgramStep:
        return ProgramStep(
            id=f"neg_{label_name or 'unknown'}",
            op="exclude",
            label=label_name or None,
            label_ids=list(label_ids),
            evidence=["class_logits"],
        )

    def _program_steps_for_selector(self, program: ProgramLike) -> List[ProgramStep]:
        if isinstance(program, OperatorizedSpatialProgram) and program.steps:
            return [ProgramStep.from_dict(step.to_dict()) for step in program.steps]
        steps: List[ProgramStep] = []
        if getattr(program, "target_label_ids", None):
            steps.append(
                ProgramStep(
                    id=f"sel_{getattr(program, 'target', 'others')}",
                    op="select",
                    label=getattr(program, "target", None),
                    label_ids=list(program.target_label_ids),
                )
            )
        for attr_name in getattr(program, "attributes", []):
            steps.append(self._attribute_step(attr_name))
        for relation in getattr(program, "relations", []):
            steps.append(self._relation_step(relation))
        negative_names = list(getattr(program, "negatives", []))
        negative_ids = list(getattr(program, "negative_label_ids", []))
        for index, label_id in enumerate(negative_ids):
            label_name = negative_names[index] if index < len(negative_names) else ""
            steps.append(self._exclude_step(label_name=label_name, label_ids=[label_id]))
        return steps

    def _program_token(self, program: ProgramLike, device: torch.device) -> torch.Tensor:
        steps = self._program_steps_for_selector(program)
        if not steps:
            return torch.zeros(
                self.hidden_dim,
                device=device,
                dtype=self.step_encoder.op_embed.weight.dtype,
            )
        encoded = [self.step_encoder.encode_step(step, device=device) for step in steps]
        return torch.stack(encoded, dim=0).mean(dim=0)

    def _program_complexity(self, program: ProgramLike) -> float:
        steps = self._program_steps_for_selector(program)
        return min(float(len(steps)) / 8.0, 1.0)

    def _candidate_selector_stats(
        self,
        outputs: Dict[str, torch.Tensor],
        verify: Dict[str, torch.Tensor],
        valid_point_mask: torch.Tensor,
        proposal_score: float,
        program: ProgramLike,
        is_no_target_candidate: bool,
    ) -> torch.Tensor:
        valid = valid_point_mask.float()
        denom = valid.sum().clamp_min(1.0)
        mask_mass = float((outputs["final_program_mask"] * valid).sum().item() / denom.item())
        return outputs["final_program_mask"].new_tensor(
            [
                mask_mass,
                float(verify["validity_score"].item()),
                float(verify["evidence_score"].item()),
                float(verify["no_target_score"].item()),
                float(verify["verifier_score"].item()),
                float(proposal_score),
                self._program_complexity(program),
                1.0 if is_no_target_candidate else 0.0,
            ]
        )

    def _execute_field_program(
        self,
        program: ProgramLike,
        evidence_tokens_i: torch.Tensor,
        geometry_tokens_i: torch.Tensor,
        ortho_tokens_i: torch.Tensor,
        geometry_features_i: torch.Tensor,
        class_probs_i: torch.Tensor,
        points_xyz_i: torch.Tensor,
        valid_mask_i: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        neutral_mask = _neutral_mask(valid_mask_i)
        class_mask = self.class_executor.execute_label_mask(
            class_probs_i,
            list(program.target_label_ids),
            valid_mask_i,
            reduction="mean",
        )
        attribute_masks: List[torch.Tensor] = []
        attribute_evidence_maps: List[torch.Tensor] = []
        for attr_name in program.attributes:
            step_token = self.step_encoder.encode_step(self._attribute_step(attr_name), device=evidence_tokens_i.device)
            outputs = self.attribute_operator.execute(
                evidence_tokens_i=evidence_tokens_i,
                geometry_tokens_i=geometry_tokens_i,
                ortho_tokens_i=ortho_tokens_i,
                geometry_features_i=geometry_features_i,
                input_mask_i=neutral_mask,
                step_token=step_token,
                attr_name=attr_name,
                valid_mask_i=valid_mask_i,
            )
            attribute_masks.append(outputs["mask"])
            attribute_evidence_maps.append(outputs["evidence_map"])

        relation_masks: List[torch.Tensor] = []
        relation_reference_masks: List[torch.Tensor] = []
        relation_evidence_maps: List[torch.Tensor] = []
        for relation in program.relations:
            step_token = self.step_encoder.encode_step(self._relation_step(relation), device=evidence_tokens_i.device)
            outputs = self.relation_operator.execute(
                evidence_tokens_i=evidence_tokens_i,
                geometry_tokens_i=geometry_tokens_i,
                ortho_tokens_i=ortho_tokens_i,
                class_probs_i=class_probs_i,
                points_xyz_i=points_xyz_i,
                input_mask_i=neutral_mask,
                step_token=step_token,
                relation=relation,
                valid_mask_i=valid_mask_i,
            )
            relation_masks.append(outputs["mask"])
            relation_reference_masks.append(outputs["reference_mask"])
            relation_evidence_maps.append(outputs["evidence_map"])

        negative_mask = self.negative_executor.execute_negative_mask(
            class_probs_i,
            list(program.negative_label_ids),
            valid_mask_i,
        )
        keep_mask = (
            (1.0 - negative_mask).clamp(0.0, 1.0) * valid_mask_i.float()
            if program.negative_label_ids
            else neutral_mask
        )
        attribute_mask = _soft_and_masks(attribute_masks, valid_mask_i) if attribute_masks else neutral_mask
        relation_mask = _soft_and_masks(relation_masks, valid_mask_i) if relation_masks else neutral_mask
        final_program_mask = (
            class_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)
            * attribute_mask.clamp(MASK_EPS, 1.0)
            * relation_mask.clamp(MASK_EPS, 1.0)
            * keep_mask.clamp(MASK_EPS, 1.0)
        ) * valid_mask_i.float()
        reference_mask = (
            torch.stack(relation_reference_masks, dim=0).max(dim=0).values if relation_reference_masks else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        attribute_evidence_map = (
            torch.stack(attribute_evidence_maps, dim=0).mean(dim=0) if attribute_evidence_maps else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        relation_evidence_map = (
            torch.stack(relation_evidence_maps, dim=0).mean(dim=0) if relation_evidence_maps else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        return {
            "class_mask": class_mask,
            "attribute_mask": attribute_mask,
            "relation_mask": relation_mask,
            "negative_mask": negative_mask,
            "keep_mask": keep_mask,
            "final_program_mask": final_program_mask,
            "reference_mask": reference_mask,
            "attribute_evidence_map": attribute_evidence_map,
            "relation_evidence_map": relation_evidence_map,
        }

    def _execute_operator_program(
        self,
        program: OperatorizedSpatialProgram,
        evidence_tokens_i: torch.Tensor,
        geometry_tokens_i: torch.Tensor,
        ortho_tokens_i: torch.Tensor,
        geometry_features_i: torch.Tensor,
        class_probs_i: torch.Tensor,
        points_xyz_i: torch.Tensor,
        valid_mask_i: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        step_masks: Dict[str, torch.Tensor] = {}
        step_attr_evidence_maps: List[torch.Tensor] = []
        step_relation_evidence_maps: List[torch.Tensor] = []
        step_reference_masks: List[torch.Tensor] = []
        class_masks: List[torch.Tensor] = []
        attribute_masks: List[torch.Tensor] = []
        relation_masks: List[torch.Tensor] = []
        negative_masks: List[torch.Tensor] = []

        for step in program.steps:
            step_token = self.step_encoder.encode_step(step, device=evidence_tokens_i.device)
            current_mask = _neutral_mask(valid_mask_i)
            if step.op == "select":
                label_ids = list(step.label_ids) if step.label_ids else list(program.target_label_ids)
                current_mask = self.class_executor.execute_label_mask(
                    class_probs_i,
                    label_ids,
                    valid_mask_i,
                    reduction="mean",
                )
                class_masks.append(current_mask)
            elif step.op == "filter":
                input_mask = step_masks.get(step.input or "", _neutral_mask(valid_mask_i))
                outputs = self.attribute_operator.execute(
                    evidence_tokens_i=evidence_tokens_i,
                    geometry_tokens_i=geometry_tokens_i,
                    ortho_tokens_i=ortho_tokens_i,
                    geometry_features_i=geometry_features_i,
                    input_mask_i=input_mask,
                    step_token=step_token,
                    attr_name=step.attribute or "",
                    valid_mask_i=valid_mask_i,
                )
                base_mask = outputs["mask"]
                step_attr_evidence_maps.append(outputs["evidence_map"])
                attribute_masks.append(base_mask)
                current_mask = (input_mask * base_mask).clamp(0.0, 1.0) * valid_mask_i.float()
            elif step.op == "relate":
                input_mask = step_masks.get(step.input or "", _neutral_mask(valid_mask_i))
                relation = RelationClause(
                    type=step.relation or "near",
                    reference=step.reference_label or "",
                    reference_label_ids=list(step.reference_label_ids),
                    distance_m=step.distance_m,
                    margin_m=step.margin_m,
                    evidence=list(step.evidence),
                )
                outputs = self.relation_operator.execute(
                    evidence_tokens_i=evidence_tokens_i,
                    geometry_tokens_i=geometry_tokens_i,
                    ortho_tokens_i=ortho_tokens_i,
                    class_probs_i=class_probs_i,
                    points_xyz_i=points_xyz_i,
                    input_mask_i=input_mask,
                    step_token=step_token,
                    relation=relation,
                    valid_mask_i=valid_mask_i,
                )
                base_mask = outputs["mask"]
                step_reference_masks.append(outputs["reference_mask"])
                step_relation_evidence_maps.append(outputs["evidence_map"])
                relation_masks.append(base_mask)
                current_mask = (input_mask * base_mask).clamp(0.0, 1.0) * valid_mask_i.float()
            elif step.op == "exclude":
                input_mask = step_masks.get(step.input or "", _neutral_mask(valid_mask_i))
                label_ids = list(step.label_ids)
                base_negative_mask = self.negative_executor.execute_negative_mask(
                    class_probs_i,
                    label_ids,
                    valid_mask_i,
                )
                negative_masks.append(base_negative_mask)
                keep_mask = (1.0 - base_negative_mask).clamp(0.0, 1.0) * valid_mask_i.float()
                current_mask = (input_mask * keep_mask).clamp(0.0, 1.0) * valid_mask_i.float()
            elif step.op == "compose":
                source_ids = list(step.inputs)
                if not source_ids and step.input is not None:
                    source_ids = [step.input]
                masks = [step_masks[source_id] for source_id in source_ids if source_id in step_masks]
                logic = (step.logic or "AND").upper()
                if not masks:
                    current_mask = _neutral_mask(valid_mask_i)
                elif logic == "OR":
                    current_mask = _soft_or_masks(masks, valid_mask_i)
                elif logic == "NOT":
                    current_mask = (1.0 - masks[0]).clamp(0.0, 1.0) * valid_mask_i.float()
                else:
                    current_mask = _soft_and_masks(masks, valid_mask_i)
            step_masks[step.id] = current_mask

        final_mask = step_masks.get(program.output_step_id, list(step_masks.values())[-1] if step_masks else _neutral_mask(valid_mask_i))
        class_mask = class_masks[0] if class_masks else self.class_executor.execute_label_mask(
            class_probs_i,
            list(program.target_label_ids),
            valid_mask_i,
            reduction="mean",
        )
        attribute_mask = _soft_and_masks(attribute_masks, valid_mask_i) if attribute_masks else _neutral_mask(valid_mask_i)
        relation_mask = _soft_and_masks(relation_masks, valid_mask_i) if relation_masks else _neutral_mask(valid_mask_i)
        negative_mask = (
            torch.stack(negative_masks, dim=0).max(dim=0).values if negative_masks else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        keep_mask = (1.0 - negative_mask).clamp(0.0, 1.0) * valid_mask_i.float() if negative_masks else _neutral_mask(valid_mask_i)
        reference_mask = (
            torch.stack(step_reference_masks, dim=0).max(dim=0).values if step_reference_masks else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        attribute_evidence_map = (
            torch.stack(step_attr_evidence_maps, dim=0).mean(dim=0) if step_attr_evidence_maps else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        relation_evidence_map = (
            torch.stack(step_relation_evidence_maps, dim=0).mean(dim=0) if step_relation_evidence_maps else class_probs_i.new_zeros(class_probs_i.shape[0])
        ) * valid_mask_i.float()
        return {
            "class_mask": class_mask,
            "attribute_mask": attribute_mask,
            "relation_mask": relation_mask,
            "negative_mask": negative_mask,
            "keep_mask": keep_mask,
            "final_program_mask": final_mask * valid_mask_i.float(),
            "reference_mask": reference_mask,
            "attribute_evidence_map": attribute_evidence_map,
            "relation_evidence_map": relation_evidence_map,
        }

    def forward(
        self,
        point_tokens: torch.Tensor,
        geometry_tokens: torch.Tensor,
        ortho_point_tokens: torch.Tensor,
        class_logits: torch.Tensor,
        points_xyz: torch.Tensor,
        geometry_features: torch.Tensor,
        programs: Sequence[ProgramLike],
        valid_point_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        class_probs = torch.softmax(class_logits, dim=-1)
        evidence_outputs = self.evidence_extractor(
            point_tokens=point_tokens,
            geometry_tokens=geometry_tokens,
            ortho_point_tokens=ortho_point_tokens,
            points_xyz=points_xyz,
            geometry_features=geometry_features,
            valid_point_mask=valid_point_mask,
        )

        final_class_masks: List[torch.Tensor] = []
        final_attribute_masks: List[torch.Tensor] = []
        final_relation_masks: List[torch.Tensor] = []
        final_negative_masks: List[torch.Tensor] = []
        final_keep_masks: List[torch.Tensor] = []
        final_program_masks: List[torch.Tensor] = []
        final_reference_masks: List[torch.Tensor] = []
        final_attribute_evidence_maps: List[torch.Tensor] = []
        final_relation_evidence_maps: List[torch.Tensor] = []
        class_active = []
        attribute_active = []
        relation_active = []
        negative_active = []

        for batch_idx, program in enumerate(programs):
            common_kwargs = {
                "evidence_tokens_i": evidence_outputs["evidence_tokens"][batch_idx],
                "geometry_tokens_i": evidence_outputs["geometry_context_tokens"][batch_idx],
                "ortho_tokens_i": evidence_outputs["ortho_evidence_tokens"][batch_idx],
                "geometry_features_i": geometry_features[batch_idx],
                "class_probs_i": class_probs[batch_idx],
                "points_xyz_i": points_xyz[batch_idx],
                "valid_mask_i": valid_point_mask[batch_idx],
            }
            if isinstance(program, OperatorizedSpatialProgram) and program.steps:
                outputs = self._execute_operator_program(program=program, **common_kwargs)
            else:
                outputs = self._execute_field_program(program=program, **common_kwargs)

            final_class_masks.append(outputs["class_mask"])
            final_attribute_masks.append(outputs["attribute_mask"])
            final_relation_masks.append(outputs["relation_mask"])
            final_negative_masks.append(outputs["negative_mask"])
            final_keep_masks.append(outputs["keep_mask"])
            final_program_masks.append(outputs["final_program_mask"])
            final_reference_masks.append(outputs["reference_mask"])
            final_attribute_evidence_maps.append(outputs["attribute_evidence_map"])
            final_relation_evidence_maps.append(outputs["relation_evidence_map"])
            class_active.append(bool(program.target_label_ids))
            attribute_active.append(bool(program.attributes))
            relation_active.append(bool(program.relations))
            negative_active.append(bool(program.negative_label_ids))

        class_mask = torch.stack(final_class_masks, dim=0)
        attribute_mask = torch.stack(final_attribute_masks, dim=0)
        relation_mask = torch.stack(final_relation_masks, dim=0)
        negative_mask = torch.stack(final_negative_masks, dim=0)
        keep_mask = torch.stack(final_keep_masks, dim=0)
        final_program_mask = torch.stack(final_program_masks, dim=0)
        reference_mask = torch.stack(final_reference_masks, dim=0)
        attribute_evidence_map = torch.stack(final_attribute_evidence_maps, dim=0)
        relation_evidence_map = torch.stack(final_relation_evidence_maps, dim=0)
        program_mask_logits = _prob_to_logit(final_program_mask) * valid_point_mask.float()

        return {
            "class_mask": class_mask,
            "class_mask_logits": _prob_to_logit(class_mask),
            "class_active_mask": torch.tensor(class_active, dtype=torch.bool, device=valid_point_mask.device),
            "attribute_mask": attribute_mask,
            "attribute_mask_logits": _prob_to_logit(attribute_mask),
            "attribute_active_mask": torch.tensor(attribute_active, dtype=torch.bool, device=valid_point_mask.device),
            "relation_mask": relation_mask,
            "relation_mask_logits": _prob_to_logit(relation_mask),
            "relation_active_mask": torch.tensor(relation_active, dtype=torch.bool, device=valid_point_mask.device),
            "negative_mask": negative_mask,
            "negative_mask_logits": _prob_to_logit(negative_mask),
            "keep_mask": keep_mask,
            "keep_mask_logits": _prob_to_logit(keep_mask),
            "negative_active_mask": torch.tensor(negative_active, dtype=torch.bool, device=valid_point_mask.device),
            "reference_mask": reference_mask,
            "reference_mask_logits": _prob_to_logit(reference_mask),
            "attribute_evidence_map": attribute_evidence_map,
            "relation_evidence_map": relation_evidence_map,
            "final_program_mask": final_program_mask,
            "program_mask_logits": program_mask_logits,
            "target_score": class_mask,
            "attribute_score": attribute_mask,
            "relation_score": relation_mask,
            "negative_score": negative_mask,
            "execution_logits": program_mask_logits,
        }

    def forward_bundles(
        self,
        point_tokens: torch.Tensor,
        geometry_tokens: torch.Tensor,
        ortho_point_tokens: torch.Tensor,
        class_logits: torch.Tensor,
        points_xyz: torch.Tensor,
        geometry_features: torch.Tensor,
        program_bundles: Sequence[ProgramBundle],
        valid_point_mask: torch.Tensor,
        query_hidden: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        selected_programs = [bundle.selected_program() for bundle in program_bundles]
        base_outputs = self.forward(
            point_tokens=point_tokens,
            geometry_tokens=geometry_tokens,
            ortho_point_tokens=ortho_point_tokens,
            class_logits=class_logits,
            points_xyz=points_xyz,
            geometry_features=geometry_features,
            programs=selected_programs,
            valid_point_mask=valid_point_mask,
        )

        class_probs = torch.softmax(class_logits, dim=-1)
        evidence_outputs = self.evidence_extractor(
            point_tokens=point_tokens,
            geometry_tokens=geometry_tokens,
            ortho_point_tokens=ortho_point_tokens,
            points_xyz=points_xyz,
            geometry_features=geometry_features,
            valid_point_mask=valid_point_mask,
        )

        batch_size, num_points = valid_point_mask.shape
        max_candidates = max((len(bundle.candidates) for bundle in program_bundles), default=1)
        candidate_program_masks_list: List[torch.Tensor] = []
        candidate_program_logits_list: List[torch.Tensor] = []
        candidate_scores_list: List[torch.Tensor] = []
        candidate_selector_logits_list: List[torch.Tensor] = []
        candidate_proposal_scores_list: List[torch.Tensor] = []
        candidate_posterior_logits_list: List[torch.Tensor] = []
        candidate_posterior_scores_list: List[torch.Tensor] = []
        verifier_scores_list: List[torch.Tensor] = []
        validity_scores_list: List[torch.Tensor] = []
        evidence_scores_list: List[torch.Tensor] = []
        no_target_scores_list: List[torch.Tensor] = []
        candidate_no_target_mask_list: List[torch.Tensor] = []
        candidate_active_mask_list: List[torch.Tensor] = []
        abstain_logits_list: List[torch.Tensor] = []
        selected_candidate_idx_list: List[int] = []
        selected_program_mask_list: List[torch.Tensor] = []
        selected_program_logits_list: List[torch.Tensor] = []
        selected_verifier_score_list: List[torch.Tensor] = []
        marginal_class_mask_list: List[torch.Tensor] = []
        marginal_attribute_mask_list: List[torch.Tensor] = []
        marginal_relation_mask_list: List[torch.Tensor] = []
        marginal_negative_mask_list: List[torch.Tensor] = []
        marginal_keep_mask_list: List[torch.Tensor] = []
        marginal_reference_mask_list: List[torch.Tensor] = []
        marginal_attribute_evidence_map_list: List[torch.Tensor] = []
        marginal_relation_evidence_map_list: List[torch.Tensor] = []
        marginal_program_mask_list: List[torch.Tensor] = []
        selected_class_mask_list: List[torch.Tensor] = []
        selected_attribute_mask_list: List[torch.Tensor] = []
        selected_relation_mask_list: List[torch.Tensor] = []
        selected_negative_mask_list: List[torch.Tensor] = []
        selected_keep_mask_list: List[torch.Tensor] = []
        selected_reference_mask_list: List[torch.Tensor] = []
        selected_attribute_evidence_map_list: List[torch.Tensor] = []
        selected_relation_evidence_map_list: List[torch.Tensor] = []
        class_active_mask_list: List[bool] = []
        attribute_active_mask_list: List[bool] = []
        relation_active_mask_list: List[bool] = []
        negative_active_mask_list: List[bool] = []
        abstain_mask_list: List[bool] = []
        selected_candidate_is_no_target_list: List[bool] = []
        posterior_no_target_mass_list: List[torch.Tensor] = []
        selected_program_texts: List[str] = []
        selected_program_dicts: List[Dict[str, object]] = []

        def _pad_candidate_tensor(values: torch.Tensor, pad_value: float) -> torch.Tensor:
            pad_count = max_candidates - values.shape[0]
            if pad_count <= 0:
                return values
            pad = values.new_full((pad_count,), float(pad_value))
            return torch.cat([values, pad], dim=0)

        def _pad_candidate_mask(values: torch.Tensor) -> torch.Tensor:
            pad_count = max_candidates - values.shape[0]
            if pad_count <= 0:
                return values
            pad = values.new_zeros((pad_count, num_points))
            return torch.cat([values, pad], dim=0)

        for batch_idx, bundle in enumerate(program_bundles):
            bundle_candidate_selector_logits: List[torch.Tensor] = []
            bundle_outputs: List[Dict[str, torch.Tensor]] = []
            bundle_candidate_program_logits: List[torch.Tensor] = []
            bundle_verifier_scores: List[torch.Tensor] = []
            bundle_validity_scores: List[torch.Tensor] = []
            bundle_evidence_scores: List[torch.Tensor] = []
            bundle_no_target_scores: List[torch.Tensor] = []
            bundle_proposal_scores: List[float] = []
            bundle_no_target_flags: List[bool] = []
            query_token = query_hidden[batch_idx] if query_hidden is not None else _masked_mean(
                evidence_outputs["evidence_tokens"][batch_idx],
                valid_point_mask[batch_idx],
            )
            scene_summary = _masked_mean(
                evidence_outputs["evidence_tokens"][batch_idx],
                valid_point_mask[batch_idx],
            )
            for cand_idx, candidate in enumerate(bundle.candidates[:max_candidates]):
                program = candidate.program
                candidate_metadata = dict(getattr(candidate, "metadata", {}))
                program_metadata = dict(getattr(program, "metadata", {}))
                is_no_target_candidate = bool(
                    candidate_metadata.get("no_target_candidate", False)
                    or program_metadata.get("no_target_candidate", False)
                    or str(candidate.proposal_source).strip().lower() == "explicit_no_target"
                )
                common_kwargs = {
                    "evidence_tokens_i": evidence_outputs["evidence_tokens"][batch_idx],
                    "geometry_tokens_i": evidence_outputs["geometry_context_tokens"][batch_idx],
                    "ortho_tokens_i": evidence_outputs["ortho_evidence_tokens"][batch_idx],
                    "geometry_features_i": geometry_features[batch_idx],
                    "class_probs_i": class_probs[batch_idx],
                    "points_xyz_i": points_xyz[batch_idx],
                    "valid_mask_i": valid_point_mask[batch_idx],
                }
                if isinstance(program, OperatorizedSpatialProgram) and program.steps:
                    outputs = self._execute_operator_program(program=program, **common_kwargs)
                else:
                    outputs = self._execute_field_program(program=program, **common_kwargs)
                verify = self.verifier(
                    outputs=outputs,
                    valid_point_mask=valid_point_mask[batch_idx],
                    proposal_score=float(candidate.proposal_score),
                    is_no_target_candidate=is_no_target_candidate,
                )
                selector_stats = self._candidate_selector_stats(
                    outputs=outputs,
                    verify=verify,
                    valid_point_mask=valid_point_mask[batch_idx],
                    proposal_score=float(candidate.proposal_score),
                    program=program,
                    is_no_target_candidate=is_no_target_candidate,
                )
                program_token = self._program_token(program, device=point_tokens.device)
                selection_score = self.latent_selector(
                    query_hidden=query_token,
                    scene_summary=scene_summary,
                    program_token=program_token,
                    stats=selector_stats,
                )
                bundle_candidate_selector_logits.append(selection_score)
                bundle_outputs.append(outputs)
                bundle_candidate_program_logits.append(
                    _prob_to_logit(outputs["final_program_mask"].clamp(MASK_EPS, 1.0 - MASK_EPS))
                    * valid_point_mask[batch_idx].float()
                )
                bundle_verifier_scores.append(verify["verifier_score"])
                bundle_validity_scores.append(verify["validity_score"])
                bundle_evidence_scores.append(verify["evidence_score"])
                bundle_no_target_scores.append(verify["no_target_score"])
                bundle_proposal_scores.append(float(getattr(candidate, "compiler_confidence", candidate.proposal_score)))
                bundle_no_target_flags.append(is_no_target_candidate)
            if not bundle_candidate_selector_logits:
                selected_program_texts.append(bundle.selected_program().to_canonical_text())
                selected_program_dicts.append(bundle.selected_program().to_dict())
                continue
            score_tensor = torch.stack(bundle_candidate_selector_logits)
            proposal_prior = point_tokens.new_tensor(bundle_proposal_scores).clamp_min(1e-4)
            proposal_prior = proposal_prior / proposal_prior.sum().clamp_min(1e-6)
            latent_logits = score_tensor + 0.15 * torch.log(proposal_prior)
            posterior = torch.softmax(latent_logits, dim=0)
            best_idx = int(torch.argmax(posterior).item())
            chosen_outputs = bundle_outputs[best_idx]
            candidate_masks = torch.stack([item["final_program_mask"] for item in bundle_outputs], dim=0)
            candidate_program_logits = torch.stack(bundle_candidate_program_logits, dim=0)
            verifier_tensor = torch.stack(bundle_verifier_scores, dim=0)
            validity_tensor = torch.stack(bundle_validity_scores, dim=0)
            evidence_tensor = torch.stack(bundle_evidence_scores, dim=0)
            no_target_tensor = torch.stack(bundle_no_target_scores, dim=0)
            no_target_flag_tensor = torch.tensor(bundle_no_target_flags, dtype=torch.bool, device=point_tokens.device)
            weight_view = posterior.unsqueeze(-1)
            marginal_class_mask = (weight_view * torch.stack([item["class_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_attribute_mask = (weight_view * torch.stack([item["attribute_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_relation_mask = (weight_view * torch.stack([item["relation_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_negative_mask = (weight_view * torch.stack([item["negative_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_keep_mask = (weight_view * torch.stack([item["keep_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_reference_mask = (weight_view * torch.stack([item["reference_mask"] for item in bundle_outputs], dim=0)).sum(dim=0)
            marginal_attribute_evidence_map = (
                weight_view * torch.stack([item["attribute_evidence_map"] for item in bundle_outputs], dim=0)
            ).sum(dim=0)
            marginal_relation_evidence_map = (
                weight_view * torch.stack([item["relation_evidence_map"] for item in bundle_outputs], dim=0)
            ).sum(dim=0)
            marginal_program_mask = (weight_view * candidate_masks).sum(dim=0)
            selected_program_mask = chosen_outputs["final_program_mask"]
            selected_program_logits = _prob_to_logit(
                chosen_outputs["final_program_mask"].clamp(MASK_EPS, 1.0 - MASK_EPS)
            ) * valid_point_mask[batch_idx].float()
            selected_verifier_score = verifier_tensor[best_idx]
            selected_class_mask = chosen_outputs["class_mask"]
            selected_attribute_mask = chosen_outputs["attribute_mask"]
            selected_relation_mask = chosen_outputs["relation_mask"]
            selected_negative_mask = chosen_outputs["negative_mask"]
            selected_keep_mask = chosen_outputs["keep_mask"]
            selected_reference_mask = chosen_outputs["reference_mask"]
            selected_attribute_evidence_map = chosen_outputs["attribute_evidence_map"]
            selected_relation_evidence_map = chosen_outputs["relation_evidence_map"]
            selected_program = bundle.candidates[best_idx].program
            class_active_mask = any(
                bool(bundle.candidates[cand_idx].program.target_label_ids) and float(posterior[cand_idx].item()) > 1e-3
                for cand_idx in range(len(bundle_outputs))
            )
            attribute_active_mask = any(
                bool(bundle.candidates[cand_idx].program.attributes) and float(posterior[cand_idx].item()) > 1e-3
                for cand_idx in range(len(bundle_outputs))
            )
            relation_active_mask = any(
                bool(bundle.candidates[cand_idx].program.relations) and float(posterior[cand_idx].item()) > 1e-3
                for cand_idx in range(len(bundle_outputs))
            )
            negative_active_mask = any(
                bool(bundle.candidates[cand_idx].program.negative_label_ids) and float(posterior[cand_idx].item()) > 1e-3
                for cand_idx in range(len(bundle_outputs))
            )
            selected_candidate_is_no_target = bool(no_target_flag_tensor[best_idx].item())
            selected_program_texts.append(selected_program.to_canonical_text())
            selected_program_dicts.append(selected_program.to_dict())
            posterior_positive_score = (posterior * verifier_tensor).sum()
            posterior_negative_score = (posterior * no_target_tensor).sum()
            posterior_no_target_mass = (posterior * no_target_flag_tensor.float()).sum()
            abstain_logit = (
                4.0 * (posterior_negative_score - posterior_positive_score)
                + 3.0 * (posterior_no_target_mass - 0.5)
            )
            abstain_mask = bool(torch.sigmoid(abstain_logit).item() >= 0.5)

            pad_count = max_candidates - candidate_masks.shape[0]
            if pad_count > 0:
                candidate_program_logits = _pad_candidate_mask(candidate_program_logits)
                candidate_masks = _pad_candidate_mask(candidate_masks)
            candidate_scores = _pad_candidate_tensor(score_tensor, -1e4)
            candidate_selector_logits = _pad_candidate_tensor(score_tensor, -1e4)
            candidate_proposal_scores = _pad_candidate_tensor(point_tokens.new_tensor(bundle_proposal_scores), -1e4)
            candidate_posterior_logits = _pad_candidate_tensor(latent_logits, -1e4)
            candidate_posterior_scores = _pad_candidate_tensor(posterior, 0.0)
            verifier_scores = _pad_candidate_tensor(verifier_tensor, 0.0)
            validity_scores = _pad_candidate_tensor(validity_tensor, 0.0)
            evidence_scores = _pad_candidate_tensor(evidence_tensor, 0.0)
            no_target_scores = _pad_candidate_tensor(no_target_tensor, 0.0)
            if pad_count > 0:
                candidate_no_target_mask = torch.cat(
                    [no_target_flag_tensor, torch.zeros((pad_count,), dtype=torch.bool, device=point_tokens.device)],
                    dim=0,
                )
                candidate_active_mask = torch.cat(
                    [
                        torch.ones((candidate_masks.shape[0] - pad_count,), dtype=torch.bool, device=point_tokens.device),
                        torch.zeros((pad_count,), dtype=torch.bool, device=point_tokens.device),
                    ],
                    dim=0,
                )
            else:
                candidate_no_target_mask = no_target_flag_tensor
                candidate_active_mask = torch.ones((candidate_masks.shape[0],), dtype=torch.bool, device=point_tokens.device)

            candidate_program_masks_list.append(candidate_masks)
            candidate_program_logits_list.append(candidate_program_logits)
            candidate_scores_list.append(candidate_scores)
            candidate_selector_logits_list.append(candidate_selector_logits)
            candidate_proposal_scores_list.append(candidate_proposal_scores)
            candidate_posterior_logits_list.append(candidate_posterior_logits)
            candidate_posterior_scores_list.append(candidate_posterior_scores)
            verifier_scores_list.append(verifier_scores)
            validity_scores_list.append(validity_scores)
            evidence_scores_list.append(evidence_scores)
            no_target_scores_list.append(no_target_scores)
            candidate_no_target_mask_list.append(candidate_no_target_mask)
            candidate_active_mask_list.append(candidate_active_mask)
            abstain_logits_list.append(abstain_logit)
            selected_candidate_idx_list.append(best_idx)
            selected_program_mask_list.append(selected_program_mask)
            selected_program_logits_list.append(selected_program_logits)
            selected_verifier_score_list.append(selected_verifier_score)
            marginal_class_mask_list.append(marginal_class_mask)
            marginal_attribute_mask_list.append(marginal_attribute_mask)
            marginal_relation_mask_list.append(marginal_relation_mask)
            marginal_negative_mask_list.append(marginal_negative_mask)
            marginal_keep_mask_list.append(marginal_keep_mask)
            marginal_reference_mask_list.append(marginal_reference_mask)
            marginal_attribute_evidence_map_list.append(marginal_attribute_evidence_map)
            marginal_relation_evidence_map_list.append(marginal_relation_evidence_map)
            marginal_program_mask_list.append(marginal_program_mask)
            selected_class_mask_list.append(selected_class_mask)
            selected_attribute_mask_list.append(selected_attribute_mask)
            selected_relation_mask_list.append(selected_relation_mask)
            selected_negative_mask_list.append(selected_negative_mask)
            selected_keep_mask_list.append(selected_keep_mask)
            selected_reference_mask_list.append(selected_reference_mask)
            selected_attribute_evidence_map_list.append(selected_attribute_evidence_map)
            selected_relation_evidence_map_list.append(selected_relation_evidence_map)
            class_active_mask_list.append(class_active_mask)
            attribute_active_mask_list.append(attribute_active_mask)
            relation_active_mask_list.append(relation_active_mask)
            negative_active_mask_list.append(negative_active_mask)
            abstain_mask_list.append(abstain_mask)
            selected_candidate_is_no_target_list.append(selected_candidate_is_no_target)
            posterior_no_target_mass_list.append(posterior_no_target_mass)

        candidate_program_masks = torch.stack(candidate_program_masks_list, dim=0)
        candidate_program_logits = torch.stack(candidate_program_logits_list, dim=0)
        candidate_scores = torch.stack(candidate_scores_list, dim=0)
        candidate_selector_logits = torch.stack(candidate_selector_logits_list, dim=0)
        candidate_proposal_scores = torch.stack(candidate_proposal_scores_list, dim=0)
        candidate_posterior_logits = torch.stack(candidate_posterior_logits_list, dim=0)
        candidate_posterior_scores = torch.stack(candidate_posterior_scores_list, dim=0)
        verifier_scores = torch.stack(verifier_scores_list, dim=0)
        validity_scores = torch.stack(validity_scores_list, dim=0)
        evidence_scores = torch.stack(evidence_scores_list, dim=0)
        no_target_scores = torch.stack(no_target_scores_list, dim=0)
        candidate_no_target_mask = torch.stack(candidate_no_target_mask_list, dim=0)
        candidate_active_mask = torch.stack(candidate_active_mask_list, dim=0)
        abstain_logits = torch.stack(abstain_logits_list, dim=0)
        selected_candidate_idx = torch.tensor(selected_candidate_idx_list, dtype=torch.long, device=point_tokens.device)
        selected_program_mask = torch.stack(selected_program_mask_list, dim=0)
        selected_program_logits = torch.stack(selected_program_logits_list, dim=0)
        selected_verifier_score = torch.stack(selected_verifier_score_list, dim=0)
        marginal_class_mask = torch.stack(marginal_class_mask_list, dim=0)
        marginal_attribute_mask = torch.stack(marginal_attribute_mask_list, dim=0)
        marginal_relation_mask = torch.stack(marginal_relation_mask_list, dim=0)
        marginal_negative_mask = torch.stack(marginal_negative_mask_list, dim=0)
        marginal_keep_mask = torch.stack(marginal_keep_mask_list, dim=0)
        marginal_reference_mask = torch.stack(marginal_reference_mask_list, dim=0)
        marginal_attribute_evidence_map = torch.stack(marginal_attribute_evidence_map_list, dim=0)
        marginal_relation_evidence_map = torch.stack(marginal_relation_evidence_map_list, dim=0)
        marginal_program_mask = torch.stack(marginal_program_mask_list, dim=0)
        selected_class_mask = torch.stack(selected_class_mask_list, dim=0)
        selected_attribute_mask = torch.stack(selected_attribute_mask_list, dim=0)
        selected_relation_mask = torch.stack(selected_relation_mask_list, dim=0)
        selected_negative_mask = torch.stack(selected_negative_mask_list, dim=0)
        selected_keep_mask = torch.stack(selected_keep_mask_list, dim=0)
        selected_reference_mask = torch.stack(selected_reference_mask_list, dim=0)
        selected_attribute_evidence_map = torch.stack(selected_attribute_evidence_map_list, dim=0)
        selected_relation_evidence_map = torch.stack(selected_relation_evidence_map_list, dim=0)
        class_active_mask = torch.tensor(class_active_mask_list, dtype=torch.bool, device=point_tokens.device)
        attribute_active_mask = torch.tensor(attribute_active_mask_list, dtype=torch.bool, device=point_tokens.device)
        relation_active_mask = torch.tensor(relation_active_mask_list, dtype=torch.bool, device=point_tokens.device)
        negative_active_mask = torch.tensor(negative_active_mask_list, dtype=torch.bool, device=point_tokens.device)
        abstain_mask = torch.tensor(abstain_mask_list, dtype=torch.bool, device=point_tokens.device)
        selected_candidate_is_no_target = torch.tensor(
            selected_candidate_is_no_target_list,
            dtype=torch.bool,
            device=point_tokens.device,
        )
        posterior_no_target_mass = torch.stack(posterior_no_target_mass_list, dim=0)

        execution_confidence = (1.0 - torch.sigmoid(abstain_logits)).unsqueeze(-1)
        final_program_mask = marginal_program_mask * execution_confidence * valid_point_mask.float()
        program_mask_logits = _prob_to_logit(final_program_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)) * valid_point_mask.float()

        outputs = dict(base_outputs)
        outputs.update(
            {
                "class_mask": marginal_class_mask,
                "class_mask_logits": _prob_to_logit(marginal_class_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "class_active_mask": class_active_mask,
                "attribute_mask": marginal_attribute_mask,
                "attribute_mask_logits": _prob_to_logit(marginal_attribute_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "attribute_active_mask": attribute_active_mask,
                "relation_mask": marginal_relation_mask,
                "relation_mask_logits": _prob_to_logit(marginal_relation_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "relation_active_mask": relation_active_mask,
                "negative_mask": marginal_negative_mask,
                "negative_mask_logits": _prob_to_logit(marginal_negative_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "keep_mask": marginal_keep_mask,
                "keep_mask_logits": _prob_to_logit(marginal_keep_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "negative_active_mask": negative_active_mask,
                "reference_mask": marginal_reference_mask,
                "reference_mask_logits": _prob_to_logit(marginal_reference_mask.clamp(MASK_EPS, 1.0 - MASK_EPS)),
                "attribute_evidence_map": marginal_attribute_evidence_map,
                "relation_evidence_map": marginal_relation_evidence_map,
                "candidate_program_mask": candidate_program_masks,
                "candidate_program_logits": candidate_program_logits,
                "candidate_scores": candidate_scores,
                "candidate_selector_logits": candidate_selector_logits,
                "candidate_proposal_scores": candidate_proposal_scores,
                "candidate_posterior_logits": candidate_posterior_logits,
                "candidate_posterior_scores": candidate_posterior_scores,
                "verification_scores": verifier_scores,
                "validity_scores": validity_scores,
                "evidence_scores": evidence_scores,
                "no_target_scores": no_target_scores,
                "candidate_no_target_mask": candidate_no_target_mask,
                "candidate_active_mask": candidate_active_mask,
                "selected_candidate_idx": selected_candidate_idx,
                "selected_candidate_is_no_target": selected_candidate_is_no_target,
                "selected_program_mask": selected_program_mask,
                "selected_verifier_score": selected_verifier_score,
                "execution_confidence": execution_confidence.squeeze(-1),
                "abstain_logits": abstain_logits,
                "abstain_mask": abstain_mask,
                "posterior_no_target_mass": posterior_no_target_mass,
                "marginal_program_mask": marginal_program_mask,
                "selected_class_mask": selected_class_mask,
                "selected_attribute_mask": selected_attribute_mask,
                "selected_relation_mask": selected_relation_mask,
                "selected_negative_mask": selected_negative_mask,
                "selected_keep_mask": selected_keep_mask,
                "selected_reference_mask": selected_reference_mask,
                "selected_attribute_evidence_map": selected_attribute_evidence_map,
                "selected_relation_evidence_map": selected_relation_evidence_map,
                "final_program_mask": final_program_mask,
                "program_mask_logits": program_mask_logits,
                "mask_selection_mode": "latent_posterior_marginalization",
                "selected_program_texts": selected_program_texts,
                "selected_program_dicts": selected_program_dicts,
            }
        )
        return outputs


class CandidateVerifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.feature_proj = nn.Sequential(
            nn.LayerNorm(4),
            nn.Linear(4, 16),
            nn.GELU(),
            nn.Linear(16, 2),
        )

    def forward(
        self,
        outputs: Dict[str, torch.Tensor],
        valid_point_mask: torch.Tensor,
        proposal_score: float,
        is_no_target_candidate: bool = False,
    ) -> Dict[str, torch.Tensor]:
        valid = valid_point_mask.float()
        denom = valid.sum().clamp_min(1.0)
        final_mask = outputs["final_program_mask"] * valid
        class_mask = outputs["class_mask"] * valid
        attribute_evidence = outputs["attribute_evidence_map"] * valid
        relation_evidence = outputs["relation_evidence_map"] * valid
        reference_mask = outputs["reference_mask"] * valid

        mask_mass = final_mask.sum() / denom
        evidence_mean = (attribute_evidence.sum() + relation_evidence.sum() + 0.5 * reference_mask.sum()) / (2.5 * denom)
        class_alignment = (final_mask * class_mask).sum() / final_mask.sum().clamp_min(1e-4)
        validity_score = class_alignment.clamp(0.0, 1.0)
        evidence_score = evidence_mean.clamp(0.0, 1.0)
        no_target_score = (1.0 - mask_mass).clamp(0.0, 1.0) * (1.0 - evidence_score).clamp(0.0, 1.0)
        proposal_tensor = final_mask.new_tensor(float(proposal_score))
        features = torch.stack([mask_mass, validity_score, evidence_score, proposal_tensor], dim=0).unsqueeze(0)
        score_logits = self.feature_proj(features).squeeze(0)
        verifier_score = torch.sigmoid(score_logits[0])
        learned_no_target = torch.sigmoid(score_logits[1])
        no_target_score = (0.5 * no_target_score + 0.5 * learned_no_target).clamp(0.0, 1.0)
        if bool(is_no_target_candidate):
            final_score = (0.7 * no_target_score + 0.3 * proposal_tensor.clamp(0.0, 1.0)).clamp(0.0, 1.0)
        else:
            final_score = verifier_score - 0.35 * no_target_score
        return {
            "validity_score": validity_score,
            "evidence_score": evidence_score,
            "no_target_score": no_target_score,
            "verifier_score": verifier_score,
            "final_score": final_score,
        }
