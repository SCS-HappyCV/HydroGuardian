# Hydro Remote Agent 完整实施方案

## 1. 建设目标

本方案为水利数据智能分析 Agent 建立独立部署体系。前端和 Agent 服务部署在本地工作站，点云分割、多模态点云分割、变化检测等专家模型部署在远程 GPU 服务器。两端不依赖 HydroGuardian Compose，通过 MinIO 传输数据，通过 WebSocket 长连接实时调度任务。

核心目标：

- 前端提交一个业务任务，Agent 自动拆解为多个专家步骤并编排执行。
- 远程 GPU Worker 主动连接本地服务，因此不要求 GPU 服务器暴露入站端口。
- 大文件不经过 WebSocket，统一写入 MinIO，消息只携带对象键、校验和及元数据。
- PostgreSQL 保存任务、步骤、租约、事件、产物和审计记录，保证可恢复和可追溯。
- 支持专家模型按需加载、GPU 分配、断线重连、超时回收、幂等执行和失败重试。

## 2. 总体架构

```text
本地 agent.example.internal
  Nginx / API Gateway
       |
  Agent API + Workflow Orchestrator
       |---- PostgreSQL：持久化状态、任务、事件、产物
       |---- Redis：缓存、分布式锁、限流、短期在线状态
       |---- RabbitMQ：本地异步通知和后台事件
       |---- MinIO：输入数据、模型产物、结果文件
       |<=== WebSocket / WSS：Worker 主动连接、任务调度 ===|
                                                        |
远程 GPU 服务器                                      |
  GPU Worker 容器
    WebSocket Client + Watchdog
    Expert Runtime + Model Pool
      点云语义分割 / 多模态点云分割 / 图像变化检测
```

建议本地对外仅开放 `80/443`，MinIO 管理端口仅本机或内网管理使用。远程 Worker 只需要主动访问本地的 WebSocket 入口和 MinIO，不需要远程服务器开放入站端口。

## 3. 服务边界

### 3.1 Agent API

负责用户认证、任务创建、任务查询、结果下载地址生成、WebSocket Worker 接入、前端进度推送和健康检查。API 不直接运行 GPU 推理。

### 3.2 Workflow Orchestrator

负责根据任务类型和输入资产生成 Workflow，检查专家能力，选择可用 Worker，维护步骤依赖关系，处理重试、超时、取消和最终汇总。

### 3.3 Expert Worker

负责远程 GPU 上的实际推理。Worker 不接受公网入站请求，只通过 WebSocket 接收任务；收到任务后从 MinIO 下载输入，调用 Expert Runtime，上传输出，再通过 WebSocket 回传状态。

### 3.4 Expert Runtime

统一封装五类核心专家的 ToolSpec 和真实 Adapter。点云语义分割使用 GUFNet，技术层派生接口可复用同一模型；变化检测使用 `vendor/change_detection`。其余专家通过相同接口接入，避免 Workflow 依赖具体模型代码。

## 4. 基础设施职责

### PostgreSQL

作为唯一持久化事实源，保存：

- `jobs`：用户任务、任务类型、总体状态、创建者和时间。
- `workflow_steps`：步骤、依赖、输入输出资产、重试次数和错误。
- `workers`：Worker 身份、能力、GPU、版本和最后心跳。
- `worker_leases`：任务租约、过期时间、分配记录和释放记录。
- `artifacts`：MinIO 对象键、大小、媒体类型、校验和和生命周期。
- `job_events`：状态变化、进度、日志摘要和审计信息。
- `idempotency_keys`：客户端请求幂等键及对应任务。

所有状态变化使用事务写入，并通过版本号或条件更新防止旧消息覆盖新状态。

### Redis

只保存可丢失的短期状态：Worker 在线缓存、分布式锁、API 限流、短期进度缓存和重复消息去重窗口。Redis 发生故障时，系统应回退到 PostgreSQL，不得依赖 Redis 恢复任务。

### RabbitMQ

用于本地服务内部的异步事件，例如任务完成通知、索引更新、报表生成和通知推送。RabbitMQ 不承担远程 Worker 的主任务通道，远程任务状态以 WebSocket 和 PostgreSQL 为准。

### MinIO

用于传输点云、影像、标注、模型输出和可视化文件。推荐建立以下 Bucket：

- `hydro-input`：用户上传的原始点云和影像，默认禁止公开读。
- `hydro-intermediate`：步骤间中间结果，按任务生命周期清理。
- `hydro-output`：最终结果和报告，按任务保留策略归档。
- `hydro-models`：远程 Worker 使用的模型权重和配置，只读访问。

对象命名统一使用逻辑 ID，不使用服务器绝对路径：

```text
{bucket}/{tenant_id}/{job_id}/{step_id}/{artifact_id}/{filename}
```

数据库记录对象键、版本号、大小、SHA-256 和生成步骤。Worker 通过短期 presigned URL 或 MinIO 服务账号访问对象；严禁把永久 Access Key 放入 WebSocket 消息。

## 5. 资产 ID 协议

前端和 Workflow 只传递 `artifact_id`，不传递 `D:\`、`E:\` 或服务器目录。每个输入资产至少包含：

```json
{
  "artifact_id": "art_01J...",
  "bucket": "hydro-input",
  "object_key": "tenant-a/job-01/input/art_01J/scene.las",
  "media_type": "application/vnd.las",
  "size_bytes": 123456789,
  "sha256": "...",
  "metadata": {"crs": "EPSG:4490", "tile_id": "..."}
}
```

模型 Adapter 只接收本地临时工作目录或已解析的资产句柄，由 Runtime 负责下载、解压、校验、清理和结果上传。这样可同时兼容本地开发、Docker 和远程 GPU 环境。

## 6. WebSocket 控制协议

连接地址：

```text
ws://agent.example.internal:18080/internal/workers/ws
wss://agent.example.com/internal/workers/ws
```

生产环境使用 `WSS`。连接建立后先完成认证，再进入消息循环。每条消息带 `protocol_version`、`message_id`、`worker_id`、`timestamp` 和 `correlation_id`。

### 注册流程

Worker 发送 `register`：

```json
{
  "type": "register",
  "message_id": "msg-1",
  "worker_id": "gpu-worker-01",
  "worker_version": "2026.08.1",
  "capabilities": ["point_segmentation", "multimodal_point_segmentation", "change_detection"],
  "gpus": [{"index": 0, "name": "NVIDIA GPU", "memory_bytes": 25769803776}],
  "protocol_version": 1
}
```

Agent 校验签名和 Worker 白名单后回复 `registered`，返回心跳间隔、最大并发数、租约时长和待恢复任务列表。

### 任务和状态消息

- `task`：下发一个 Workflow Step，包含 `step_id`、`job_id`、工具名、参数、输入资产和输出约束。
- `task_ack`：Worker 已持久化接收任务，返回 `step_id` 和 `attempt`。
- `progress`：报告阶段、百分比、已处理 tile、吞吐量和可选日志摘要。
- `heartbeat`：Worker 报告存活、GPU 利用率、显存和当前步骤。
- `completed`：返回输出资产清单、指标、运行时长和模型版本。
- `failed`：返回稳定错误码、可重试标志、错误摘要和日志资产。
- `cancel`：请求 Worker 停止步骤并清理临时目录。
- `ack`：Agent 对关键消息确认已持久化。

大日志、点云、影像和预测文件一律放 MinIO，WebSocket 仅传引用。

## 7. 断线恢复与可靠性

### 主动重连

Worker 使用指数退避加随机抖动重连。重连后携带 `last_received_sequence` 和正在执行的 `step_id`，Agent 返回未确认消息。Worker 对同一 `message_id` 重复收到的任务只执行一次。

### 租约和超时

任务下发后 PostgreSQL 创建租约。Worker 通过心跳续租；超过租约时间未续租时，Orchestrator 将步骤标为 `lost`，释放 Worker 并按策略重试。服务重启时由恢复任务扫描器重新投递过期租约。

### 幂等

每个步骤使用 `job_id + step_id + attempt` 作为执行键，结果使用确定性的 `artifact_id` 或版本号。完成消息重复到达时，Agent 只接受第一次有效版本，后续消息记录为重复消息，不重复推进下游步骤。

## 8. 状态机

Job 状态：

```text
CREATED -> VALIDATING -> QUEUED -> RUNNING -> SUCCEEDED
                                      |          |
                                      |          -> PARTIAL_SUCCEEDED
                                      -> FAILED / CANCELLED
```

Step 状态：

```text
PENDING -> READY -> DISPATCHED -> RUNNING -> SUCCEEDED
                         |             |        |
                         |             -> LOST   -> RETRY_WAIT -> READY
                         -> CANCELLED       -> FAILED
```

状态转换只能由服务端事务完成，并记录操作者、原因、旧状态、新状态和事件序号。前端展示状态以服务端事件为准，不根据本地计时器推断任务完成。

## 9. Expert Runtime 和模型池

### ToolSpec

每个专家统一定义工具名、输入资产类型、参数 Schema、输出类型、GPU/CPU 需求、超时和可重试错误。例如：

```json
{
  "name": "point_segmentation",
  "input_types": ["point_cloud"],
  "output_types": ["semantic_labels", "metrics"],
  "resource": {"device": "cuda", "min_vram_gb": 16},
  "timeout_seconds": 7200
}
```

### 模型池

Runtime 启动时读取配置，不必一次加载全部模型。采用按需加载和 LRU/显存阈值回收；同一模型的并发请求使用队列控制，避免显存超卖。每个 Adapter 返回统一的 `ExpertResult`，包括结果资产、指标、可视化资产、模型版本和日志。

### GPU 资源管理

Worker 注册每块 GPU 的显存和能力。调度器根据工具需求、当前占用和优先级选择 GPU。发生 CUDA OOM 时先释放缓存并重试一次；再次失败则返回稳定错误码 `GPU_OOM`，由策略决定降级、换卡或终止步骤。

### 现有模型接入

- 点云语义分割：使用 GUFNet Adapter。
- 多模态点云语义分割：使用 GUFNet Adapter，保留 CLIP 文本分支。
- 图像变化检测：使用 `vendor/change_detection` Adapter。
- 其余三个专家沿用同一 ToolSpec、Remote Adapter 和结果协议，待模型部署后仅增加 Worker capability 和 Runtime 配置。

## 10. 前端接口

建议 API：

- `POST /api/v1/assets/presign`：获取上传 URL。
- `POST /api/v1/jobs`：创建任务，支持 `Idempotency-Key`。
- `GET /api/v1/jobs/{job_id}`：查询任务和步骤状态。
- `POST /api/v1/jobs/{job_id}/cancel`：取消任务。
- `GET /api/v1/jobs/{job_id}/events`：SSE 推送进度。
- `GET /api/v1/artifacts/{artifact_id}/download`：获取短期下载 URL。
- `GET /api/v1/health`、`GET /api/v1/ready`：健康和就绪探针。

前端使用 SSE 订阅 Agent 的任务事件，Agent 内部通过 PostgreSQL 事件表和 RabbitMQ 分发。页面刷新后从数据库补拉事件，不依赖浏览器保持 WebSocket。

## 11. 独立 Docker Compose

### 本地 Compose

独立文件 `hydro_remote_agent/deploy/docker-compose.yml` 应包含：

- `agent`：API、Planner、Executor、WebSocket Hub。
- `nginx`：反向代理、TLS、上传限制和访问日志。
- `postgres`：持久化数据库。
- `redis`：缓存和锁。
- `rabbitmq`：本地消息总线。
- `minio`：对象存储。
- `frontend`：前端静态资源或前端容器。
- `prometheus`、`grafana`：指标和可视化，可按部署规模启用。

### 远程 GPU Compose

远程服务器单独使用 Worker Compose，仅包含：

- `expert-worker`：WebSocket Client、Expert Runtime、Watchdog。
- 可选 `node-exporter` 或 GPU 指标 Exporter。

远程 Compose 通过环境变量配置：`AGENT_WS_URL`、`WORKER_ID`、`WORKER_TOKEN`、`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、模型目录和 GPU 可见设备。两套 Compose 不共享 Docker 网络，通过 IP/DNS、WebSocket 和 MinIO 通信。

## 12. 安全设计

- Worker 使用唯一身份和短期 Token，注册消息使用 HMAC 签名并带时间戳、随机数，防止重放。
- Nginx 强制 HTTPS/WSS；开发环境可使用内网 HTTP，但不得用于生产。
- PostgreSQL、Redis、RabbitMQ、MinIO 管理端口不直接暴露公网。
- MinIO 使用最小权限账号；输入、输出、模型使用不同策略。
- 文件上传限制大小、扩展名和内容类型，下载使用短期 presigned URL。
- 所有任务、状态转换、Worker 操作和异常写入审计事件。
- 密钥只放 `.env`、Docker Secret 或外部 Secret Manager，不提交到代码仓库。
- 使用防火墙仅允许本地 Agent 入口、MinIO 数据端口和必要的管理来源访问。

## 13. 可观测性

指标至少包括：任务创建数、排队时长、步骤执行时长、成功率、重试率、Worker 在线数、WebSocket 重连次数、消息延迟、MinIO 传输耗时、GPU 利用率和显存使用率。

日志采用 JSON 格式，所有日志带 `job_id`、`step_id`、`worker_id`、`attempt` 和 `correlation_id`。应用日志与模型 stdout 分开保存，模型详细日志上传 MinIO 并在数据库登记。

告警包括：无可用 Worker、心跳超时、任务积压、连续失败、GPU OOM、MinIO 空间不足、PostgreSQL 连接池耗尽和 WebSocket 重连异常。

## 14. 完整实施阶段

### 阶段一：基础工程和配置

1. 固化目录结构、环境变量模板和版本号。
2. 定义 `ToolSpec`、`ExpertResult`、资产 Schema 和错误码。
3. 为 PostgreSQL 编写迁移脚本、索引和状态转换约束。
4. 增加配置校验，启动时检查 MinIO、数据库和消息系统连接。

### 阶段二：资产和任务持久化

1. 实现 MinIO Bucket 初始化和最小权限策略。
2. 实现 presigned 上传、SHA-256 校验、资产登记和清理任务。
3. 实现 Job/Step CRUD、幂等键、事件表和审计表。
4. 将当前本地绝对路径输入全面改为 `artifact_id` 协议。

### 阶段三：WebSocket 控制平面

1. 实现 Worker 注册、认证、能力协商和心跳。
2. 实现消息序列号、ACK、发送队列和重连补发。
3. 实现任务下发、进度、完成、失败、取消消息。
4. 实现租约续期、断线恢复、过期回收和重复消息幂等。

### 阶段四：远程 Worker

1. 将 Expert Runtime、真实 Adapter 和模型配置复制到 `hydro_remote_agent`。
2. 实现 Worker 启动自检、GPU 探测、MinIO 下载和结果上传。
3. 实现模型池、按需加载、并发队列、OOM 处理和临时目录清理。
4. 为每个专家增加能力注册、输入校验、输出校验和模型版本记录。

### 阶段五：Workflow 远程化

1. Planner 根据任务类型生成可持久化 Workflow DAG。
2. Executor 将 READY 步骤分配到符合能力和 GPU 条件的 Worker。
3. 实现依赖触发、失败重试、人工取消、部分成功和最终汇总。
4. 增加结果指标聚合、可视化产物和报告生成步骤。

### 阶段六：前端和服务编排

1. 实现任务创建、上传、进度、取消和结果下载页面。
2. 使用 SSE 展示实时状态，断线后按事件序号补拉。
3. 完善独立本地 Compose、远程 Worker Compose、Nginx 和 TLS 配置。
4. 添加数据库备份、MinIO 版本保留和过期对象清理。

### 阶段七：安全、监控和验证

1. 启用 WSS、Worker Token/HMAC、权限策略和防火墙规则。
2. 接入 Prometheus、Grafana、结构化日志和告警。
3. 执行单元测试、Adapter 契约测试、WebSocket 协议测试和故障注入测试。
4. 测试 Worker 断线、Agent 重启、消息重复、任务取消、MinIO 超时和 GPU OOM。
5. 进行长时间压力测试，确认租约、幂等和资源回收无泄漏。

## 15. 部署顺序

### 本地机器

```powershell
cd D:\workspace\HydroGuardian\hydro_remote_agent\deploy
Copy-Item .env.example .env
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f agent
```

将 `.env` 中的本地地址设置为 `agent.example.internal`，确认本地防火墙允许远程 GPU 服务器访问 WebSocket 端口和 MinIO 数据端口。

### 远程 GPU 服务器

```bash
cd /path/to/hydro_remote_agent/deploy
cp .env.example .env
docker compose -f docker-compose.worker.yml config
docker compose -f docker-compose.worker.yml build
docker compose -f docker-compose.worker.yml up -d
docker compose -f docker-compose.worker.yml logs -f expert-worker
```

启动后先确认 Worker 在 Agent 的 Worker 列表中显示为 `ONLINE`，再提交小规模验证任务，最后进行完整数据集任务。

## 16. 验收标准

- API 可以创建任务并通过 MinIO 完成输入上传。
- Worker 可以主动建立 WebSocket 连接并完成认证、注册和心跳。
- 三个已接入专家可以完成真实推理，输出能在 MinIO 下载并在数据库追溯。
- Agent 或 Worker 重启后任务可恢复，不重复产生有效结果。
- 重复消息、断线、租约过期、取消和 GPU OOM 均有确定状态和错误码。
- 前端可以实时查看进度，刷新页面后状态与数据库一致。
- Compose 可独立启动，不引用 HydroGuardian 的网络、容器或卷。
- 监控、日志、审计、备份和权限策略通过上线检查。

## 17. 结论

采用“本地 Agent + 本地中间件 + MinIO 文件中转 + 远程 Worker 主动 WebSocket 连接”的方案，可以在远程 GPU 容器没有入站接口的条件下完成稳定调度。WebSocket 负责低延迟控制消息，MinIO 负责大文件，PostgreSQL 负责可靠状态，Redis 和 RabbitMQ 分别承担短期协调与本地异步处理，四者职责清晰，后续增加专家模型和 GPU Worker 时无需改变前端协议。
