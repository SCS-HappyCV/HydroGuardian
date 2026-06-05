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
   |- scene_preprocess/    # 图像/点云预处理与 manifest 注册
   `- nodes/               # LangGraph 节点
```

## 接手指南

这部分是给下一位接手 `agent-service` 的同学用的，目标是先快速看懂主链路，再决定改哪一层。

### 1. 先看什么

建议按下面顺序读代码：

1. [src/main.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/main.py>)  
   服务启动入口，负责拉起 gRPC server，并处理 Nacos 注册与心跳。
2. [src/grpc_service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/grpc_service.py>)  
   `ExecuteTask / PreprocessScene` 的真正入口。这里会初始化 `AgentState` 执行智能体图，也会触发真实场景预处理。
3. [src/agent_graph.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/agent_graph.py>)  
   主流程编排定义。现在是线性 MVP 链路：
   `parse_task -> build_program -> prepare_scene_sample -> execute_3d -> maybe_detect_change -> assess_risk -> generate_recommendation`
4. [src/state.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/state.py>)  
   共享状态结构定义。后面所有节点都围绕这份 `AgentState` 原地读写。
5. `src/nodes/*.py`  
   每个节点只负责一段业务语义，先看 `task.py`、`program.py`、`scene.py`、`risk.py`。
6. `src/clients/*.py`  
   这里是对外部服务的真实调用封装，特别是：
   - [src/clients/hydro_program3d.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/hydro_program3d.py>)
   - [src/clients/change_detection.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/change_detection.py>)
   - [src/clients/case_file.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/case_file.py>)

### 2. 当前主链路怎么跑

一次 `ExecuteTask` 调用的核心路径是：

```text
api-gateway / grpc 客户端
-> AgentRpcService.ExecuteTask
-> 初始化 AgentState
-> LangGraph 逐节点执行
-> 调 hydro-program3d /execute
-> 调 hydro-program3d /compile_evidence
-> 可选调 change-detection /predict
-> 生成 RiskCard / RecommendationCard / WorkOrderCard
-> 调 case-service 持久化
-> 返回摘要结果
```

要点：

- `AgentState` 是这条链路里的唯一共享上下文。
- 节点之间不直接互调，统一通过 `state` 传递数据。
- 当前图里的提前退出，主要通过 `status`、`needs_clarification`、`needs_abstain` 和失败时构造的 `EvidencePack` 降级实现。

### 3. 各层现在分别负责什么

#### 任务层

- [src/nodes/task.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task.py>)
- [src/nodes/task_contract.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_contract.py>)
- [src/nodes/task_openai_parser.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_openai_parser.py>)
- [src/nodes/task_rule_parser.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_rule_parser.py>)
- [src/nodes/program.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/program.py>)

当前任务理解已经拆成几层：

- `task.py` 只负责选择解析后端、处理 LLM 失败回退、写入 `task_intent`
- `task_contract.py` 放任务理解的字段规范、允许词表、别名归一化和工具调用 schema
- `task_openai_parser.py` 负责 OpenAI-compatible 工具调用解析
- `task_rule_parser.py` 负责无 LLM 或 LLM 失败时的规则回退解析
- `program.py` 把任务意图转成 `hydro-program3d` 可执行的 field schema program

如果后面要改 prompt、工具 schema 或允许词表，优先改 `task_contract.py`。如果要换 LLM 调用方式，优先改 `task_openai_parser.py`。

#### 数据层

- [src/nodes/scene.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/scene.py>)

这里负责把 `scene_id / sample_id` 转成 `SceneTensorSample`。

当前策略：

- 先向 case-service 查询 `scene_asset_manifest`，按 `sceneId` 找到 `sceneSampleFileId`
- 如果 case-service 没有清单，再去 `AGENT_SCENE_MANIFEST_DIR` 找 `{scene_id}.json` 或 `{sample_id}.json`
- 命中 manifest 后，按 manifest 中的 `sceneSampleFileId` 从 file-service 下载 `SceneTensorSample`
- 如果没有 manifest，再去 `AGENT_SCENE_SAMPLE_DIR` 找本地 `{scene_id}.json` 或 `{sample_id}.json`
- 找不到且 `AGENT_ALLOW_DEMO_SAMPLE=true` 时，回退到 demo sample
- 如果命中的样本文件 JSON 损坏或根对象不是 JSON object，会直接失败，不再回退 demo
- 进入 3D 执行前校验 `images / points_xyz / points_rgb / point_geometry_features / valid_point_mask`
- trace 中会记录样本来源、shape 摘要、点数、是否 demo、是否包含变化检测图片引用、来源文件 `fileId/objectKey/checksum`

这意味着：

- 现在图编排和服务联通性可以独立调
- 真实样本生成已经先放在 `src/scene_preprocess/`，后续如果预处理变重，可以把这个包整体拆成独立服务
- 真实推理验收时应关闭 demo sample 回退

#### 预处理层

- [src/scene_preprocess/service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/service.py>)
- [src/scene_preprocess/image.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/image.py>)
- [src/scene_preprocess/point_cloud.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/point_cloud.py>)
- [src/scene_preprocess/sample_builder.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/sample_builder.py>)
- [src/scene_preprocess/manifest_registry.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/manifest_registry.py>)

当前预处理是 MVP 版本：

- 图像使用 Pillow 转 RGB、resize，并输出 `[3,H,W]` 的 0-1 浮点数组
- 点云支持 ASCII PLY、XYZ、CSV、TXT 等文本格式，暂不支持二进制 PLY/LAS/LAZ
- 点云会均匀采样、中心化归一化，并参考 `wcs_unified.geometry_features` 生成 `z_norm / grid_slope / grid_roughness / grid_density`
- 生成的 `SceneTensorSample JSON` 会上传到 file-service，并自动调用 case-service 注册 `scene_asset_manifest`

#### 证据执行层

- [src/clients/hydro_program3d.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/hydro_program3d.py>)

职责是：

- 发现或直连 `hydro-program3d`
- 调 `/execute` 拿原始模型输出
- 调 `/compile_evidence` 拿结构化 `EvidencePack`
- 将 `/health / /execute / /compile_evidence` 的状态码、耗时、错误类型写入 trace
- 对连接失败、超时和 5xx 做一次有限重试
- 对 4xx、响应 JSON 异常和无效 `EvidencePack` 直接结构化失败

当前约定很重要：

- 下游风险节点不直接消费原始 tensor 输出
- 下游只消费 `EvidencePack`

这层出了错，也会构造一个失败态 `EvidencePack`，让后面的风险节点可以降级到 `REVIEW_REQUIRED`，而不是整条链路崩掉。失败态 `EvidencePack.raw_trace` 会包含：

- `error_type`
- `stage`
- `status_code`
- `duration_ms`
- `base_url`
- `request_summary`

#### 风险与闭环层

- [src/nodes/risk.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/risk.py>)
- [src/nodes/recommendation.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/recommendation.py>)
- [src/clients/case_file.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/case_file.py>)

当前策略是：

- `risk.py` 基于 `EvidencePack` 做可解释规则加权
- `recommendation.py` 同时生成建议卡和工单卡
- `case_file.py` 构建 `agent_result_snapshot.v1`，完整快照通过 case-service 写入 `case_agent_result.agent_result_json`
- `tags` 只保留风险类型、证据状态、样本摘要和快照存储位置等轻量索引信息
- case-service 持久化失败不会阻断主结果，但会在返回中标记 `case_persistence_status=failed`

注意：现在 recommendation 和 work order 还没拆节点，这是有意保留的 MVP 形态。

### 4. 接手时最常见的改动入口

#### 想把规则解析换成 LLM

从这里开始：

- [src/nodes/task.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task.py>)
- [src/nodes/task_openai_parser.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_openai_parser.py>)
- [src/nodes/task_contract.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/task_contract.py>)
- [src/nodes/program.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/program.py>)

建议保持输出结构不变，至少先兼容：

- `task_intent`
- `selected_program`
- `program_bundle`

这样后面的节点基本不用跟着重写。

#### 想接真实样本预处理

从这里开始：

- [src/scene_preprocess/service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/service.py>)
- [src/scene_preprocess/point_cloud.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/scene_preprocess/point_cloud.py>)
- [src/nodes/scene.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/scene.py>)

目标是让 `scene_preprocess` 稳定生成 `SceneTensorSample`，让 `scene.py` 只负责按 `sceneId` 读取和校验样本。

#### 想调整风险等级或评分逻辑

从这里开始：

- [src/nodes/risk.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/risk.py>)

建议先调当前规则权重，再决定要不要上学习式风险评分器。

#### 想打通外部工作流 / 派单系统

从这里开始：

- [src/nodes/recommendation.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/recommendation.py>)
- [src/clients/case_file.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/case_file.py>)

大概率要把“建议生成”和“工单创建”拆开。

### 5. 外部依赖怎么理解

联调时最关键的外部依赖有 4 个：

- `hydro-program3d`  
  负责 3D 执行和证据编译，是主链路核心依赖。
- `change-detection`  
  只在任务有时间变化意图且 sample 带 `pre/post image` 时触发。
- `case-service`  
  负责 case 持久化和 `scene_asset_manifest` 查询；case 落库失败不会阻断 agent 生成风险和建议，场景清单查询异常会让样本准备阶段失败。
- `file-service`  
  负责把前端上传的图像、点云、样本 JSON 和证据产物保存到 MinIO，并在 `file_asset` 中登记 `fileId / objectKey / fileType / checksumSha256`。

此外，`Nacos` 负责发现：

- agent-service 自己注册
- case/file/change/hydro-program3d 等服务发现

如果本地只想单独调某个服务，优先直接配显式地址环境变量，减少发现链路干扰。

### 6. 常见排障点

#### 任务执行后直接进入 `REVIEW_REQUIRED`

先看：

- `task_intent.needs_clarification`
- `task_intent.needs_abstain`
- `evidence_pack.status`
- `errors`
- `trace`

#### 3D 服务看起来通了，但结果为空

优先确认：

- `scene_tensor_sample` 是否真的是预处理样本，而不是 demo sample
- `selected_program.target_label_ids / reference_label_ids / negative_label_ids` 是否填对
- `hydro-program3d` 的 checkpoint、device、CLIP 权重是否齐全

#### change detection 没触发

先看两个条件：

- `task_intent.temporal_intent` 是否为 `true`
- `scene_tensor_sample` 里是否带 `pre_image_path` 和 `post_image_path`

#### case 没落库，但接口没报错

这是当前设计使然。  
`grpc_service.py` 里持久化失败会记录 `errors`，不会阻断主结果返回。
接口会返回 `case_persistence_status / case_persistence_error`；即使落库失败，agent-service 也会在本次响应的内部 `case_result` 中保留 `agentResultSnapshot`，便于调试链路回放。落库成功时，完整快照保存在 case-service 的 `case_agent_result.agent_result_json`。

### 7. 现在的边界，接手时不要误判

当前 `agent-service` 已经能打通的是：

- 规则任务解析
- program 构建
- sample 装配
- 3D 执行
- 证据编译
- 风险卡 / 建议卡 / 工单卡生成
- case 持久化
- agent 执行快照构建，并通过 case-service 保存到 `case_agent_result` 数据表

当前还明显是 MVP 的地方：

- 任务理解已有 LLM 工具调用版，但 prompt、工具 schema 和规则回退仍需要随业务继续校准
- scene sample 还没有正式预处理服务
- 风险评分还是规则版
- recommendation 和 work order 还没彻底拆层
- gRPC 返回给上游的是摘要和链路诊断字段，不是完整证据链对象

完整的 MVP 升级清单见 [MVP_UPGRADE.md](</D:/py_project/HydroGuardian/backend/services/agent-service/MVP_UPGRADE.md>)。

所以后续扩展时，优先做“替换节点内部实现”，尽量不要先打散整张图。

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
| `CASE_GRPC_TIMEOUT_SECONDS` | `20` | case-service gRPC 调用默认超时时间 |
| `FILE_GRPC_ADDR` | 空 | file-service 直连地址，配置后跳过 Nacos |
| `FILE_GRPC_MAX_MESSAGE_BYTES` | `104857600` | file-service 大文件/样本下载的 gRPC 消息上限 |
| `FILE_GRPC_TIMEOUT_SECONDS` | `30` | file-service 查询/下载超时时间 |
| `HYDRO_PROGRAM3D_URL` | 空 | hydro-program3d 直连 URL，compose 中配置为 `http://hydro-program3d:8093` |
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
| `CHANGE_DETECTION_URL` | 空 | change-detection 直连 URL，compose 中配置为 `http://change-detection:8011` |
| `CHANGE_DETECTION_SERVICE_NAME` | `change-detection` | change-detection Nacos 服务名 |
| `AGENT_SCENE_MANIFEST_DIR` | `/app/data/scene_manifests` | scene 资产 manifest 目录，优先级高于本地样本目录 |
| `AGENT_SCENE_MANIFEST_SERVICE_ENABLED` | `true` | 是否优先从 case-service 查询入库的 scene 资产 manifest |
| `AGENT_SCENE_MANIFEST_SERVICE_TIMEOUT_SECONDS` | `CASE_GRPC_TIMEOUT_SECONDS` | 查询 scene 资产 manifest 的 gRPC 超时时间 |
| `AGENT_SCENE_PREPROCESS_IMAGE_SIZE` | `64` | `PreprocessScene` 默认输出图像尺寸 |
| `AGENT_SCENE_PREPROCESS_MAX_POINTS` | `4096` | `PreprocessScene` 默认点云采样上限 |
| `AGENT_SCENE_PREPROCESS_VERSION` | `preprocess-mvp-v1` | `PreprocessScene` 默认预处理版本 |
| `AGENT_SCENE_PREPROCESS_GEOMETRY_CELL_SIZE` | `2.0` | 网格几何特征的 XY cell size |
| `AGENT_SCENE_SAMPLE_DIR` | `/app/data/scene_samples` | 预处理后场景样本 JSON 目录 |
| `AGENT_ALLOW_DEMO_SAMPLE` | `true` | 缺少场景样本时是否生成 demo sample |

## 场景样本

`hydro-program3d /execute` 不读取原始文件路径，调用方必须提供预处理后的 JSON 张量。推荐链路是：

1. 前端先通过 `api-gateway POST /api/v1/files` 上传图像和点云
2. 网关转发给 file-service 保存到 MinIO，并返回各自的 `fileId`
3. 前端通过 `api-gateway POST /api/v1/scenes/preprocess` 触发 agent-service 内部预处理
4. agent-service 下载原始资产，生成 `SceneTensorSample JSON`，上传到 file-service
5. agent-service 自动调用 case-service 注册 `scene_asset_manifest`
6. agent-service 执行任务时优先从 case-service 查询该清单，再按 `sceneSampleFileId` 下载样本 JSON

预处理示例：

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

如果你已经有外部预处理流水线生成了 `SceneTensorSample JSON`，也可以继续手动上传 sample JSON 后注册清单：

```bash
curl -X POST http://localhost:8080/api/v1/scenes/demo-scene-001/manifest \
  -H "Content-Type: application/json" \
  -d '{
    "sampleId": "demo-sample-001",
    "sceneSampleFileId": "file-scene-sample-json",
    "imageFileId": "file-ortho-image",
    "pointCloudFileId": "file-point-cloud",
    "preprocessVersion": "preprocess-v1",
    "schemaVersion": "scene_asset_manifest.v1"
  }'
```

查询清单示例：

```bash
curl http://localhost:8080/api/v1/scenes/demo-scene-001/manifest
```

本地 manifest 文件仍作为离线联调兜底。可在 `AGENT_SCENE_MANIFEST_DIR` 放置资产清单：

```json
{
  "schemaVersion": "scene_asset_manifest.v1",
  "sceneId": "demo-scene-001",
  "sampleId": "demo-sample-001",
  "sceneSampleFileId": "file-scene-sample-json",
  "imageFileId": "file-ortho-image",
  "pointCloudFileId": "file-point-cloud",
  "preImageFileId": "file-pre-image",
  "postImageFileId": "file-post-image",
  "preprocessVersion": "preprocess-v1",
  "createdAt": "2026-06-05T10:00:00+08:00"
}
```

manifest 文件名仍按以下规则查找：

```text
{scene_id}.json
{sample_id}.json
```

如果没有 manifest，`agent-service` 会再从 `AGENT_SCENE_SAMPLE_DIR` 读取同名本地样本 JSON。

样本至少应包含真实 JSON 数组，而不是 shape 字符串：

```json
{
  "sample_id": "demo-001",
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

如果是变化检测任务，可额外提供：

```json
{
  "pre_image_path": "/app/data/pre.png",
  "post_image_path": "/app/data/post.png"
}
```

如果使用 manifest，`preImageFileId/postImageFileId` 会写入样本元数据；变化检测节点会优先通过 file-service gRPC 下载前后时相影像，再转发给 change-detection。`pre_image_url/post_image_url` 仅作为调试和兜底引用。

## gRPC 接口

服务定义在 `proto/agent.proto`：

- `ExecuteTask`
- `PreprocessScene`
- `QueryFile`

文件上传不再绕 agent-service，前端走 `api-gateway POST /api/v1/files`，网关转发到 file-service gRPC `UploadFile`。agent-service 后续通过 `PreprocessScene` 下载这些 `fileId`，生成真实 `SceneTensorSample`，再上传 sample JSON 并注册 manifest。

示例：

```bash
grpcurl -plaintext \
  -d '{"task_text":"find thin linear ditch near waterline and exclude road","scene_id":"demo-001","debug":true}' \
  127.0.0.1:9091 \
  hydro.agent.v1.AgentRpcService/ExecuteTask
```

`debug=true` 时，`ExecuteTask` 会返回完整 `trace`；无论是否开启 debug，返回体都会带上：

- `execution_status`
- `parser_source`
- `evidence_status`
- `review_required`
- `trace_total`
- `error_count`
- `errors`
- `case_persistence_status`
- `case_persistence_error`

## 失败处理

- 任务不可解析：进入 `REVIEW_REQUIRED` 或 `ABSTAINED`
- 缺少场景样本：如果 `AGENT_ALLOW_DEMO_SAMPLE=false`，直接返回结构化失败
- 3D 服务不可达、超时、4xx/5xx、响应 JSON 异常或 `EvidencePack` 无效：生成 `execution_failed` 形式的 `EvidencePack`
- 证据不足、no-target 或拒答信号高：风险等级进入 `REVIEW_REQUIRED`
- case-service 持久化失败：不阻断风险和建议返回，但会记录到 `errors`

## 当前限制

- 第一版任务解析是规则实现，后续可替换为 LLM/工具调用式解析。
- 2D 变化检测只有在任务含时间变化意图且样本中有 `pre_image_path/post_image_path` 时才触发。
- `AGENT_ALLOW_DEMO_SAMPLE=true` 适合联调，不适合真实推理验收。
