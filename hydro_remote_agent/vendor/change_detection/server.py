from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from final_model import final_BaseNet
from nacos import NacosRegistrar
from service_config import load_settings
from Transforms import Compose, NormalizeJpgSafe, Scale, ToTensor

app = FastAPI(title="RFANet Inference API")

settings = load_settings()
nacos = NacosRegistrar(settings)
nacos_task: Optional[asyncio.Task] = None

OUTPUT_DIR = str(settings.output_dir)
DEFAULT_WEIGHTS = str(settings.weights_path)
DEFAULT_DEVICE = settings.device

_model: Optional[torch.nn.Module] = None
_device: str = DEFAULT_DEVICE


def _load_state_dict(model: torch.nn.Module, weights_path: str) -> None:
    if not os.path.isfile(weights_path):
        raise FileNotFoundError(f"weights not found: {weights_path}")

    state_dict = torch.load(weights_path, map_location=_device)
    if isinstance(state_dict, dict) and "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]

    filtered_state_dict = {
        k: v
        for k, v in state_dict.items()
        if not (".total_ops" in k or ".total_params" in k or k.endswith("total_ops") or k.endswith("total_params"))
    }

    model.load_state_dict(filtered_state_dict, strict=False)


def _get_transform():
    mean = [0.406, 0.456, 0.485, 0.406, 0.456, 0.485]
    std = [0.225, 0.224, 0.229, 0.225, 0.224, 0.229]
    return Compose([
        #若输入为jpg则use_otsu=True,为PNG则use_otsu=False
        NormalizeJpgSafe(mean=mean, std=std, use_otsu=False),
        Scale(256, 256),
        ToTensor(),
    ])


def _read_image(file: UploadFile) -> np.ndarray:
    data = file.file.read()
    if not data:
        raise ValueError("empty upload")
    image_array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("failed to decode image")
    return image


def _ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.on_event("startup")
async def _startup() -> None:
    global _model, _device, nacos_task
    _device = settings.device
    weights_path = str(settings.weights_path)

    model = final_BaseNet(3, 1)
    _load_state_dict(model, weights_path)
    model.eval()
    _model = model.to(_device)

    _ensure_output_dir()
    if settings.nacos_enabled:
        nacos_task = asyncio.create_task(nacos.heartbeat_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global nacos_task
    if nacos_task:
        nacos_task.cancel()
        nacos_task = None
    try:
        await nacos.deregister()
    except Exception as exc:
        print(f"[change-detection] nacos deregister failed: {exc}")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "change_detection",
        "device": _device,
        "weights": str(settings.weights_path),
        "nacos_enabled": settings.nacos_enabled,
        "nacos_service_name": settings.nacos_service_name,
        "nacos_registered": nacos.registered,
        "nacos_error": nacos.last_error,
    }


@app.post("/predict")
def predict(
    pre_image: UploadFile = File(...),
    post_image: UploadFile = File(...),
    threshold: float = 0.5,
) -> dict:
    if _model is None:
        raise HTTPException(status_code=500, detail="model not loaded")

    try:
        pre_img = _read_image(pre_image)
        post_img = _read_image(post_image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if pre_img.shape[:2] != post_img.shape[:2]:
        raise HTTPException(status_code=400, detail="pre_image and post_image must have the same size")

    img = np.concatenate((pre_img, post_img), axis=2)
    label = np.zeros(pre_img.shape[:2], dtype=np.uint8)

    transform = _get_transform()
    img_tensor, _ = transform(img, label)
    img_tensor = img_tensor.unsqueeze(0).float().to(_device)

    with torch.no_grad():
        outputs = _model(img_tensor[:, 0:3], img_tensor[:, 3:6])

    output = outputs[0]
    pred = torch.where(output > threshold, torch.ones_like(output), torch.zeros_like(output)).long()
    mask = pred[0, 0].cpu().numpy() * 255
    mask = mask.astype(np.uint8)

    _ensure_output_dir()
    filename = f"mask_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
    out_path = os.path.abspath(os.path.join(OUTPUT_DIR, filename))
    cv2.imwrite(out_path, mask)
    print(output.min().item(), output.max().item(), output.mean().item())

    return FileResponse(out_path, media_type="image/png", filename=filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
