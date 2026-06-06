# HydroGuardian agent-service

`agent-service` 是 HydroGuardian 的智能体编排服务。它负责把自然语言巡查任务、场景样本、3D 程序执行、变化检测、风险评估、建议生成和 case 持久化串成一条可追踪闭环。

本文档按两种使用方式组织：

- **开发接手版**：给后端同学快速理解目录、主链路、运行方式和排障入口。
- **接口文档版**：给前端、网关、联调同学查询 HTTP/gRPC 请求字段、响应字段和调用顺序。

## 一、开发接手版

### 1. 服务定位

`agent-service` 不直接保存文件，也不直接训练或加载 3D/2D 模型。它的核心职责是编排：

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

默认 gRPC 端口是 `9091`，服务通过 Nacos 注册为 `agent-service`。前端通常不直接调用它，而是走 `api-gateway` 的 HTTP 接口。

### 2. 目录结构

```text
agent-service/
|- Dockerfile
|- requirements.txt
|- proto/                  # agent/case/file gRPC proto 源文件
|- scripts/
|  `- build_proto.sh       # 生成 Python pb2 文件
`- src/
   |- main.py              # 服务启动、gRPC server、Nacos 生命周期
   |- config.py            # 环境变量和默认配置
   |- state.py             # AgentState、trace/error、失败 EvidencePack
   |- discovery.py         # Nacos 注册、心跳、服务发现
   |- agent_graph.py       # LangGraph 主流程
   |- grpc_service.py      # ExecuteTask / PreprocessScene / QueryFile 入口
   |- generated/           # 生成的 *_pb2.py / *_pb2_grpc.py
   |- clients/             # 外部服务客户端
   |- nodes/               # LangGraph 节点
   |- responses/           # gRPC 响应组装
   |- scene_preprocess/    # 图像/点云预处理、质量报告、manifest 注册
   `- scene_samples/       # 场景样本校验与 demo sample
```

### 3. 推荐阅读顺序

1. [src/main.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/main.py>)  
   服务启动入口，负责启动 gRPC server，并处理 Nacos 注册与心跳。

2. [src/grpc_service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/grpc_service.py>)  
   `ExecuteTask / PreprocessScene / QueryFile` 的真实入口。

3. [src/agent_graph.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/agent_graph.py>)  
   主流程编排，当前 MVP 链路是：
   `parse_task -> build_program -> prepare_scene_sample -> execute_3d -> maybe_detect_change -> assess_risk -> generate_recommendation`

4. [src/state.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/state.py>)
   智能体共享状态结构，所有节点都通过 `AgentState` 读写上下文。

5. [src/nodes](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes>)
   任务解析、程序构建、样本准备、3D 执行、变化检测、风险评估、建议生成。

6. [src/scene_preprocess](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess>)
   真实图像和点云转 `SceneTensorSample JSON`，并注册场景资产清单。

7. [src/clients](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients>)
   `case-service`、`file-service`、`hydro-program3d`、`change-detection` 的客户端封装。

### 4. 核心模块职责

#### 任务理解层

主要文件：

- [src/nodes/task.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task.py>)
- [src/nodes/task_contract.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_contract.py>)
- [src/nodes/task_openai_parser.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_openai_parser.py>)
- [src/nodes/task_rule_parser.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_rule_parser.py>)
- [src/nodes/program.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/program.py>)

职责：

- `task.py` 选择解析后端，处理 LLM 失败回退，写入 `task_intent`。
- `task_contract.py` 存放字段规范、允许词表、别名归一化和工具调用 schema。
- `task_openai_parser.py` 调 OpenAI-compatible 接口做工具调用式解析。
- `task_rule_parser.py` 在无 LLM 或 LLM 失败时做规则回退。
- `program.py` 把任务意图转成 `hydro-program3d` 可执行的 program。

#### 场景样本层

主要文件：

- [src/nodes/scene.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/scene.py>)
- [src/scene_samples/validator.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_samples/validator.py>)

`scene.py` 负责把 `scene_id / sample_id` 转成 `SceneTensorSample`。当前读取优先级：

1. 从 case-service 查询 `scene_asset_manifest`。
2. 根据 manifest 中的 `sceneSampleFileId` 从 file-service 下载样本 JSON。
3. case-service 没有清单时，读取 `AGENT_SCENE_MANIFEST_DIR` 下的本地 manifest。
4. 仍未命中时，读取 `AGENT_SCENE_SAMPLE_DIR` 下的本地样本 JSON。
5. 仍未命中且 `AGENT_ALLOW_DEMO_SAMPLE=true` 时，生成 demo sample。

如果命中的样本 JSON 损坏，或根对象不是 JSON object，会直接失败，不再回退 demo。

#### 场景预处理层

主要文件：

- [src/scene_preprocess/service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/service.py>)
- [src/scene_preprocess/image.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/image.py>)
- [src/scene_preprocess/point_cloud.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/point_cloud.py>)
- [src/scene_preprocess/sample_builder.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/sample_builder.py>)
- [src/scene_preprocess/quality.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/quality.py>)
- [src/scene_preprocess/manifest_registry.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/manifest_registry.py>)

当前 MVP 能力：

- 通过 file-service 下载主图像、点云、可选前后时相图像。
- 图像使用 Pillow 转 RGB、resize，输出 `[3,H,W]` 的 0-1 浮点数组。
- 点云支持 ASCII PLY、XYZ、CSV、TXT，暂不支持二进制 PLY/LAS/LAZ。
- 点云会均匀采样、中心化归一化，并生成 `z_norm / grid_slope / grid_roughness / grid_density` 几何特征。
- 生成 `SceneTensorSample JSON` 后上传到 file-service。
- 自动调用 case-service 注册 `scene_asset_manifest`。
- 返回 `qualityReport`，并把同一份报告写入 `SceneTensorSample.metadata.quality_report`。

#### 模型与证据层

主要文件：

- [src/clients/hydro_program3d.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/hydro_program3d.py>)
- [src/nodes/evidence.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/evidence.py>)
- [src/nodes/change.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/change.py>)

职责：

- 调 `hydro-program3d /execute` 获取模型执行结果。
- 调 `hydro-program3d /compile_evidence` 获取结构化 `EvidencePack`。
- 在任务存在时间变化意图，并且样本有前后时相图像时，调用 `change-detection /predict`。
- 对连接失败、超时、5xx 做有限重试。
- 对 4xx、响应 JSON 异常、无效 `EvidencePack` 做结构化失败。

下游风险节点只消费 `EvidencePack`，不直接消费原始 tensor 输出。

#### 风险与闭环层

主要文件：

- [src/nodes/risk.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/risk.py>)
- [src/nodes/recommendation.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/recommendation.py>)
- [src/clients/case_file.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/case_file.py>)
- [src/responses/execute_task.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/responses/execute_task.py>)

职责：

- `risk.py` 基于 `EvidencePack` 做规则加权风险评估。
- `recommendation.py` 生成建议卡。
- `work_order.py` 生成工单草稿，真实 `workOrderId` 由 case-service 落库后返回。
- `case_file.py` 构建 `agent_result_snapshot.v1`，并通过 case-service 写入 `case_agent_result.agent_result_json`。
- case 持久化失败不会阻断主结果返回，但会写入 `errors` 和 `case_persistence_status`。

### 5. 运行方式

从 `backend/` 目录启动完整链路：

```bash
docker compose up agent-service api-gateway file-service case-service
```

如果要拉起全部依赖：

```bash
docker compose up
```

完整闭环依赖：

- `nacos`
- `mysql`
- `minio`
- `case-service`
- `file-service`
- `hydro-program3d`
- `change-detection`，仅时间变化任务需要
- `api-gateway`，前端 HTTP 联调需要

本地直接运行：

```bash
cd backend/services/agent-service
python -m pip install -r requirements.txt
sh ./scripts/build_proto.sh
python ./src/main.py
```

Windows 下建议在 Git Bash、WSL 或容器内执行 `build_proto.sh`。

### 6. Proto 生成

Python pb2 生成产物位于：

```text
src/generated/
```

在 `backend/` 目录通过容器生成：

```bash
docker compose run --rm --no-deps agent-service sh ./scripts/build_proto.sh
```

脚本会清理旧的 `src/*_pb2.py` 和 `src/*_pb2_grpc.py`，然后重新生成到 `src/generated/`，并修正 `*_pb2_grpc.py` 的包内相对导入。

### 7. 核心环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AGENT_GRPC_PORT` | `9091` | agent-service gRPC 端口 |
| `NACOS_ENABLED` | `true` | 是否注册/发现 Nacos |
| `NACOS_SERVER_ADDR` | `localhost:8848` | Nacos 地址，compose 中为 `nacos:8848` |
| `NACOS_SERVICE_NAME` | `agent-service` | 本服务注册名 |
| `CASE_SERVICE_NAME` | `case-service` | case-service Nacos 服务名 |
| `CASE_GRPC_ADDR` | 空 | case-service 直连地址，配置后跳过 Nacos |
| `CASE_GRPC_TIMEOUT_SECONDS` | `20` | case-service gRPC 超时时间 |
| `FILE_SERVICE_NAME` | `file-service` | file-service Nacos 服务名 |
| `FILE_GRPC_ADDR` | 空 | file-service 直连地址，配置后跳过 Nacos |
| `FILE_GRPC_MAX_MESSAGE_BYTES` | `104857600` | file-service 大文件/样本下载的 gRPC 消息上限 |
| `FILE_GRPC_TIMEOUT_SECONDS` | `30` | file-service 查询/下载超时时间 |
| `HYDRO_PROGRAM3D_URL` | 空 | hydro-program3d 直连 URL，compose 中为 `http://hydro-program3d:8093` |
| `HYDRO_PROGRAM3D_SERVICE_NAME` | `hydro-program3d` | hydro-program3d Nacos 服务名 |
| `HYDRO_PROGRAM3D_CHECKPOINT_NAME` | `hydro_program3d_demo.pth` | `/execute` 使用的 checkpoint |
| `HYDRO_PROGRAM3D_DEVICE` | `cuda` | `/execute` 使用设备 |
| `HYDRO_MODEL_OVERRIDES_JSON` | 空 | 覆盖 `/execute.model_overrides` 的 JSON |
| `AGENT_TASK_PARSER_BACKEND` | `auto` | 任务理解后端，支持 `auto/openai/rule` |
| `AGENT_TASK_PARSER_MODEL` | `gpt-5.5` | LLM 工具调用解析使用的模型 |
| `AGENT_TASK_PARSER_TIMEOUT_SECONDS` | `45` | LLM 任务解析超时时间 |
| `AGENT_TASK_PARSER_MAX_TOKENS` | `500` | LLM 任务解析最大输出 token |
| `AGENT_TASK_PARSER_DISABLE_THINKING` | `false` | 是否给 Qwen 类模型传入关闭 thinking 的兼容参数 |
| `AGENT_TASK_PARSER_FALLBACK_TO_RULE` | `true` | LLM 解析失败时是否回退到规则解析 |
| `AGENT_TASK_PARSER_OPENAI_API_KEY` | `OPENAI_API_KEY` | 可选，覆盖任务解析专用 API Key |
| `AGENT_TASK_PARSER_OPENAI_BASE_URL` | `OPENAI_BASE_URL` | 可选，覆盖任务解析专用 OpenAI-compatible 地址 |
| `DASHSCOPE_API_KEY` | 空 | 可选，`OPENAI_API_KEY` 未配置时用于 DashScope/Qwen 兼容调用 |
| `CHANGE_DETECTION_URL` | 空 | change-detection 直连 URL，compose 中为 `http://change-detection:8011` |
| `CHANGE_DETECTION_SERVICE_NAME` | `change-detection` | change-detection Nacos 服务名 |
| `AGENT_SCENE_MANIFEST_DIR` | `/app/data/scene_manifests` | 本地 scene 资产 manifest 目录 |
| `AGENT_SCENE_MANIFEST_SERVICE_ENABLED` | `true` | 是否优先从 case-service 查询入库 manifest |
| `AGENT_SCENE_MANIFEST_SERVICE_TIMEOUT_SECONDS` | `CASE_GRPC_TIMEOUT_SECONDS` | 查询 scene manifest 的 gRPC 超时时间 |
| `AGENT_SCENE_PREPROCESS_IMAGE_SIZE` | `64` | `PreprocessScene` 默认输出图像尺寸 |
| `AGENT_SCENE_PREPROCESS_MAX_POINTS` | `4096` | `PreprocessScene` 默认点云采样上限 |
| `AGENT_SCENE_PREPROCESS_VERSION` | `preprocess-mvp-v1` | `PreprocessScene` 默认预处理版本 |
| `AGENT_SCENE_PREPROCESS_GEOMETRY_CELL_SIZE` | `2.0` | 网格几何特征的 XY cell size |
| `AGENT_SCENE_SAMPLE_DIR` | `/app/data/scene_samples` | 本地预处理后场景样本 JSON 目录 |
| `AGENT_ALLOW_DEMO_SAMPLE` | `true` | 缺少样本时是否生成 demo sample |

### 8. 常见排障

#### 任务执行后直接进入 `REVIEW_REQUIRED`

优先看：

- `task_intent.needs_clarification`
- `task_intent.needs_abstain`
- `evidence_pack.status`
- `errors`
- `trace`

#### 3D 服务通了但结果为空

优先确认：

- `scene_tensor_sample` 是否来自真实预处理样本，而不是 demo sample。
- `selected_program.target_label_ids / reference_label_ids / negative_label_ids` 是否符合任务。
- `hydro-program3d` 的 checkpoint、device、CLIP 权重是否齐全。

#### 变化检测没有触发

需要同时满足：

- `task_intent.temporal_intent=true`
- 样本或 manifest 中存在 `preImageFileId/postImageFileId`，或样本中存在前后时相引用。

#### case 没落库但接口没报错

这是当前设计。持久化失败不会阻断风险和建议返回，但响应中会出现：

- `case.persistenceStatus=failed`
- `case.persistenceError`
- `errors`

落库成功时，完整快照保存在 case-service 的 `case_agent_result.agent_result_json`。

## 二、接口文档版

### 1. HTTP 调用顺序

推荐真实场景链路：

```text
1. POST /api/v1/files 上传主图像
2. POST /api/v1/files 上传点云
3. 可选 POST /api/v1/files 上传前后时相图像
4. POST /api/v1/scenes/preprocess 生成 SceneTensorSample JSON 并注册 manifest
5. POST /api/v1/tasks/execute 执行巡查任务并创建真实工单
6. GET /api/v1/work-orders/{workOrderId} 查询工单
7. PATCH /api/v1/work-orders/{workOrderId}/status 更新工单状态
```

如果已有外部预处理系统，也可以跳过第 4 步的预处理，改为：

```text
1. POST /api/v1/files 上传已经生成的 SceneTensorSample JSON
2. POST /api/v1/scenes/{sceneId}/manifest 注册 sceneSampleFileId
3. POST /api/v1/tasks/execute 执行巡查任务
```

网关统一响应外壳：

```json
{
  "code": "0",
  "message": "OK",
  "data": {},
  "traceId": "e4b1c0c2a0c84b0b9d0f0b7f5f5c4d11"
}
```

业务字段都放在 `data` 中。下面的响应示例主要展示 `data`。

### 2. 上传文件

`POST /api/v1/files`

用途：上传图像、点云、预处理样本 JSON 或证据文件到 file-service，最终保存到 MinIO，并在 `file_asset` 中登记元数据。

请求类型：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 原始文件 |
| `fileType` | string | 否 | 建议传 `image`、`point_cloud`、`scene_sample`、`evidence` 等业务类型 |

示例：

```bash
curl -X POST http://localhost:8080/api/v1/files \
  -F "file=@./data/demo/ortho.png" \
  -F "fileType=image"
```

响应 `data`：

```json
{
  "fileId": "file-ortho-image",
  "fileName": "ortho.png",
  "contentType": "image/png",
  "size": 245760,
  "downloadUrl": "http://localhost:9000/hydro-files/...",
  "objectKey": "2026/06/scene/ortho.png",
  "fileType": "image",
  "checksumSha256": "..."
}
```

### 3. 查询文件元数据

`GET /api/v1/files/{fileId}`

用途：按 `fileId` 查询 file-service 中的文件元数据。

示例：

```bash
curl http://localhost:8080/api/v1/files/file-ortho-image
```

响应 `data` 与上传接口一致。

### 4. 真实场景预处理

`POST /api/v1/scenes/preprocess`

用途：让 agent-service 从 file-service 下载图像和点云，生成 `SceneTensorSample JSON`，上传回 file-service，并注册到 case-service 的 `scene_asset_manifest`。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sceneId` | string | 是 | 场景业务 ID，后续 `ExecuteTask` 用它查询 manifest |
| `sampleId` | string | 否 | 样本业务 ID，空时 agent-service 默认使用 `sceneId` |
| `imageFileId` | string | 是 | 主图像或正射图 fileId |
| `pointCloudFileId` | string | 是 | 点云文件 fileId |
| `preImageFileId` | string | 否 | 变化检测前时相图像 fileId |
| `postImageFileId` | string | 否 | 变化检测后时相图像 fileId |
| `preprocessVersion` | string | 否 | 预处理版本，空时使用 `AGENT_SCENE_PREPROCESS_VERSION` |
| `imageSize` | integer | 否 | 输出图像尺寸，`0` 或空表示使用默认值 |
| `maxPoints` | integer | 否 | 最大采样点数，`0` 或空表示使用默认值 |

示例：

```bash
curl -X POST http://localhost:8080/api/v1/scenes/preprocess \
  -H "Content-Type: application/json" \
  -d '{
    "sceneId": "demo-scene-001",
    "sampleId": "demo-sample-001",
    "imageFileId": "file-ortho-image",
    "pointCloudFileId": "file-point-cloud",
    "preImageFileId": "file-pre-image",
    "postImageFileId": "file-post-image",
    "preprocessVersion": "preprocess-mvp-v1",
    "imageSize": 64,
    "maxPoints": 4096
  }'
```

响应 `data`：

```json
{
  "sceneId": "demo-scene-001",
  "sampleId": "demo-sample-001",
  "sceneSampleFileId": "file-scene-sample-json",
  "imageFileId": "file-ortho-image",
  "pointCloudFileId": "file-point-cloud",
  "preImageFileId": "file-pre-image",
  "postImageFileId": "file-post-image",
  "preprocessVersion": "preprocess-mvp-v1",
  "manifestRegistered": true,
  "checksumSha256": "...",
  "sceneSampleFileName": "demo-scene-001_scene_sample.json",
  "status": "ok",
  "qualityReport": {
    "imageShape": [3, 64, 64],
    "pointsShape": [4096, 3],
    "pointsRgbShape": [4096, 3],
    "geometryFeatureShape": [4096, 4],
    "validPointMaskShape": [4096],
    "pointCountOriginal": 120000,
    "pointCountSampled": 4096,
    "maxPoints": 4096,
    "imageSize": 64,
    "geometryFeatureNames": [
      "z_norm",
      "grid_slope",
      "grid_roughness",
      "grid_density"
    ],
    "geometryCellSize": 2.0,
    "hasRgb": true,
    "hasPreImage": true,
    "hasPostImage": true,
    "sampleValidation": {
      "valid": true,
      "issues": []
    },
    "warnings": []
  }
}
```

### 5. 注册场景资产清单

`POST /api/v1/scenes/{sceneId}/manifest`

用途：把某个 `sceneId` 和已经生成的 `SceneTensorSample JSON` 绑定起来。外部预处理系统接入时会用到这个接口。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sceneSampleFileId` | string | 是 | 预处理样本 JSON 的 fileId |
| `sampleId` | string | 否 | 样本业务 ID |
| `imageFileId` | string | 否 | 主图像 fileId |
| `pointCloudFileId` | string | 否 | 点云 fileId |
| `preImageFileId` | string | 否 | 前时相图像 fileId |
| `postImageFileId` | string | 否 | 后时相图像 fileId |
| `preprocessVersion` | string | 否 | 预处理版本 |
| `checksumSha256` | string | 否 | 样本 JSON 校验和 |
| `schemaVersion` | string | 否 | 建议传 `scene_asset_manifest.v1` |

示例：

```bash
curl -X POST http://localhost:8080/api/v1/scenes/demo-scene-001/manifest \
  -H "Content-Type: application/json" \
  -d '{
    "sampleId": "demo-sample-001",
    "sceneSampleFileId": "file-scene-sample-json",
    "imageFileId": "file-ortho-image",
    "pointCloudFileId": "file-point-cloud",
    "preImageFileId": "file-pre-image",
    "postImageFileId": "file-post-image",
    "preprocessVersion": "preprocess-mvp-v1",
    "checksumSha256": "...",
    "schemaVersion": "scene_asset_manifest.v1"
  }'
```

响应 `data`：

```json
{
  "sceneId": "demo-scene-001",
  "sampleId": "demo-sample-001",
  "sceneSampleFileId": "file-scene-sample-json",
  "imageFileId": "file-ortho-image",
  "pointCloudFileId": "file-point-cloud",
  "preImageFileId": "file-pre-image",
  "postImageFileId": "file-post-image",
  "preprocessVersion": "preprocess-mvp-v1",
  "checksumSha256": "...",
  "schemaVersion": "scene_asset_manifest.v1",
  "createdAt": "2026-06-06T10:00:00+08:00",
  "updatedAt": "2026-06-06T10:00:00+08:00"
}
```

### 6. 查询场景资产清单

`GET /api/v1/scenes/{sceneId}/manifest`

用途：确认某个 `sceneId` 是否已经绑定可执行的 `SceneTensorSample JSON`。

示例：

```bash
curl http://localhost:8080/api/v1/scenes/demo-scene-001/manifest
```

响应 `data` 与注册接口一致。

### 7. 执行智能体任务

`POST /api/v1/tasks/execute`

用途：执行一条自然语言巡查任务。agent-service 会根据 `sceneId` 查 manifest、下载样本、执行 3D/2D、评估风险并尝试落库。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `taskText` | string | 是 | 自然语言巡查任务 |
| `sceneId` | string | 是 | 场景业务 ID |
| `debug` | boolean | 否 | `true` 时返回完整 trace；默认 `false` |

示例：

```bash
curl -X POST http://localhost:8080/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "taskText": "find thin linear ditch near waterline and exclude road",
    "sceneId": "demo-scene-001",
    "debug": true
  }'
```

响应 `data`：

```json
{
  "task": {
    "taskText": "find thin linear ditch near waterline and exclude road",
    "sceneId": "demo-scene-001"
  },
  "parsed": {
    "targetType": "ditch",
    "parserSource": "rule"
  },
  "risk": {
    "score": 0.73,
    "riskLevel": "HIGH",
    "reviewRequired": false
  },
  "recommendation": {
    "action": "REVIEW_AND_DISPATCH"
  },
  "workOrders": [
    {
      "work_order_id": "wo-001",
      "case_id": "case-001",
      "risk_type": "near_waterline_ditch_risk",
      "risk_level": "HIGH",
      "status": "ASSIGNED",
      "assignee": "field_team_a"
    }
  ],
  "case": {
    "caseId": "case-001",
    "status": "OPEN",
    "persistenceStatus": "saved",
    "persistenceError": ""
  },
  "execution": {
    "status": "completed",
    "evidenceStatus": "ok",
    "traceCount": 12,
    "errorCount": 0
  },
  "trace": [
    {
      "stage": "prepare_scene_sample",
      "message": "loaded scene sample from file-service",
      "dataJson": "{\"scene_id\":\"demo-scene-001\"}"
    }
  ]
}
```

说明：

- `errors` 只在 `errorCount > 0` 时返回。
- `trace` 只在请求 `debug=true` 时返回。
- `case.persistenceStatus=failed` 时，主风险结果仍可能正常返回。

### 8. 查询和更新工单

`GET /api/v1/work-orders/{workOrderId}`

用途：查询单个工单详情。

示例：

```bash
curl http://localhost:8080/api/v1/work-orders/wo-001
```

`GET /api/v1/cases/{caseId}/work-orders`

用途：查询某个 case 下的所有工单。

示例：

```bash
curl http://localhost:8080/api/v1/cases/case-001/work-orders
```

`PATCH /api/v1/work-orders/{workOrderId}/status`

用途：推进工单状态。当前 MVP 支持：

```text
TODO
ASSIGNED
IN_PROGRESS
REVIEWED
CLOSED
```

示例：

```bash
curl -X PATCH http://localhost:8080/api/v1/work-orders/wo-001/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "IN_PROGRESS",
    "assignee": "field_team_a",
    "closureNote": "现场人员已接单，准备复核候选区域"
  }'
```

响应 `data`：

```json
{
  "workOrderId": "wo-001",
  "caseId": "case-001",
  "riskCardId": "risk_primary",
  "riskType": "near_waterline_ditch_risk",
  "riskLevel": "HIGH",
  "title": "复核 near_waterline_ditch_risk 线索",
  "summary": "针对场景 demo-scene-001 的 HIGH 风险线索执行现场复核",
  "recommendedAction": "优先安排人工复核疑似高风险区域，并同步保留 3D 证据链",
  "status": "IN_PROGRESS",
  "assignee": "field_team_a",
  "deadline": "",
  "closureNote": "现场人员已接单，准备复核候选区域",
  "evidenceSummary": [],
  "schemaVersion": "case_work_order.v1",
  "createdAt": "2026-06-06T10:00:00",
  "updatedAt": "2026-06-06T10:10:00"
}
```

### 9. agent-service gRPC 接口

gRPC 定义位于 [proto/agent.proto](</D:/py_project/HydroGuardian/backend/services/agent-service/proto/agent.proto>)。

服务：

```proto
service AgentRpcService {
  rpc ExecuteTask (ExecuteTaskRequest) returns (ExecuteTaskReply);
  rpc PreprocessScene (PreprocessSceneRequest) returns (PreprocessSceneReply);
  rpc QueryFile (QueryFileRequest) returns (QueryFileReply);
}
```

#### ExecuteTask

请求：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_text` | string | 自然语言巡查任务 |
| `scene_id` | string | 场景业务 ID |
| `debug` | bool | 是否返回完整 trace |

响应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `target_type` | string | 解析出的目标类型 |
| `risk_score` | double | 风险分数 |
| `risk_level` | string | 风险等级 |
| `recommendation_action` | string | 推荐动作 |
| `case_id` | string | 落库后的 case ID |
| `case_status` | string | case 状态 |
| `execution_status` | string | agent 执行状态 |
| `parser_source` | string | `openai/rule/fallback` 等解析来源 |
| `evidence_status` | string | 证据状态 |
| `review_required` | bool | 是否需要人工复核 |
| `trace` | repeated | 调试链路事件 |
| `errors` | repeated | 错误事件 |
| `trace_total` | int32 | trace 总数 |
| `error_count` | int32 | error 总数 |
| `case_persistence_status` | string | case 持久化状态 |
| `case_persistence_error` | string | case 持久化错误 |
| `work_orders_json` | string | 已创建工单列表的 JSON 字符串 |

grpcurl 示例：

```bash
grpcurl -plaintext \
  -d '{"task_text":"find thin linear ditch near waterline and exclude road","scene_id":"demo-scene-001","debug":true}' \
  127.0.0.1:9091 \
  hydro.agent.v1.AgentRpcService/ExecuteTask
```

#### PreprocessScene

请求字段与 HTTP `/api/v1/scenes/preprocess` 一一对应，只是命名使用 snake_case。

响应中的 `scene_sample_file_id` 是生成并上传到 file-service 的 `SceneTensorSample JSON` 文件 ID，`quality_report_json` 是质量报告 JSON 字符串。

#### QueryFile

请求：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_id` | string | file-service 文件 ID |

响应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_id` | string | 文件 ID |
| `file_name` | string | 文件名 |
| `content_type` | string | MIME 类型 |
| `size` | int64 | 文件大小 |
| `download_url` | string | 下载地址 |
| `object_key` | string | MinIO object key |
| `file_type` | string | 业务文件类型 |
| `checksum_sha256` | string | SHA-256 |

### 10. SceneTensorSample 契约

`hydro-program3d /execute` 不读取原始文件路径，它需要预处理后的 JSON 张量。样本至少包含：

```json
{
  "sample_id": "demo-sample-001",
  "text": "find thin linear ditch near waterline and exclude road",
  "images": [
    [[0.0, 0.1], [0.2, 0.3]],
    [[0.0, 0.1], [0.2, 0.3]],
    [[0.0, 0.1], [0.2, 0.3]]
  ],
  "points_xyz": [[0.0, 0.0, 0.0]],
  "points_rgb": [[0.2, 0.3, 0.4]],
  "point_geometry_features": [[0.1, 0.0, 0.2, 0.8]],
  "valid_point_mask": [true]
}
```

校验规则：

- `images`: `[3,H,W]` 或 `[B,3,H,W]`
- `points_xyz`: `[N,3]` 或 `[B,N,3]`
- `points_rgb`: `[N,3]` 或 `[B,N,3]`
- `point_geometry_features`: `[N,G]` 或 `[B,N,G]`
- `valid_point_mask`: `[N]` 或 `[B,N]`
- `points_rgb / point_geometry_features / valid_point_mask` 的 batch 和点数必须与 `points_xyz` 一致

当前几何特征顺序固定为：

```text
z_norm
grid_slope
grid_roughness
grid_density
```

变化检测任务可额外包含前后时相引用。使用 manifest 链路时，推荐通过 `preImageFileId/postImageFileId` 提供。

### 11. 当前限制

- 点云预处理暂不支持二进制 PLY/LAS/LAZ。
- 风险评分仍是规则版，后续可以替换为学习式评分器。
- recommendation 和 work order 已拆成独立节点，但工单状态流转仍是 MVP 版本。
- `AGENT_ALLOW_DEMO_SAMPLE=true` 适合联调，不适合真实推理验收。
- gRPC 返回给上游的是摘要和诊断字段，不是完整证据链对象；完整快照落在 case-service。

完整 MVP 升级清单见 [MVP_UPGRADE.md](</D:/py_project/HydroGuardian/backend/services/agent-service/MVP_UPGRADE.md>)。
