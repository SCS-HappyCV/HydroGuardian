from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from wcs_unified.dataset import WCS_CLASS_NAMES

TRAIN_ID_TO_NAME = {idx: name for idx, name in enumerate(WCS_CLASS_NAMES)}
NAME_TO_TRAIN_ID = {name: idx for idx, name in TRAIN_ID_TO_NAME.items()}

LABEL_ALIASES = {
    "shed": "shed",
    "sheds": "shed",
    "house": "concrete house",
    "houses": "concrete house",
    "concrete house": "concrete house",
    "concrete houses": "concrete house",
    "cement road": "cement road",
    "cement roads": "cement road",
    "road": "cement road",
    "roads": "cement road",
    "dirt road": "dirt road",
    "dirt roads": "dirt road",
    "slope": "slope",
    "slopes": "slope",
    "scarp": "scarp",
    "scarps": "scarp",
    "dam": "dam",
    "dams": "dam",
    "vegetable field": "vegetable field",
    "vegetable fields": "vegetable field",
    "field": "vegetable field",
    "fields": "vegetable field",
    "grassland": "grassland",
    "grasslands": "grassland",
    "dryland": "dryland",
    "drylands": "dryland",
    "woodland": "woodland",
    "woodlands": "woodland",
    "bareland": "bareland",
    "barelands": "bareland",
    "waterline": "waterline",
    "water line": "waterline",
    "water edge": "waterline",
    "ditch": "ditch",
    "ditches": "ditch",
    "other": "others",
    "others": "others",
}

ATTRIBUTE_ALIASES = {
    "thin": "thin",
    "thin linear structures": "thin",
    "linear": "linear",
    "elongated": "linear",
    "flat": "flat",
    "steep": "steep",
    "low elevation": "low_elevation",
    "lower elevation": "low_elevation",
    "low-elevation": "low_elevation",
    "high elevation": "high_elevation",
    "higher elevation": "high_elevation",
    "high-elevation": "high_elevation",
    "water-related": "water_related",
    "water related": "water_related",
    "vegetated": "vegetated",
    "bare ground": "bare_ground",
    "built": "built",
    "engineered": "built",
}

RELATION_ALIASES = {
    "near": "near",
    "adjacent": "adjacent",
    "adjacent to": "adjacent",
    "along": "along",
    "above": "above",
    "below": "below",
}

DEFAULT_NEGATIVE_PRIORS = {
    "ditch": ["cement road", "dirt road"],
    "waterline": ["ditch", "cement road"],
    "cement road": ["ditch", "waterline", "dirt road"],
    "dirt road": ["cement road", "ditch"],
    "slope": ["scarp", "dam"],
    "scarp": ["slope"],
}

DEFAULT_EVIDENCE = {
    "thin": ["geometry", "ortho_edge"],
    "linear": ["geometry", "ortho_edge"],
    "flat": ["slope"],
    "steep": ["slope"],
    "low_elevation": ["z_norm"],
    "high_elevation": ["z_norm"],
    "water_related": ["ortho_texture", "geometry"],
    "vegetated": ["ortho_texture"],
    "bare_ground": ["ortho_texture"],
    "built": ["ortho_texture", "geometry"],
}


def canonicalize_label_name(name: str) -> Optional[str]:
    key = " ".join(name.strip().lower().replace("_", " ").split())
    if key in NAME_TO_TRAIN_ID:
        return key
    return LABEL_ALIASES.get(key)


def canonicalize_attribute_name(name: str) -> Optional[str]:
    key = " ".join(name.strip().lower().replace("_", " ").split())
    return ATTRIBUTE_ALIASES.get(key, key if key in ATTRIBUTE_ALIASES.values() else None)


def canonicalize_relation_type(name: str) -> Optional[str]:
    key = " ".join(name.strip().lower().replace("_", " ").split())
    return RELATION_ALIASES.get(key, key if key in RELATION_ALIASES.values() else None)


def label_ids_from_names(names: Sequence[str]) -> List[int]:
    ids: List[int] = []
    for name in names:
        canonical = canonicalize_label_name(name)
        if canonical is None:
            continue
        ids.append(NAME_TO_TRAIN_ID[canonical])
    return sorted(set(ids))


def label_names_from_ids(label_ids: Sequence[int]) -> List[str]:
    names = []
    for label_id in label_ids:
        if label_id in TRAIN_ID_TO_NAME:
            names.append(TRAIN_ID_TO_NAME[label_id])
    return names


@dataclass
class RelationClause:
    type: str
    reference: str
    reference_label_ids: List[int]
    distance_m: Optional[float] = None
    margin_m: Optional[float] = None
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "reference": self.reference,
            "reference_label_ids": list(self.reference_label_ids),
            "distance_m": self.distance_m,
            "margin_m": self.margin_m,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RelationClause":
        return cls(
            type=str(payload.get("type", "near")),
            reference=str(payload.get("reference", "")),
            reference_label_ids=[int(idx) for idx in payload.get("reference_label_ids", [])],
            distance_m=payload.get("distance_m"),
            margin_m=payload.get("margin_m"),
            evidence=[str(item) for item in payload.get("evidence", [])],
        )


@dataclass
class ProgramStep:
    id: str
    op: str
    input: Optional[str] = None
    inputs: List[str] = field(default_factory=list)
    label: Optional[str] = None
    label_ids: List[int] = field(default_factory=list)
    attribute: Optional[str] = None
    relation: Optional[str] = None
    reference_label: Optional[str] = None
    reference_label_ids: List[int] = field(default_factory=list)
    distance_m: Optional[float] = None
    margin_m: Optional[float] = None
    logic: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "input": self.input,
            "inputs": list(self.inputs),
            "label": self.label,
            "label_ids": list(self.label_ids),
            "attribute": self.attribute,
            "relation": self.relation,
            "reference_label": self.reference_label,
            "reference_label_ids": list(self.reference_label_ids),
            "distance_m": self.distance_m,
            "margin_m": self.margin_m,
            "logic": self.logic,
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProgramStep":
        label = payload.get("label")
        if label is not None:
            label = canonicalize_label_name(str(label)) or str(label)
        attribute = payload.get("attribute")
        if attribute is not None:
            attribute = canonicalize_attribute_name(str(attribute)) or str(attribute)
        relation = payload.get("relation")
        if relation is not None:
            relation = canonicalize_relation_type(str(relation)) or str(relation)
        reference_label = payload.get("reference_label")
        if reference_label is not None:
            reference_label = canonicalize_label_name(str(reference_label)) or str(reference_label)
        return cls(
            id=str(payload.get("id", "")),
            op=str(payload.get("op", "")),
            input=None if payload.get("input") is None else str(payload.get("input")),
            inputs=[str(item) for item in payload.get("inputs", [])],
            label=label,
            label_ids=[int(idx) for idx in payload.get("label_ids", [])],
            attribute=attribute,
            relation=relation,
            reference_label=reference_label,
            reference_label_ids=[int(idx) for idx in payload.get("reference_label_ids", [])],
            distance_m=payload.get("distance_m"),
            margin_m=payload.get("margin_m"),
            logic=None if payload.get("logic") is None else str(payload.get("logic")),
            evidence=[str(item) for item in payload.get("evidence", [])],
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class HydrologicalProgram:
    target: str
    target_label_ids: List[int]
    attributes: List[str] = field(default_factory=list)
    relations: List[RelationClause] = field(default_factory=list)
    negatives: List[str] = field(default_factory=list)
    negative_label_ids: List[int] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "program_schema_mode": "field",
            "program_version": self.metadata.get("program_version", "v1_field"),
            "target": self.target,
            "target_label_ids": list(self.target_label_ids),
            "attributes": list(self.attributes),
            "relations": [relation.to_dict() for relation in self.relations],
            "negatives": list(self.negatives),
            "negative_label_ids": list(self.negative_label_ids),
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
            "source_text": self.source_text,
            "canonical_text": self.to_canonical_text(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HydrologicalProgram":
        return cls(
            target=str(payload.get("target", "others")),
            target_label_ids=[int(idx) for idx in payload.get("target_label_ids", [])],
            attributes=[str(item) for item in payload.get("attributes", [])],
            relations=[RelationClause.from_dict(item) for item in payload.get("relations", [])],
            negatives=[str(item) for item in payload.get("negatives", [])],
            negative_label_ids=[int(idx) for idx in payload.get("negative_label_ids", [])],
            evidence=[str(item) for item in payload.get("evidence", [])],
            metadata=dict(payload.get("metadata", {})),
            source_text=str(payload.get("source_text", "")),
        )

    def to_canonical_text(self) -> str:
        if bool(self.metadata.get("no_target_candidate", False)):
            return "no target"
        parts = [f"segment {self.target}"]
        if self.attributes:
            parts.append("with attributes " + ", ".join(self.attributes))
        for relation in self.relations:
            if relation.type in {"near", "adjacent", "along"} and relation.distance_m is not None:
                parts.append(f"{relation.type} {relation.reference} within {relation.distance_m:.1f}m")
            elif relation.type in {"above", "below"} and relation.margin_m is not None:
                parts.append(f"{relation.type} {relation.reference} by {relation.margin_m:.1f}m")
            else:
                parts.append(f"{relation.type} {relation.reference}")
        if self.negatives:
            parts.append("not " + ", ".join(self.negatives))
        return " ; ".join(parts)

    def with_metadata(self, **kwargs: Any) -> "HydrologicalProgram":
        merged = dict(self.metadata)
        merged.update(kwargs)
        return HydrologicalProgram(
            target=self.target,
            target_label_ids=list(self.target_label_ids),
            attributes=list(self.attributes),
            relations=[RelationClause.from_dict(item.to_dict()) for item in self.relations],
            negatives=list(self.negatives),
            negative_label_ids=list(self.negative_label_ids),
            evidence=list(self.evidence),
            metadata=merged,
            source_text=self.source_text,
        )


@dataclass
class OperatorizedSpatialProgram:
    program_version: str
    target: str
    target_label_ids: List[int]
    steps: List[ProgramStep]
    output_step_id: str
    attributes: List[str] = field(default_factory=list)
    relations: List[RelationClause] = field(default_factory=list)
    negatives: List[str] = field(default_factory=list)
    negative_label_ids: List[int] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "program_schema_mode": "operatorized",
            "program_version": self.program_version,
            "target": self.target,
            "target_label_ids": list(self.target_label_ids),
            "attributes": list(self.attributes),
            "relations": [relation.to_dict() for relation in self.relations],
            "negatives": list(self.negatives),
            "negative_label_ids": list(self.negative_label_ids),
            "steps": [step.to_dict() for step in self.steps],
            "output_step_id": self.output_step_id,
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
            "source_text": self.source_text,
            "canonical_text": self.to_canonical_text(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OperatorizedSpatialProgram":
        return cls(
            program_version=str(payload.get("program_version", "v3_operatorized")),
            target=str(payload.get("target", "others")),
            target_label_ids=[int(idx) for idx in payload.get("target_label_ids", [])],
            attributes=[str(item) for item in payload.get("attributes", [])],
            relations=[RelationClause.from_dict(item) for item in payload.get("relations", [])],
            negatives=[str(item) for item in payload.get("negatives", [])],
            negative_label_ids=[int(idx) for idx in payload.get("negative_label_ids", [])],
            steps=[ProgramStep.from_dict(item) for item in payload.get("steps", [])],
            output_step_id=str(payload.get("output_step_id", payload.get("output", ""))),
            evidence=[str(item) for item in payload.get("evidence", [])],
            metadata=dict(payload.get("metadata", {})),
            source_text=str(payload.get("source_text", "")),
        )

    def to_canonical_text(self) -> str:
        return self.to_field_program().to_canonical_text()

    def with_metadata(self, **kwargs: Any) -> "OperatorizedSpatialProgram":
        merged = dict(self.metadata)
        merged.update(kwargs)
        return OperatorizedSpatialProgram(
            program_version=self.program_version,
            target=self.target,
            target_label_ids=list(self.target_label_ids),
            attributes=list(self.attributes),
            relations=[RelationClause.from_dict(item.to_dict()) for item in self.relations],
            negatives=list(self.negatives),
            negative_label_ids=list(self.negative_label_ids),
            steps=[ProgramStep.from_dict(item.to_dict()) for item in self.steps],
            output_step_id=self.output_step_id,
            evidence=list(self.evidence),
            metadata=merged,
            source_text=self.source_text,
        )

    def to_field_program(self) -> HydrologicalProgram:
        metadata = dict(self.metadata)
        metadata.setdefault("program_version", self.program_version)
        metadata["program_schema_mode"] = "operatorized"
        return HydrologicalProgram(
            target=self.target,
            target_label_ids=list(self.target_label_ids),
            attributes=list(self.attributes),
            relations=[RelationClause.from_dict(item.to_dict()) for item in self.relations],
            negatives=list(self.negatives),
            negative_label_ids=list(self.negative_label_ids),
            evidence=list(self.evidence),
            metadata=metadata,
            source_text=self.source_text,
        )

    def step_map(self) -> Dict[str, ProgramStep]:
        return {step.id: step for step in self.steps}


ProgramLike = Union[HydrologicalProgram, OperatorizedSpatialProgram]


@dataclass
class ProgramCandidate:
    candidate_id: str
    program: ProgramLike
    proposal_score: float = 0.0
    proposal_source: str = "unknown"
    noise_type: str = "unknown"
    compiler_confidence: float = 0.0
    rationale: str = ""
    is_repaired: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "program": self.program.to_dict(),
            "proposal_score": float(self.proposal_score),
            "proposal_source": self.proposal_source,
            "noise_type": self.noise_type,
            "compiler_confidence": float(self.compiler_confidence),
            "rationale": self.rationale,
            "is_repaired": bool(self.is_repaired),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProgramCandidate":
        program_payload = payload.get("program", {})
        if not isinstance(program_payload, dict):
            raise TypeError("ProgramCandidate.program must be a JSON object.")
        return cls(
            candidate_id=str(payload.get("candidate_id", "")),
            program=program_from_dict(program_payload),
            proposal_score=float(payload.get("proposal_score", 0.0)),
            proposal_source=str(payload.get("proposal_source", "unknown")),
            noise_type=str(payload.get("noise_type", "unknown")),
            compiler_confidence=float(payload.get("compiler_confidence", 0.0)),
            rationale=str(payload.get("rationale", "")),
            is_repaired=bool(payload.get("is_repaired", False)),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class VerificationTrace:
    candidate_id: str
    validity_score: float = 0.0
    evidence_score: float = 0.0
    no_target_score: float = 0.0
    final_score: float = 0.0
    abstain: bool = False
    failure_type: str = ""
    step_scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "validity_score": float(self.validity_score),
            "evidence_score": float(self.evidence_score),
            "no_target_score": float(self.no_target_score),
            "final_score": float(self.final_score),
            "abstain": bool(self.abstain),
            "failure_type": self.failure_type,
            "step_scores": {str(key): float(value) for key, value in self.step_scores.items()},
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "VerificationTrace":
        return cls(
            candidate_id=str(payload.get("candidate_id", "")),
            validity_score=float(payload.get("validity_score", 0.0)),
            evidence_score=float(payload.get("evidence_score", 0.0)),
            no_target_score=float(payload.get("no_target_score", 0.0)),
            final_score=float(payload.get("final_score", 0.0)),
            abstain=bool(payload.get("abstain", False)),
            failure_type=str(payload.get("failure_type", "")),
            step_scores={str(key): float(value) for key, value in dict(payload.get("step_scores", {})).items()},
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class ProgramBundle:
    source_text: str
    candidates: List[ProgramCandidate]
    selected_candidate_id: str = ""
    verification: List[VerificationTrace] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def selected_program(self) -> ProgramLike:
        if self.selected_candidate_id:
            for candidate in self.candidates:
                if candidate.candidate_id == self.selected_candidate_id:
                    return candidate.program
        if not self.candidates:
            raise ValueError("ProgramBundle has no candidates.")
        return self.candidates[0].program

    def selected_candidate(self) -> ProgramCandidate:
        if self.selected_candidate_id:
            for candidate in self.candidates:
                if candidate.candidate_id == self.selected_candidate_id:
                    return candidate
        if not self.candidates:
            raise ValueError("ProgramBundle has no candidates.")
        return self.candidates[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_type": "program_bundle",
            "source_text": self.source_text,
            "selected_candidate_id": self.selected_candidate_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "verification": [trace.to_dict() for trace in self.verification],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProgramBundle":
        return cls(
            source_text=str(payload.get("source_text", "")),
            candidates=[ProgramCandidate.from_dict(item) for item in payload.get("candidates", []) if isinstance(item, dict)],
            selected_candidate_id=str(payload.get("selected_candidate_id", "")),
            verification=[
                VerificationTrace.from_dict(item)
                for item in payload.get("verification", [])
                if isinstance(item, dict)
            ],
            metadata=dict(payload.get("metadata", {})),
        )


def ensure_negative_priors(target_name: str, existing: Sequence[str]) -> List[str]:
    negatives = [canonicalize_label_name(name) or name for name in existing]
    target_key = canonicalize_label_name(target_name) or target_name
    defaults = DEFAULT_NEGATIVE_PRIORS.get(target_key, [])
    for name in defaults:
        if name not in negatives and name != target_key:
            negatives.append(name)
    return negatives


def merge_evidence(attributes: Sequence[str], relations: Sequence[RelationClause]) -> List[str]:
    items: List[str] = []
    for attribute in attributes:
        for token in DEFAULT_EVIDENCE.get(attribute, []):
            if token not in items:
                items.append(token)
    for relation in relations:
        for token in relation.evidence:
            if token not in items:
                items.append(token)
    return items


def first_available_target(label_ids: Sequence[int]) -> str:
    for label_id in label_ids:
        if label_id in TRAIN_ID_TO_NAME:
            return TRAIN_ID_TO_NAME[label_id]
    return "others"


def unique_list(values: Iterable[str]) -> List[str]:
    seen = set()
    items: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def program_from_dict(payload: Dict[str, Any]) -> ProgramLike:
    if str(payload.get("program_schema_mode", "")).lower() == "operatorized" or "steps" in payload:
        return OperatorizedSpatialProgram.from_dict(payload)
    return HydrologicalProgram.from_dict(payload)


def bundle_from_dict(payload: Dict[str, Any]) -> ProgramBundle:
    if str(payload.get("bundle_type", "")).lower() == "program_bundle" or "candidates" in payload:
        return ProgramBundle.from_dict(payload)
    program = program_from_dict(payload)
    return ProgramBundle(
        source_text=getattr(program, "source_text", ""),
        candidates=[
            ProgramCandidate(
                candidate_id="c0",
                program=program,
                proposal_score=1.0,
                proposal_source=str(dict(getattr(program, "metadata", {})).get("compiler", "single_program")),
            )
        ],
        selected_candidate_id="c0",
        metadata={"wrapped_single_program": True},
    )


def operatorized_program_from_field_program(
    program: HydrologicalProgram,
    program_version: str = "v3_operatorized",
) -> OperatorizedSpatialProgram:
    steps: List[ProgramStep] = []
    step_index = 1

    select_id = f"s{step_index}"
    steps.append(
        ProgramStep(
            id=select_id,
            op="select",
            label=program.target,
            label_ids=list(program.target_label_ids),
            evidence=["class_logits"],
        )
    )
    current_id = select_id

    for attr_name in program.attributes:
        step_index += 1
        current_id = f"s{step_index}"
        steps.append(
            ProgramStep(
                id=current_id,
                op="filter",
                input=steps[-1].id,
                attribute=attr_name,
                evidence=list(DEFAULT_EVIDENCE.get(attr_name, [])),
            )
        )

    for relation in program.relations:
        step_index += 1
        current_id = f"s{step_index}"
        steps.append(
            ProgramStep(
                id=current_id,
                op="relate",
                input=steps[-1].id,
                relation=relation.type,
                reference_label=relation.reference,
                reference_label_ids=list(relation.reference_label_ids),
                distance_m=relation.distance_m,
                margin_m=relation.margin_m,
                evidence=list(relation.evidence),
            )
        )

    for negative_name, negative_id in zip(program.negatives, program.negative_label_ids):
        step_index += 1
        current_id = f"s{step_index}"
        steps.append(
            ProgramStep(
                id=current_id,
                op="exclude",
                input=steps[-1].id,
                label=negative_name,
                label_ids=[int(negative_id)],
                evidence=["class_logits"],
            )
        )

    source_schema_mode = str(program.metadata.get("program_schema_mode", "field"))
    metadata = dict(program.metadata)
    metadata["program_schema_mode"] = "operatorized"
    metadata["source_program_schema_mode"] = source_schema_mode
    return OperatorizedSpatialProgram(
        program_version=program_version,
        target=program.target,
        target_label_ids=list(program.target_label_ids),
        attributes=list(program.attributes),
        relations=[RelationClause.from_dict(item.to_dict()) for item in program.relations],
        negatives=list(program.negatives),
        negative_label_ids=list(program.negative_label_ids),
        steps=steps,
        output_step_id=current_id,
        evidence=list(program.evidence),
        metadata=metadata,
        source_text=program.source_text,
    )
