from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytorch_lightning as pl
import torch
import yaml
from easydict import EasyDict
from pytorch_lightning import loggers as pl_loggers
from pytorch_lightning.callbacks import EarlyStopping, LearningRateMonitor, ModelCheckpoint


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = PROJECT_ROOT / "hydro_remote_agent" / "vendor" / "gufnet"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from dataloader.dataset import get_collate_class, get_model_class  # noqa: E402
from dataloader.pc_dataset import get_pc_model_class  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_manifests(config: EasyDict) -> dict[str, Any]:
    dataset = config.dataset_params
    manifests = {name: Path(path).resolve() for name, path in dataset.split_manifests.items()}
    expected = dict(dataset.expected_split_counts)
    sets: dict[str, set[str]] = {}
    split_reports: dict[str, Any] = {}
    data_root = Path(dataset.train_data_loader.data_path).resolve()
    for name in ("train", "val", "test"):
        path = manifests[name]
        rows = _read_jsonl(path)
        ids = [str(row["sample_id"]) for row in rows]
        if len(rows) != int(expected[name]) or len(set(ids)) != len(rows):
            raise ValueError(
                f"{name}: expected {expected[name]} unique rows, got {len(rows)} rows/{len(set(ids))} ids"
            )
        missing = []
        for row in rows:
            point = data_root / str(row["folder_id"]) / "velodyne" / f"{row['patch_id']}.pth"
            image = data_root / str(row["folder_id"]) / "image" / f"{row['patch_id']}.png"
            if not point.is_file() or not image.is_file():
                missing.append(str(row["sample_id"]))
        if missing:
            raise FileNotFoundError(f"{name}: {len(missing)} samples lack preprocessed assets: {missing[:5]}")
        sets[name] = set(ids)
        split_reports[name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "row_count": len(rows),
            "unique_sample_count": len(set(ids)),
            "missing_asset_count": len(missing),
        }
    overlaps = {
        "train_val": len(sets["train"] & sets["val"]),
        "train_test": len(sets["train"] & sets["test"]),
        "val_test": len(sets["val"] & sets["test"]),
    }
    if any(overlaps.values()):
        raise ValueError(f"Frozen split overlap detected: {overlaps}")
    return {
        "schema_version": "hydro_agent_bench.gufnet_data_integrity.v1",
        "status": "qualified_zero_overlap",
        "splits": split_reports,
        "overlaps": overlaps,
        "union_sample_count": len(set.union(*sets.values())),
        "preprocessed_data_root": str(data_root),
    }


def _build_loaders(config: EasyDict):
    pc_dataset = get_pc_model_class(config.dataset_params.pc_dataset_type)
    wrapped_dataset = get_model_class(config.dataset_params.dataset_type)
    collate = get_collate_class(config.dataset_params.collate_type)
    train_cfg = config.dataset_params.train_data_loader
    val_cfg = config.dataset_params.val_data_loader
    train_points = pc_dataset(config, data_path=train_cfg.data_path, imageset="train")
    val_points = pc_dataset(config, data_path=val_cfg.data_path, imageset="val")
    train_dataset = wrapped_dataset(train_points, config, train_cfg)
    val_dataset = wrapped_dataset(val_points, config, val_cfg, num_vote=1)
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=int(train_cfg.batch_size),
        collate_fn=collate,
        shuffle=bool(train_cfg.shuffle),
        num_workers=int(train_cfg.num_workers),
        pin_memory=True,
        drop_last=True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=int(val_cfg.batch_size),
        collate_fn=collate,
        shuffle=False,
        num_workers=int(val_cfg.num_workers),
        pin_memory=True,
    )
    return train_loader, val_loader


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a zero-overlap GUFNet expert on wcs10m_primary.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--fast-dev-run", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = EasyDict(yaml.safe_load(config_path.read_text(encoding="utf-8")))
    config.update(
        {
            "debug": False,
            "test": False,
            "submit_to_server": False,
            "baseline_only": bool(config.model_params.get("baseline_only", False)),
            "pretrain2d": False,
            "fine_tune": False,
            "mask_dir": None,
            "iou_log_path": None,
            "gpu": [0],
            "monitor": "val/mIoU",
            "seed": args.seed,
        }
    )
    integrity = audit_manifests(config)
    (output_dir / "data_integrity.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(config_path, output_dir / "frozen_config.yaml")

    pl.seed_everything(args.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(args.seed)
    train_loader, val_loader = _build_loaders(config)
    model_module = importlib.import_module(f"network.{config.model_params.model_architecture}")
    model = model_module.get_model(config)

    checkpoints = output_dir / "checkpoints"
    checkpoint_callback = ModelCheckpoint(
        dirpath=str(checkpoints),
        filename="gufnet-primary-{epoch:03d}",
        monitor="val/mIoU",
        mode="max",
        save_last=True,
        save_top_k=1,
    )
    callbacks = [checkpoint_callback, LearningRateMonitor(logging_interval="step")]
    if not args.fast_dev_run:
        callbacks.append(EarlyStopping(monitor="val/mIoU", patience=30, mode="max", verbose=True))
    logger = pl_loggers.TensorBoardLogger(str(output_dir), name="tensorboard", default_hp_metric=False)
    trainer = pl.Trainer(
        gpus=1,
        max_epochs=1 if args.fast_dev_run else int(config.train_params.max_num_epochs),
        resume_from_checkpoint=None if args.resume is None else str(args.resume.resolve()),
        callbacks=callbacks,
        logger=logger,
        gradient_clip_val=1.0,
        deterministic=True,
        fast_dev_run=args.fast_dev_run,
        num_sanity_val_steps=1,
    )
    trainer.fit(model, train_loader, val_loader)
    summary = {
        "status": "smoke_complete" if args.fast_dev_run else "training_complete",
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "seed": args.seed,
        "best_model_path": checkpoint_callback.best_model_path,
        "best_model_score": None
        if checkpoint_callback.best_model_score is None
        else float(checkpoint_callback.best_model_score),
        "last_model_path": str(checkpoints / "last.ckpt"),
        "data_integrity": integrity,
        "torch_version": torch.__version__,
        "lightning_version": pl.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
