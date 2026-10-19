# Standalone Docker deployment

This deployment is independent from HydroGuardian and uses two separate Compose projects:

- Control-server `agent`: HTTP API, WebSocket Hub, queue executor, and PostgreSQL job state.
- Optional control-server `planner`: Qwen3-VL planner, enabled with the `planner` Compose profile.
- Remote `expert-worker`: six real expert adapters and an active WebSocket client on the GPU server.

The control plane is deployed at `172.16.224.4:18080`, with MinIO at
`172.16.224.4:19000`. Upstream network policy drops direct GPU traffic to these two
ports, so the GPU opens an SSH local-forward tunnel to control-server port `22`.
Workers connect to `ws://127.0.0.1:28080/internal/workers/ws`, while MinIO uses
`127.0.0.1:29000`. The GPU server does not need an inbound
service port. Set the same strong `WORKER_SECRET` on both
sides. Use `POST /v1/assets/presign` to upload files to MinIO and pass `artifact://...`
values in job inputs. The Worker downloads these assets into an isolated temporary
directory and uploads expert outputs back to MinIO.

## Prepare

Copy `.env.example` to `.env` and update all host paths. The expected checkpoint names are:

```text
GUFNET_MODEL_DIR/epoch=242-step=16766.ckpt
CHANGE_MODEL_DIR/best_model.pth
HYDRO_PROGRAM3D_MODEL_DIR/best.pth
```

Install Docker Engine and Docker Compose v2 on the control server. Install NVIDIA Container Toolkit and
configure the Docker NVIDIA runtime on each machine that runs a GPU container.

## Run

Start the control plane on `172.16.224.4` from the project root:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml config
docker compose --env-file deploy/.env -f deploy/docker-compose.yml build agent
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
curl http://127.0.0.1:18080/healthz
```

The default control plane does not require a local GPU or planner checkpoint. When the
planner weights are available, start the optional planner service with:

```bash
docker compose --profile planner up -d planner
```

Start the remote GPU Worker from the copied project directory on the GPU server:

```bash
docker compose -f docker-compose.worker.yml config
docker compose -f docker-compose.worker.yml build
docker compose -f docker-compose.worker.yml up -d
docker compose -f docker-compose.worker.yml logs -f expert-worker
```

Verify registration with `GET http://172.16.224.4:18080/v1/workers`.

Start the tunnel on the GPU before launching Workers:

```bash
tmux new-session -d -s hydro_control_tunnel \
  'bash deploy/run-control-tunnel.sh >> logs/control-tunnel.log 2>&1'
```

The remote CPU geometry and quality worker can then run without claiming a GPU:

```bash
tmux new-session -d -s hydro_expert_cpu_worker \
  'cd hydro_remote_agent && bash deploy/run-expert-cpu-worker.sh >> logs/cpu-worker.log 2>&1'
```

Submit jobs using MinIO artifact IDs, for example:

```json
{
  "request_id": "web-001",
  "query": "segment all water points",
  "language": "en",
  "assets": {
    "point_cloud_path": "artifact://art_01JEXAMPLE"
  }
}
```

The API remains asynchronous: submit with `POST /v1/jobs`, then poll
`GET /v1/jobs/{job_id}`. For live progress use
`GET /v1/jobs/{job_id}/events/stream?last_event_id=0` with an SSE client. The regular
`GET /v1/jobs/{job_id}/events` endpoint remains the recovery API.

For local unit tests, passing a filesystem path as `--db` still selects the SQLite backend.
The Compose deployment uses PostgreSQL through `DATABASE_URL`; Redis and RabbitMQ are
started as independent infrastructure services for the next asynchronous scaling phase.

## End-to-end smoke test

After the Agent is running, use the smoke runtime to verify WebSocket scheduling without
loading GPU checkpoints:

```bash
  python -m hydro_remote_agent.tools.e2e_smoke \
  --runtime hydro_remote_agent/configs/expert_runtime.smoke.yaml \
  --tool point_semantic_segmentation \
  --arguments '{"point_cloud_path":"smoke_points.txt"}'
```

For real model validation, replace `--runtime` with `expert_runtime.yaml`, set a real
`--worker-secret`, and use arguments whose assets are available on the Worker or are
expanded from `artifact://...` by MinIO.
