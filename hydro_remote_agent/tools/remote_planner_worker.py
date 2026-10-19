from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.planner import Qwen3VLPlannerBackend


def _request(base_url: str, path: str, secret: str, worker_id: str, payload: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8") if payload is not None else b"{}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Worker-Secret": secret, "X-Worker-Id": worker_id},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _rewrite_download_url(download_url: str, asset_base_url: Optional[str]) -> str:
    if not asset_base_url:
        return download_url
    original = urlsplit(download_url)
    tunnel = urlsplit(asset_base_url)
    return urlunsplit((tunnel.scheme or original.scheme, tunnel.netloc, original.path, original.query, original.fragment))


def _download_url(
    base_url: str,
    artifact_uri: str,
    secret: str,
    worker_id: str,
    asset_base_url: Optional[str] = None,
) -> str:
    artifact_id = artifact_uri.removeprefix("artifact://")
    if asset_base_url:
        access = _request(base_url, f"/internal/planner/assets/{artifact_id}/access", secret, worker_id)
        return f"{asset_base_url.rstrip('/')}{access['download_path']}"
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/v1/assets/{artifact_id}/download", timeout=60) as response:
        download_url = str(json.loads(response.read().decode("utf-8"))["download_url"])
    return download_url


def _preview_url(
    base_url: str,
    artifact_uri: str,
    asset_base_url: Optional[str] = None,
    max_dimension: int = 2048,
) -> str:
    artifact_id = artifact_uri.removeprefix("artifact://")
    origin = (asset_base_url or base_url).rstrip("/")
    dimension = max(512, min(int(max_dimension), 4096))
    return f"{origin}/v1/assets/{artifact_id}/preview?max_dimension={dimension}"


def _replace(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    return value


def _planner_submission(
    base_url: str,
    submission: Mapping[str, Any],
    secret: str,
    worker_id: str,
    asset_base_url: Optional[str] = None,
    preview_dimension: int = 2048,
) -> tuple[dict[str, Any], dict[str, str]]:
    resolved = dict(submission)
    assets = dict(submission.get("assets", {}))
    reverse: dict[str, str] = {}
    for role in ("image_path", "before_image_path", "after_image_path"):
        value = assets.get(role)
        if isinstance(value, str) and value.startswith("artifact://"):
            url = _preview_url(base_url, value, asset_base_url, preview_dimension)
            assets[role] = url
            reverse[url] = value
    resolved["assets"] = assets
    return resolved, reverse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GPU-backed remote Planner Worker.")
    parser.add_argument("--agent-base-url", default=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:28080"))
    parser.add_argument("--asset-base-url", default=os.getenv("ASSET_BASE_URL"))
    parser.add_argument("--worker-secret", default=os.getenv("WORKER_SECRET", ""))
    parser.add_argument("--worker-id", default=os.getenv("PLANNER_WORKER_ID", "qwen3-vl-planner"))
    parser.add_argument("--registry", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--adapter-path")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--max-new-tokens", type=int, default=int(os.getenv("PLANNER_MAX_NEW_TOKENS", "640")))
    parser.add_argument("--chat-max-new-tokens", type=int, default=int(os.getenv("PLANNER_CHAT_MAX_NEW_TOKENS", "256")))
    parser.add_argument("--max-image-pixels", type=int, default=int(os.getenv("PLANNER_MAX_IMAGE_PIXELS", "196608")))
    parser.add_argument("--preview-dimension", type=int, default=int(os.getenv("PLANNER_PREVIEW_DIMENSION", "2048")))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.worker_secret:
        raise ValueError("WORKER_SECRET is required")
    registry = load_tool_registry(args.registry)
    backend = Qwen3VLPlannerBackend(
        config_path=os.path.join(os.path.dirname(args.registry), "backbone_qwen3_vl_8b.json"),
        registry=registry, model_path=args.model_path, adapter_path=args.adapter_path,
        max_new_tokens=args.max_new_tokens, max_image_pixels=args.max_image_pixels,
    )
    backend.prepare()
    while True:
        job: Optional[dict[str, Any]] = None
        chat_request: Optional[dict[str, Any]] = None
        try:
            claimed = _request(args.agent_base_url, "/internal/planner/claim", args.worker_secret, args.worker_id)
            job = claimed.get("job")
            if isinstance(job, dict):
                submission, reverse = _planner_submission(
                    args.agent_base_url, job["submission"], args.worker_secret, args.worker_id,
                    args.asset_base_url, args.preview_dimension,
                )
                plan = _replace(backend.plan(submission), reverse)
                _request(args.agent_base_url, f"/internal/planner/{job['job_id']}/complete", args.worker_secret, args.worker_id, {"plan": plan})
                print(f"REMOTE_PLANNER_SUCCEEDED job_id={job['job_id']}", flush=True)
                continue
            claimed_chat = _request(args.agent_base_url, "/internal/planner/chat/claim", args.worker_secret, args.worker_id)
            chat_request = claimed_chat.get("request")
            if not isinstance(chat_request, dict):
                time.sleep(max(args.poll_seconds, 0.1))
                continue
            request_id = str(chat_request["request"]["request_id"])
            response = backend.chat(chat_request, max_new_tokens=args.chat_max_new_tokens)
            _request(
                args.agent_base_url, f"/internal/planner/chat/{request_id}/complete",
                args.worker_secret, args.worker_id, response,
            )
            print(f"REMOTE_PLANNER_CHAT_SUCCEEDED request_id={request_id}", flush=True)
        except Exception as exc:
            job_id = job.get("job_id") if isinstance(job, dict) else None
            request_id = chat_request.get("request", {}).get("request_id") if isinstance(chat_request, dict) else None
            print(f"REMOTE_PLANNER_ERROR job_id={job_id} request_id={request_id} error={type(exc).__name__}: {exc}", flush=True)
            if job_id:
                try:
                    _request(args.agent_base_url, f"/internal/planner/{job_id}/fail", args.worker_secret, args.worker_id, {"error": {"code": "planning_failed", "message": f"{type(exc).__name__}: {exc}"}})
                except Exception:
                    pass
            elif request_id:
                try:
                    _request(args.agent_base_url, f"/internal/planner/chat/{request_id}/fail", args.worker_secret, args.worker_id, {"error": {"code": "agent_chat_failed", "message": f"{type(exc).__name__}: {exc}"}})
                except Exception:
                    pass
            time.sleep(max(args.poll_seconds, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
