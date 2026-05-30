from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

import torch
import torch.nn as nn

from wcs_unified.model_stage_a import (
    ClipTextTokenEncoder,
    CrossAttentionBlock,
    GUFNetSPVPointEncoder,
    ImageTokenEncoder,
    OpenSceneSparsePointEncoder,
    OrthoSpatialPriorEncoder,
    PointMLPEncoder,
    PointRefineBlock,
    QueryMaskHead,
    SimpleTextTokenEncoder,
)

from .program_executor import ProgramExecutor
from .query_program import HydrologicalQueryCompiler, QueryCompilerConfig
from .schema import HydrologicalProgram, OperatorizedSpatialProgram, ProgramBundle, ProgramLike, bundle_from_dict, program_from_dict


class HydroProgram3D(nn.Module):
    def __init__(
        self,
        hidden_dim: int = 128,
        num_classes: int = 15,
        geometry_feature_dim: int = 4,
        point_encoder_type: str = "mlp",
        text_encoder_type: str = "simple",
        clip_model_name: str = "ViT-B-32",
        clip_pretrained: str = "openai",
        clip_local_dir: Optional[str] = None,
        use_ortho_prior: bool = True,
        ortho_token_grid: int = 16,
        ortho_y_flip: bool = True,
        voxel_size: float = 0.05,
        spv_scale_list: Sequence[int] = (2, 4, 8, 16),
        spv_spatial_shape: Sequence[int] = (23088, 73472, 880),
        spv_min_volume_space: Sequence[float] = (-4654.0, -5286.0, -88.0),
        spv_max_volume_space: Sequence[float] = (1116.0, 13082.0, 129.0),
        point_chunk_size: int = 4096,
        compiler: Optional[HydrologicalQueryCompiler] = None,
        use_program_executor: bool = True,
        text_source: str = "raw",
        program_residual_weight: float = 0.15,
        program_schema_mode: str = "field",
        program_version: str = "v3_operatorized",
    ) -> None:
        super().__init__()
        self.hidden_dim = int(hidden_dim)
        self.num_classes = int(num_classes)
        self.geometry_feature_dim = int(geometry_feature_dim)
        self.use_ortho_prior = bool(use_ortho_prior)
        self.point_chunk_size = int(point_chunk_size)
        self.program_schema_mode = str(program_schema_mode)
        self.program_version = str(program_version)
        self.compiler = compiler or HydrologicalQueryCompiler(
            config=QueryCompilerConfig(
                program_schema_mode=self.program_schema_mode,
                program_version=self.program_version,
            )
        )
        self.use_program_executor = bool(use_program_executor)
        self.text_source = str(text_source)
        self.program_residual_weight = float(program_residual_weight)
        if self.text_source not in {"program", "raw"}:
            raise ValueError(f"Unsupported text_source={self.text_source!r}, expected 'program' or 'raw'.")
        self.model_variant = "program" if self.use_program_executor else "direct_matching"
        normalized_point_encoder = str(point_encoder_type).strip().lower()
        if normalized_point_encoder == "spvcnn":
            normalized_point_encoder = "spconv"

        if normalized_point_encoder == "openscene":
            self.point_encoder = OpenSceneSparsePointEncoder(
                hidden_dim=hidden_dim,
                arch_3d="MinkUNet18A",
                voxel_size=voxel_size,
            )
            self.point_encoder_type = "openscene"
        elif normalized_point_encoder == "spconv":
            self.point_encoder = GUFNetSPVPointEncoder(
                hidden_dim=hidden_dim,
                input_dims=6,
                scale_list=tuple(spv_scale_list),
                spatial_shape=tuple(spv_spatial_shape),
                min_volume_space=tuple(spv_min_volume_space),
                max_volume_space=tuple(spv_max_volume_space),
            )
            self.point_encoder_type = "spconv"
        else:
            self.point_encoder = PointMLPEncoder(in_dim=6, hidden_dim=hidden_dim)
            self.point_encoder_type = "mlp"

        if self.use_ortho_prior:
            self.image_encoder = OrthoSpatialPriorEncoder(
                out_dim=hidden_dim,
                token_grid=ortho_token_grid,
                y_flip=ortho_y_flip,
            )
            self.ortho_point_proj = nn.Sequential(
                nn.LayerNorm(hidden_dim),
                nn.Linear(hidden_dim, hidden_dim),
                nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim),
            )
            self.ortho_point_gate = nn.Sequential(
                nn.LayerNorm(hidden_dim * 2),
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Sigmoid(),
            )
        else:
            self.image_encoder = ImageTokenEncoder(out_dim=hidden_dim, token_grid=ortho_token_grid)
            self.ortho_point_proj = None
            self.ortho_point_gate = None

        self.geometry_proj = nn.Sequential(
            nn.LayerNorm(geometry_feature_dim),
            nn.Linear(geometry_feature_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.geometry_gate = nn.Sequential(
            nn.LayerNorm(hidden_dim * 2),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Sigmoid(),
        )

        if text_encoder_type == "clip":
            self.text_encoder = ClipTextTokenEncoder(
                model_name=clip_model_name,
                pretrained=clip_pretrained,
                out_dim=hidden_dim,
                local_dir=clip_local_dir,
            )
        else:
            self.text_encoder = SimpleTextTokenEncoder(out_dim=hidden_dim)

        self.text_to_point = CrossAttentionBlock(dim=hidden_dim, num_heads=4, query_chunk_size=point_chunk_size)
        self.image_to_point = CrossAttentionBlock(dim=hidden_dim, num_heads=4, query_chunk_size=point_chunk_size)
        self.point_refine = PointRefineBlock(dim=hidden_dim, chunk_size=point_chunk_size)
        self.query_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.class_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_classes),
        )
        self.base_mask_head = QueryMaskHead(hidden_dim=hidden_dim, chunk_size=point_chunk_size)
        self.program_executor = ProgramExecutor(
            hidden_dim=hidden_dim,
            geometry_feature_dim=geometry_feature_dim,
            num_classes=num_classes,
            point_chunk_size=point_chunk_size,
        )

    def get_model_config(self) -> Dict[str, Union[int, float, str, bool, Sequence[int], Sequence[float], None]]:
        return {
            "hidden_dim": self.hidden_dim,
            "num_classes": self.num_classes,
            "geometry_feature_dim": self.geometry_feature_dim,
            "point_encoder_type": self.point_encoder_type,
            "text_encoder_type": "clip" if isinstance(self.text_encoder, ClipTextTokenEncoder) else "simple",
            "use_ortho_prior": self.use_ortho_prior,
            "point_chunk_size": self.point_chunk_size,
            "use_program_executor": self.use_program_executor,
            "text_source": self.text_source,
            "program_residual_weight": self.program_residual_weight,
            "program_schema_mode": self.program_schema_mode,
            "program_version": self.program_version,
        }

    def _program_objects(
        self,
        programs: Optional[Sequence[Union[ProgramLike, Dict]]],
        program_bundles: Optional[Sequence[Union[ProgramBundle, Dict]]],
        texts: Optional[List[str]],
    ) -> List[ProgramLike]:
        if program_bundles is not None:
            outputs = []
            for item in program_bundles:
                if isinstance(item, ProgramBundle):
                    outputs.append(item.selected_program())
                else:
                    outputs.append(bundle_from_dict(item).selected_program())
            return outputs
        if programs is not None:
            outputs = []
            for item in programs:
                if isinstance(item, (HydrologicalProgram, OperatorizedSpatialProgram)):
                    outputs.append(item)
                else:
                    outputs.append(program_from_dict(item))
            return outputs
        if texts is None:
            raise ValueError("HydroProgram3D.forward requires either programs or texts.")
        return [self.compiler.compile_text(text) for text in texts]

    def _bundle_objects(
        self,
        program_bundles: Optional[Sequence[Union[ProgramBundle, Dict]]],
    ) -> Optional[List[ProgramBundle]]:
        if program_bundles is None:
            return None
        outputs: List[ProgramBundle] = []
        for item in program_bundles:
            if isinstance(item, ProgramBundle):
                outputs.append(item)
            else:
                outputs.append(bundle_from_dict(item))
        return outputs

    def _text_inputs(
        self,
        program_objects: Sequence[ProgramLike],
        texts: Optional[List[str]],
    ) -> List[str]:
        if self.text_source == "raw":
            if texts is not None:
                return list(texts)
            return [program.source_text or program.to_canonical_text() for program in program_objects]
        return [program.to_canonical_text() for program in program_objects]

    def forward(
        self,
        images: torch.Tensor,
        points_xyz: torch.Tensor,
        points_rgb: torch.Tensor,
        point_geometry_features: torch.Tensor,
        programs: Optional[Sequence[Union[ProgramLike, Dict]]] = None,
        program_bundles: Optional[Sequence[Union[ProgramBundle, Dict]]] = None,
        texts: Optional[List[str]] = None,
        valid_point_mask: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        bundle_objects = self._bundle_objects(program_bundles)
        program_objects = self._program_objects(programs, program_bundles, texts)
        device = points_xyz.device
        if valid_point_mask is None:
            valid_point_mask = torch.ones(points_xyz.shape[:2], dtype=torch.bool, device=device)
        text_inputs = self._text_inputs(program_objects, texts)
        valid_mask_float = valid_point_mask.unsqueeze(-1).float() if valid_point_mask is not None else None

        if self.point_encoder_type in {"openscene", "spconv"}:
            point_tokens = self.point_encoder(points_xyz, points_rgb, valid_point_mask=valid_point_mask)
        else:
            point_tokens = self.point_encoder(points_xyz, points_rgb)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float

        geometry_tokens = self.geometry_proj(point_geometry_features.to(device))
        if valid_mask_float is not None:
            geometry_tokens = geometry_tokens * valid_mask_float
        geometry_gate = self.geometry_gate(torch.cat([point_tokens, geometry_tokens], dim=-1))
        point_tokens = point_tokens + geometry_gate * geometry_tokens
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float

        if self.use_ortho_prior:
            image_tokens, ortho_point_tokens = self.image_encoder(images, points_xyz, valid_point_mask=valid_point_mask)
            ortho_point_tokens = self.ortho_point_proj(ortho_point_tokens)
            if valid_mask_float is not None:
                ortho_point_tokens = ortho_point_tokens * valid_mask_float
            ortho_gate = self.ortho_point_gate(torch.cat([point_tokens, ortho_point_tokens], dim=-1))
            point_tokens = point_tokens + ortho_gate * ortho_point_tokens
            if valid_mask_float is not None:
                point_tokens = point_tokens * valid_mask_float
        else:
            image_tokens = self.image_encoder(images)
            ortho_point_tokens = torch.zeros_like(point_tokens)

        text_tokens = self.text_encoder(text_inputs, device=device)
        point_tokens = self.text_to_point(point_tokens, text_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float
        point_tokens = self.image_to_point(point_tokens, image_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float
        point_tokens = self.point_refine(point_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float

        query_hidden = self.query_proj(text_tokens.mean(dim=1))
        class_logits = self.class_head(point_tokens)
        base_mask_logits = self.base_mask_head(point_tokens, query_hidden)
        if self.use_program_executor:
            if bundle_objects is not None:
                executor_outputs = self.program_executor.forward_bundles(
                    point_tokens=point_tokens,
                    geometry_tokens=geometry_tokens,
                    ortho_point_tokens=ortho_point_tokens,
                    class_logits=class_logits,
                    points_xyz=points_xyz,
                    geometry_features=point_geometry_features,
                    program_bundles=bundle_objects,
                    valid_point_mask=valid_point_mask,
                    query_hidden=query_hidden,
                )
                program_texts = list(executor_outputs.get("selected_program_texts", [bundle.selected_program().to_canonical_text() for bundle in bundle_objects]))
            else:
                executor_outputs = self.program_executor(
                    point_tokens=point_tokens,
                    geometry_tokens=geometry_tokens,
                    ortho_point_tokens=ortho_point_tokens,
                    class_logits=class_logits,
                    points_xyz=points_xyz,
                    geometry_features=point_geometry_features,
                    programs=program_objects,
                    valid_point_mask=valid_point_mask,
                )
                program_texts = [program.to_canonical_text() for program in program_objects]
            mask_logits = executor_outputs["program_mask_logits"] + self.program_residual_weight * base_mask_logits
        else:
            zeros = base_mask_logits.new_zeros(base_mask_logits.shape)
            neutral_mask = valid_point_mask.float()
            inactive_batch_mask = torch.zeros(point_tokens.shape[0], dtype=torch.bool, device=device)
            executor_outputs = {
                "class_mask": zeros,
                "class_mask_logits": zeros,
                "class_active_mask": inactive_batch_mask,
                "attribute_mask": neutral_mask,
                "attribute_mask_logits": zeros,
                "attribute_active_mask": inactive_batch_mask,
                "relation_mask": neutral_mask,
                "relation_mask_logits": zeros,
                "relation_active_mask": inactive_batch_mask,
                "negative_mask": zeros,
                "negative_mask_logits": zeros,
                "keep_mask": neutral_mask,
                "keep_mask_logits": zeros,
                "negative_active_mask": inactive_batch_mask,
                "reference_mask": zeros,
                "reference_mask_logits": zeros,
                "attribute_evidence_map": zeros,
                "relation_evidence_map": zeros,
                "final_program_mask": zeros,
                "program_mask_logits": zeros,
                "target_score": zeros,
                "attribute_score": neutral_mask,
                "relation_score": neutral_mask,
                "negative_score": zeros,
                "execution_logits": zeros,
            }
            mask_logits = base_mask_logits
            program_texts = [program.to_canonical_text() for program in program_objects]

        outputs = {
            "point_tokens": point_tokens,
            "geometry_tokens": geometry_tokens,
            "ortho_point_tokens": ortho_point_tokens,
            "query_hidden": query_hidden,
            "class_logits": class_logits,
            "base_mask_logits": base_mask_logits,
            "mask_logits": mask_logits,
            "program_texts": program_texts,
            "text_inputs": text_inputs,
            "model_variant": self.model_variant,
            "selected_program_count": torch.tensor(len(program_objects), device=device),
        }
        outputs.update(executor_outputs)
        return outputs
