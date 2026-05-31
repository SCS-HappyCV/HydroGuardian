# agent-service

`agent-service` 是 HydroGuardian 的智能体编排服务。它不直接加载 3D 模型或 2D 变化检测模型，而是把巡查任务编排成可执行闭环：

```text
自然语言任务
-> 任务解析
-> ProgramBundle 构建
-> SceneTensorSample 准备
-> hydro-program3d /execute
-> hydro-program3d /compile_evidence
-> 可选 change-detection /predict
-> RiskCard
-> RecommendationCard
-> WorkOrderCard
-> case-service 持久化
```

当前对外主接口是 gRPC，默认监听 `9091`，并通过 Nacos 注册为 `agent-service`。HTTP 请求通常由 `api-gateway` 转成 gRPC 调用。

## 目录结构

```text
agent-service/
|- Dockerfile
|- requirements.txt
|- proto/                  # gRPC proto 源文件
|- scripts/
|  `- build_proto.sh       # 生成 Python pb2 文件
`- src/
   |- main.py              # 服务启动、Nacos 生命周期
   |- config.py            # 环境变量和默认配置
   |- state.py             # AgentState、trace/error、失败 EvidencePack
   |- discovery.py         # Nacos 注册、心跳、服务发现
   |- agent_graph.py       # LangGraph 编排图
   |- grpc_service.py      # AgentRpcService 实现
   |- grpc_client.py       # 通用 gRPC channel helper
   |- generated/           # 生成的 *_pb2.py / *_pb2_grpc.py
   |- clients/             # 外部服务客户端
   `- nodes/               # LangGraph 节点
```

## 运行

### Docker Compose

从 `backend/` 目录启动：

```bash
docker compose up agent-service
```

完整闭环依赖：

- `nacos`
- `case-service`
- `file-service`
- `hydro-program3d`
- `change-detection`，仅时间变化任务需要

### 本地运行

```bash
cd backend/services/agent-service
python -m pip install -r requirements.txt
sh ./scripts/build_proto.sh
python ./src/main.py
```

Windows 下建议在 Git Bash、WSL 或容器内执行 `build_proto.sh`。

## Proto 生成

pb2 生成产物统一放在：

```text
src/generated/
```

生成脚本会清理旧的 `src/*_pb2.py` 和 `src/*_pb2_grpc.py`，然后重新生成到 `src/generated/`。`*_pb2_grpc.py` 会被脚本修正为包内相对导入。

## 核心环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AGENT_GRPC_PORT` | `9091` | agent-service gRPC 端口 |
| `NACOS_ENABLED` | `true` | 是否注册/发现 Nacos |
| `NACOS_SERVER_ADDR` | `localhost:8848` | Nacos 地址，compose 中为 `nacos:8848` |
| `NACOS_SERVICE_NAME` | `agent-service` | 本服务注册名 |
| `CASE_SERVICE_NAME` | `case-service` | case-service Nacos 服务名 |
| `FILE_SERVICE_NAME` | `file-service` | file-service Nacos 服务名 |
| `CASE_GRPC_ADDR` | 空 | case-service 直连地址，配置后跳过 Nacos |
| `FILE_GRPC_ADDR` | 空 | file-service 直连地址，配置后跳过 Nacos |
| `HYDRO_PROGRAM3D_URL` | 空 | hydro-program3d 直连 URL，compose 中配置为 `http://hydro-program3d:8093` |
| `HYDRO_PROGRAM3D_SERVICE_NAME` | `hydro-program3d` | hydro-program3d Nacos 服务名 |
| `HYDRO_PROGRAM3D_CHECKPOINT_NAME` | `hydro_program3d_demo.pth` | `/execute` 使用的 checkpoint |
| `HYDRO_PROGRAM3D_DEVICE` | `cuda` | `/execute` 使用设备 |
| `HYDRO_MODEL_OVERRIDES_JSON` | 空 | 覆盖 `/execute.model_overrides` 的 JSON |
| `CHANGE_DETECTION_URL` | 空 | change-detection 直连 URL，compose 中配置为 `http://change-detection:8011` |
| `CHANGE_DETECTION_SERVICE_NAME` | `change-detection` | change-detection Nacos 服务名 |
| `AGENT_SCENE_SAMPLE_DIR` | `/app/data/scene_samples` | 预处理后场景样本 JSON 目录 |
| `AGENT_ALLOW_DEMO_SAMPLE` | `true` | 缺少场景样本时是否生成 demo sample |

## 场景样本

`hydro-program3d /execute` 不读取原始文件路径，调用方必须提供预处理后的 JSON 张量。`agent-service` 会优先从 `AGENT_SCENE_SAMPLE_DIR` 读取：

```text
{scene_id}.json
{sample_id}.json
```

样本至少应包含：

```json
{
  "sample_id": "demo-001",
  "text": "find thin linear ditch near waterline and exclude road",
  "images": "[3,H,W] or [B,3,H,W]",
  "points_xyz": "[N,3] or [B,N,3]",
  "points_rgb": "[N,3] or [B,N,3]",
  "point_geometry_features": "[N,G] or [B,N,G]",
  "valid_point_mask": "[N] or [B,N]"
}
```

如果是变化检测任务，可额外提供：

```json
{
  "pre_image_path": "/app/data/pre.png",
  "post_image_path": "/app/data/post.png"
}
```

## gRPC 接口

服务定义在 `proto/agent.proto`：

- `ExecuteTask`
- `QueryFile`

示例：

```bash
grpcurl -plaintext \
  -d '{"task_text":"find thin linear ditch near waterline and exclude road","scene_id":"demo-001"}' \
  127.0.0.1:9091 \
  hydro.agent.v1.AgentRpcService/ExecuteTask
```

## 失败处理

- 任务不可解析：进入 `REVIEW_REQUIRED` 或 `ABSTAINED`
- 缺少场景样本：如果 `AGENT_ALLOW_DEMO_SAMPLE=false`，直接返回结构化失败
- 3D 服务不可达或 `/execute` 失败：生成 `execution_failed` 形式的 `EvidencePack`
- 证据不足、no-target 或拒答信号高：风险等级进入 `REVIEW_REQUIRED`
- case-service 持久化失败：不阻断风险和建议返回，但会记录到 `errors`

## 当前限制

- 第一版任务解析是规则实现，后续可替换为 LLM/工具调用式解析。
- 2D 变化检测只有在任务含时间变化意图且样本中有 `pre_image_path/post_image_path` 时才触发。
- `AGENT_ALLOW_DEMO_SAMPLE=true` 适合联调，不适合真实推理验收。
