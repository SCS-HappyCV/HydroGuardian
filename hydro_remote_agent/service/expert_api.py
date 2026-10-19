from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Dict

from hydro_remote_agent.runtime import ExpertRuntime
from hydro_remote_agent.runtime.contracts import ExpertNotReadyError
from hydro_remote_agent.schemas.tool_spec import ToolArgumentError


def create_expert_app(runtime: ExpertRuntime):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.concurrency import run_in_threadpool
    except ImportError as exc:
        raise RuntimeError("Expert Worker API requires fastapi") from exc

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            runtime.shutdown()

    app = FastAPI(title="VagueHydro Expert Worker", version="1.0", lifespan=lifespan)

    @app.get("/healthz")
    def health() -> Dict[str, Any]:
        experts = [asdict(item) for item in runtime.health_check()]
        unavailable = [
            item["tool"] for item in experts if item["status"] in {"disabled", "unavailable"}
        ]
        return {
            "status": "degraded" if unavailable else "ok",
            "experts": experts,
            "unavailable": unavailable,
        }

    @app.get("/v1/tools")
    def tools() -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": tool.name,
                    "version": tool.version,
                    "backend": runtime.get_adapter(tool.name).backend,
                }
                for tool in runtime.registry.tools
            ]
        }

    @app.post("/v1/tools/{tool_name}/prepare")
    async def prepare(tool_name: str) -> Dict[str, Any]:
        try:
            health_result = await run_in_threadpool(runtime.prepare, tool_name)
            return asdict(health_result[0])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}") from exc

    @app.post("/v1/tools/{tool_name}/invoke")
    async def invoke(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        arguments = payload.get("arguments")
        invocation_id = payload.get("invocation_id")
        if not isinstance(arguments, dict):
            raise HTTPException(status_code=422, detail="arguments must be an object")
        if invocation_id is not None and not isinstance(invocation_id, str):
            raise HTTPException(status_code=422, detail="invocation_id must be a string")
        try:
            result = await run_in_threadpool(
                runtime.invoke,
                tool_name,
                arguments,
                invocation_id,
            )
            return result.to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ToolArgumentError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ExpertNotReadyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc

    return app
