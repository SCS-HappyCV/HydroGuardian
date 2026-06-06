# agent-service MVP 升级清单

本文档用于说明 `agent-service` 当前仍属于 MVP 形态的部分，以及后续应如何升级。当前主链路已经可以跑通：

```text
parse_task -> build_program -> prepare_scene_sample -> execute_3d
-> maybe_detect_change -> assess_risk -> generate_recommendation -> persist_case
```

但“能跑通”不等于“生产级稳定”。下面按模块列出边界、风险和建议升级方向。

## 总览

| 模块 | 当前状态 | MVP 点 | 建议优先级 |
| --- | --- | --- | --- |
| 任务理解 | 已支持 LLM 工具调用和规则回退 | schema、prompt、评测集和观测信息仍偏轻 | P0 |
| Program 构建 | 单候选 field program | 没有多候选、校验、排序和 schema 协商 | P1 |
| 场景样本 | 可从磁盘读样本，缺失时可 demo 回退 | 缺少正式预处理服务和样本校验 | P0 |
| 3D 证据执行 | 调 `/execute` 和 `/compile_evidence` | 单次调用、弱重试、失败证据包较粗 | P0 |
| 变化检测 | temporal 任务按 pre/post 图片调用 | ChangePack 很薄，mask 未落库，阈值硬编码 | P1 |
| 风险评分 | 基于 EvidencePack 的规则加权 | 权重和阈值未校准，缺少业务风险基准 | P1 |
| 建议/工单 | 已拆分 recommendation 和 work order，并由 case-service 生成真实工单 | 状态流转仍是 MVP，缺少 SLA、关闭验收和外部派单系统 | P1 |
| Case 持久化 | 保存摘要到 case-service | 未持久化完整 evidence、trace、artifact | P0 |
| API 返回 | gRPC/网关只返回摘要 | trace/errors/evidence 不对上游暴露 | P0 |
| 可观测性和测试 | 有基础 print 日志和 trace 数组 | 缺少结构化日志、指标、自动化测试 | P0 |

优先级说明：

- `P0`：影响联调、排错、验收稳定性，应优先升级。
- `P1`：影响业务效果和可扩展性，建议在核心链路稳定后升级。
- `P2`：生产治理或体验增强，可在比赛演示版本之后逐步做。

## 1. 任务理解层

相关文件：

- `src/nodes/task.py`
- `src/nodes/task_openai_parser.py`
- `src/nodes/task_rule_parser.py`
- `src/nodes/task_contract.py`

当前已经具备：

- `AGENT_TASK_PARSER_BACKEND=openai/auto/rule` 三种模式。
- OpenAI-compatible 工具调用解析，可接 DashScope/Qwen。
- LLM 失败后可按配置回退到规则解析。
- 日志里能看到 LLM 成功或失败，例如 `task parser llm success source=openai_tool target=ditch`。

MVP 点：

- `task_contract.py` 中的类别、属性、关系词表仍是第一版，覆盖面有限。
- LLM prompt 和工具 schema 没有成体系评测，复杂任务可能被过度简化。
- 规则回退只覆盖常见比赛样例，不能当成完整中文语义解析器。
- 当前只选一个最终 intent，没有保留多个候选解释和置信度。
- 解析结果没有作为独立审计 artifact 持久化，接口返回里也看不到 parser_source、trace、errors。

升级建议：

- 建一份任务理解评测集，覆盖 `class / attribute / relation / no_target / temporal / exclude`。
- 对每条样例保存期望 `target / attributes / relations / negatives / temporal_intent`。
- 给 LLM 输出增加 `confidence`、`reasoning_summary`、`unsupported_terms` 等非敏感诊断字段。
- 允许生成多个 `task_intent_candidates`，再由 program 编译或规则打分选择。
- 将 `parser_source`、LLM 调用耗时、模型名、失败原因写入可查询 trace。

## 2. Program 构建层

相关文件：

- `src/nodes/program.py`
- `src/config.py`

当前已经具备：

- 将 `task_intent` 翻译成 hydro-program3d 可执行的 field schema program。
- 补齐 `target_label_ids / reference_label_ids / negative_label_ids`。

MVP 点：

- 当前只构造一个候选 `c0`。
- `proposal_score` 固定为 `1.0`，没有真实排序含义。
- `evidence` 固定为 `["geometry", "ortho_edge"]`。
- `LABEL_IDS` 在 `config.py` 中硬编码，缺少版本化标签表。
- 对非法组合缺少强校验，例如 target 不在标签表、relation 缺 reference、negative label 不存在。

升级建议：

- 引入 `ProgramBundle` 多候选机制，至少支持 `primary / relaxed / no_target` 三类候选。
- 增加 program schema 校验器，失败时给出可读错误。
- 将标签表外置为版本化配置，例如 `label_schema_v1.json`。
- 与 hydro-program3d 约定 schema version，避免上下游字段漂移。
- 将 program 编译失败和降级路径写入 trace，并返回到调试接口。

## 3. 场景样本层

相关文件：

- `src/nodes/scene.py`
- `src/config.py`

当前已经具备：

- 优先从 `AGENT_SCENE_SAMPLE_DIR` 读取 `{scene_id}.json` 或 `{sample_id}.json`。
- 找不到样本且 `AGENT_ALLOW_DEMO_SAMPLE=true` 时，会生成 demo sample 打通链路。

MVP 点：

- demo sample 是手工构造的小矩阵，只适合联通性测试，不代表真实图像或点云。
- 缺少正式预处理服务，尚未从 file-service 或上游数据流水线拿真实 tensor。
- 缺少 sample schema 校验，字段缺失可能到下游才暴露。
- `scene_id` 和真实数据资产的映射关系不明确。
- pre/post 图片路径仅作为样本字段约定，没有统一资产管理。

升级建议：

- 建立正式 `scene-preprocess-service` 或数据适配节点，输出标准 `SceneTensorSample`。
- 默认生产环境设置 `AGENT_ALLOW_DEMO_SAMPLE=false`。
- 为 sample 加 JSON Schema 或 Pydantic 校验，进入 3D 执行前先失败。
- 给 sample 增加 `source_files / preprocess_version / created_at / checksum`。
- 明确 `scene_id -> sample_id -> file artifacts` 的索引关系。

## 4. 3D 证据执行层

相关文件：

- `src/clients/hydro_program3d.py`
- `src/nodes/evidence.py`
- `src/state.py`

当前已经具备：

- 调用 hydro-program3d `/health`、`/execute`、`/compile_evidence`。
- 保存原始 executor 输出到 `raw_executor_output`。
- 失败时生成 `failure_evidence_pack`，让风险节点降级为人工复核。

MVP 点：

- 只有单次 HTTP 调用，没有重试、退避、熔断和错误分类。
- `/execute` 与 `/compile_evidence` 的契约没有自动化测试保护。
- 失败 EvidencePack 只保存简短 reason，缺少 request_id、下游状态码、耗时和关键输入摘要。
- `HYDRO_PROGRAM3D_CHECKPOINT_NAME` 默认是 demo checkpoint 名称。
- 原始输出、证据包、候选区域和可视化 artifact 未落库。

升级建议：

- 增加有限重试和错误分类：连接失败、超时、4xx 请求错误、5xx 服务错误分开处理。
- 建立 EvidencePack schema 和契约测试。
- 保存 3D 请求摘要、响应摘要、耗时、模型版本、checkpoint、device。
- 将关键 artifact 上传 file-service 或对象存储，并把 artifact id 写入 case。
- 给 `/execute` 和 `/compile_evidence` 增加独立 trace stage，方便定位是哪一步失败。

## 5. 变化检测层

相关文件：

- `src/nodes/change.py`
- `src/clients/change_detection.py`

当前已经具备：

- 只有任务带 `temporal_intent=true` 才触发 change-detection。
- sample 带 `pre_image_path` 和 `post_image_path` 时，会以 multipart 调 `/predict`。

MVP 点：

- 缺少 pre/post 文件存在性、格式、尺寸、坐标对齐校验。
- 阈值 `0.5` 硬编码。
- 成功后只记录 `mask_bytes` 和摘要，mask 本身没有保存为 artifact。
- ChangePack 没有和 EvidencePack 做空间对齐或候选区域融合。
- 缺少变化类型区分，例如新增扰动、消失、扩张、疑似水位变化。

升级建议：

- 将 threshold、变化类型、最小连通域面积做成配置。
- 保存 mask artifact，并返回 `mask_file_id / bbox / changed_area`。
- 与 3D candidate region 做空间匹配，形成融合证据。
- 给变化检测失败增加可解释原因，并区分“跳过”和“失败”。

## 6. 风险评分层

相关文件：

- `src/nodes/risk.py`

当前已经具备：

- 基于 EvidencePack 的 `confidence / verifier / no_target / abstain / relations / attributes` 做规则加权。
- 能输出 `HIGH / MEDIUM / LOW / REVIEW_REQUIRED`。
- 能根据 target 推断基础 `risk_type`。

MVP 点：

- 权重和阈值是手工规则，没有经过样本集校准。
- 不同风险类型共享一套打分公式，业务解释力有限。
- `negative_penalty`、`relation_bonus` 等系数不可配置。
- 只取第一个 candidate region，不能表达 Top-K 风险点。
- 对 evidence 质量的处理较粗，例如 confidence 高但区域很小、no-target 高但 verifier 高等冲突情况。

升级建议：

- 建立验证集，校准阈值和权重。
- 按风险类型拆分评分策略，例如 near-water ditch、road disturbance、steep slope 使用不同规则。
- 将权重放入配置文件，并记录 `score_breakdown`。
- 支持 Top-K risk cards，每个风险卡绑定 region、evidence、artifact。
- 增加人工复核标签回流，用于后续学习式风险评分器。

## 7. 建议和工单层

相关文件：

- `src/nodes/recommendation.py`

当前已经具备：

- 根据风险等级生成 recommendation。
- recommendation 和 work order 已拆成独立节点。
- agent-service 先生成工单草稿，case 落库后调用 case-service 创建真实 `work_order_id`。
- api-gateway 已提供工单查询和状态更新接口。

MVP 点：

- 文案是固定模板，缺少与风险类型、证据摘要、区域信息的细粒度绑定。
- `recommendation_id` 仍是本次执行内的轻量 ID，尚未作为独立数据库对象持久化。
- assignee 仍按风险等级简单推导。
- 工单状态已支持 `TODO / ASSIGNED / IN_PROGRESS / REVIEWED / CLOSED`，但还没有 SLA、关闭验证和外部派单系统。

升级建议：

- 根据 `risk_type / risk_level / candidate_region / evidence_summary` 生成更具体的处置建议。
- 接入外部派单系统或 case-service 的工单表。
- 增加状态流转：`todo -> assigned -> in_progress -> reviewed -> closed`。

## 8. Case 持久化层

相关文件：

- `src/clients/case_file.py`
- `src/grpc_service.py`

当前已经具备：

- 推理结束后调用 case-service `CreateCase`。
- case-service 失败时不会阻断主结果返回，只记录 errors。

MVP 点：

- 当前只保存摘要字段：title、task_text、scene_id、risk_level、assignee、tags。
- tags 是 JSON 字符串，结构化查询能力有限。
- 完整 `task_intent / program / evidence_pack / change_pack / risk_card / recommendation / trace / errors` 未持久化。
- case 持久化失败后，上游只看到空 case 信息，不知道失败原因。
- 缺少幂等键，重复请求会创建多个 case。

升级建议：

- 增加 `case_detail` 或 `agent_result` 表，保存完整链路快照。
- 给 `CreateCase` 增加 idempotency key，例如 `traceId + sceneId + normalized_task`。
- 把 evidence artifact、mask artifact、原始响应摘要关联到 case。
- 在网关调试模式下返回 case 持久化错误。

## 9. API 和返回协议

相关文件：

- `proto/agent.proto`
- `src/grpc_service.py`
- `api-gateway/src/main/proto/agent.proto`
- `api-gateway/src/main/java/com/hydro/gateway/TaskGatewayController.java`

当前已经具备：

- HTTP 网关接收任务，并转 gRPC `ExecuteTask`。
- 返回 `targetType / riskScore / riskLevel / recommendationAction / caseId / caseStatus` 摘要。

MVP 点：

- 返回体没有 `status`、`parser_source`、`trace`、`errors`、`evidence_status`。
- 网关 `traceId` 没有贯穿传入 agent-service 的 `AgentState`。
- gRPC proto 只适合摘要展示，不适合调试和证据回放。
- 缺少异步任务接口，长耗时推理只能阻塞请求。

升级建议：

- 扩展 proto，增加 `execution_status`、`parser_source`、`evidence_status`、`review_required`。
- 增加 debug 模式或单独的 `GetTaskTrace` 接口返回 trace/errors。
- 将网关 `X-Trace-Id` 传给 agent-service，贯穿 case 和日志。
- 对长任务引入异步任务模式：`SubmitTask -> taskId`，再 `GetTaskResult(taskId)`。

## 10. 可观测性和测试

当前已经具备：

- `AgentState.trace` 和 `AgentState.errors`。
- 任务解析成功/失败已有日志。
- Nacos 注册失败有重试日志。

MVP 点：

- 日志主要是 `print`，不是结构化 JSON 日志。
- 没有统一 request_id、trace_id、span_id。
- 没有 Prometheus 指标，例如 LLM 成功率、3D 调用耗时、EvidencePack 成功率。
- 缺少单元测试、契约测试、集成 smoke test。
- 当前测试主要依赖人工 curl 和 Docker Compose 联调。

升级建议：

- 引入结构化日志，字段至少包含 `trace_id / scene_id / parser_source / status / duration_ms`。
- 增加指标：`task_parse_success_total`、`llm_parse_failed_total`、`execute_3d_duration_seconds`、`review_required_total`。
- 增加最小测试集：
  - 任务解析单测。
  - ProgramBuilder 单测。
  - Scene sample schema 校验单测。
  - hydro-program3d client mock 测试。
  - 网关到 agent-service 的 Docker Compose smoke test。

## 11. 部署和配置

相关文件：

- `Dockerfile`
- `requirements.txt`
- `backend/docker-compose.yml`
- `src/config.py`
- `src/discovery.py`

当前已经具备：

- Docker 镜像安装依赖并生成 proto。
- Compose 中传入 OpenAI/DashScope、Nacos、下游服务地址等配置。
- agent-service Nacos 注册失败后会重试。

MVP 点：

- 缺少启动时配置校验，关键配置错误要到请求时才暴露。
- agent-service 没有独立 HTTP health/readiness endpoint。
- Compose 对 agent-service 没有 healthcheck。
- 默认 `AGENT_ALLOW_DEMO_SAMPLE=true` 对生产环境不安全。
- 依赖版本固定但缺少安全扫描和镜像大小优化。

升级建议：

- 启动时打印脱敏后的关键配置，并校验必需项。
- 增加 gRPC health 或 HTTP `/healthz`。
- Compose healthcheck 等待 agent-service 真正注册成功或 gRPC 可连。
- 区分 `dev / demo / prod` 配置模板。
- 生产环境强制关闭 demo sample，缺少真实样本时明确失败。

## 建议升级路线

### P0：先把联调和验收稳定住

1. 扩展返回或新增 debug 接口，让 `trace/errors/parser_source/evidence_status` 可见。
2. 生产或验收环境关闭 `AGENT_ALLOW_DEMO_SAMPLE`，接入真实样本或明确失败。
3. 为任务理解、program 构建、3D client 增加最小自动化测试。
4. 保存完整 agent 执行快照到 case 或文件 artifact。
5. 给 3D 调用增加错误分类、耗时日志、有限重试。

### P1：提升业务效果

1. 建任务理解评测集，持续校准 LLM prompt 和工具 schema。
2. ProgramBuilder 支持多候选和 schema 校验。
3. 风险评分拆分风险类型，并输出 `score_breakdown`。
4. ChangePack 保存 mask artifact，并与 3D candidate region 融合。
5. recommendation 和 work order 继续增强 SLA、关闭验收和外部派单系统。

### P2：走向生产治理

1. 引入异步任务队列，避免长请求阻塞网关。
2. 建结构化日志、指标、链路追踪。
3. 做人工复核闭环，把 case 结论回流到风险评分和任务理解评测集。
4. 建配置中心和模型版本管理，支持多模型灰度。

## 验收标准建议

升级后的 agent-service 至少应满足：

- 同一条任务请求能看到完整 `trace/errors/parser_source/evidence_status`。
- LLM 失败时，能明确区分 key 缺失、网络失败、模型拒绝、schema 解析失败。
- demo sample 关闭后，缺真实样本会给出清晰失败，不会伪造推理结果。
- 3D 服务失败不会导致主链路崩溃，但会留下足够定位的信息。
- 风险分数能解释每一项加分和扣分来源。
- case 中能追溯到任务理解结果、program、evidence、risk、recommendation 和 artifact。

## 接手建议

后续扩展时，优先替换节点内部实现，不要一开始打散整张 LangGraph。当前图的职责边界已经比较清楚，适合按下面顺序演进：

```text
task_contract/task_openai_parser
-> program
-> scene
-> hydro_program3d client
-> risk
-> recommendation/work_order
-> case persistence/API protocol
```
