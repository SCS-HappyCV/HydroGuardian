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

## 接手指南

这部分是给下一位接手 `agent-service` 的同学用的，目标是先快速看懂主链路，再决定改哪一层。

### 1. 先看什么

建议按下面顺序读代码：

1. [src/main.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/main.py>)  
   服务启动入口，负责拉起 gRPC server，并处理 Nacos 注册与心跳。
2. [src/grpc_service.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/grpc_service.py>)  
   `ExecuteTask` 的真正入口。这里会初始化 `AgentState`，执行整张 LangGraph 图，并在最后尝试持久化 case。
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

- 先去 `AGENT_SCENE_SAMPLE_DIR` 找 `{scene_id}.json` 或 `{sample_id}.json`
- 找不到且 `AGENT_ALLOW_DEMO_SAMPLE=true` 时，回退到 demo sample

这意味着：

- 现在图编排和服务联通性可以独立调
- 但真实推理上线前，必须把这里替换成正式预处理流水线

#### 证据执行层

- [src/clients/hydro_program3d.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/hydro_program3d.py>)

职责是：

- 发现或直连 `hydro-program3d`
- 调 `/execute` 拿原始模型输出
- 调 `/compile_evidence` 拿结构化 `EvidencePack`

当前约定很重要：

- 下游风险节点不直接消费原始 tensor 输出
- 下游只消费 `EvidencePack`

这层出了错，也会构造一个失败态 `EvidencePack`，让后面的风险节点可以降级到 `REVIEW_REQUIRED`，而不是整条链路崩掉。

#### 风险与闭环层

- [src/nodes/risk.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/risk.py>)
- [src/nodes/recommendation.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/recommendation.py>)
- [src/clients/case_file.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/clients/case_file.py>)

当前策略是：

- `risk.py` 基于 `EvidencePack` 做可解释规则加权
- `recommendation.py` 同时生成建议卡和工单卡
- `case_file.py` 把摘要结果落到 case-service

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

- [src/nodes/scene.py](</D:/py_project/HydroGuardian/backend/services/agent-service/src/nodes/scene.py>)

目标不是改 graph，而是让这个节点稳定输出 `SceneTensorSample`。

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
  负责 case 持久化；挂掉不会阻断 agent 生成风险和建议。
- `file-service`  
  当前主要用于文件查询接口。

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
`grpc_service.py` 里持久化失败只记 `errors`，不会阻断主结果返回。

### 7. 现在的边界，接手时不要误判

当前 `agent-service` 已经能打通的是：

- 规则任务解析
- program 构建
- sample 装配
- 3D 执行
- 证据编译
- 风险卡 / 建议卡 / 工单卡生成
- case 持久化

当前还明显是 MVP 的地方：

- 任务理解已有 LLM 工具调用版，但 prompt、工具 schema 和规则回退仍需要随业务继续校准
- scene sample 还没有正式预处理服务
- 风险评分还是规则版
- recommendation 和 work order 还没彻底拆层
- gRPC 返回给上游的是摘要，不是完整证据链对象

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
| `FILE_GRPC_ADDR` | 空 | file-service 直连地址，配置后跳过 Nacos |
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
