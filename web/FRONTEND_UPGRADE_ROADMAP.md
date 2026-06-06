# HydroGuardian 前端升级路线

本文档面向 `web` 前端从“静态演示控制台”升级为“可联调、可演示、可逐步生产化的业务前端”。当前重点不是重做 UI，而是把已有页面稳妥接入后端闭环：

```text
文件上传
-> 场景预处理 / manifest 注册
-> 自然语言任务执行
-> 证据、风险、建议、工单展示
-> 复核闭环
```

## 1. 当前状态

### 1.1 技术状态

- 前端目录：`D:\py_project\HydroGuardian\web`
- 技术栈：Astro 5 + Vue 3 + Tailwind CSS + reka-ui + TypeScript
- 构建模式：`output: "static"`
- 默认 API 地址：`.env` 中的 `VITE_API_BASE_URL=http://localhost:8080`
- 当前 `pnpm build` 可以成功构建，产出 20 个静态页面。

### 1.2 页面状态

已有页面覆盖较完整的比赛演示框架：

- `dashboard.html`：全局总览
- `task-studio.html`：任务工作坊
- `task-execution-monitor.html`：任务执行监控
- `risk-workspace.html`：风险分析工作区
- `workorder-center.html` / `workorder-detail.html` / `workorder-review.html`：工单闭环
- `history*.html`：历史回溯与对比
- `knowledge.html` / `template-editor.html` / `rule-editor.html`：知识与规则管理
- `settings.html` / `system-health.html` / `user-perm-management.html`：系统管理

### 1.3 数据状态

当前业务主数据仍以 mock/localStorage 为主：

- `src/data/*Service.ts` 提供本地查询和保存。
- `task-studio` 创建任务时只写入本地 `TaskService`。
- `task-execution-monitor` 使用模拟进度和模拟日志。
- `risk-workspace` 读取本地 `RiskEventService`。
- `workorder-*` 页面读取本地工单、证据和复核数据。

已经具备的 API 基础：

- `src/lib/http-client.ts`：统一 HTTP 客户端、trace id、鉴权头、超时、错误封装。
- `src/lib/api-contracts.ts`：API 常量和部分类型。
- `src/lib/auth-api.ts`：登录/注册 API 封装。

### 1.4 已知构建警告

`pnpm build` 可通过，但有几个需要后续处理的警告：

- `src/components/ui/select/index.ts` re-export 导致 Rollup circular chunk warning。
- `caniuse-lite` / `baseline-browser-mapping` 数据偏旧。
- 部分 chunk 较大，后续真实 API 接入后需要关注首屏加载。

## 2. 升级目标

### 2.1 MVP 联调目标

前端能够完整跑通一条真实后端链路：

```text
上传正射图和点云
-> 调用 /api/v1/scenes/preprocess
-> 调用 /api/v1/tasks/execute
-> 展示 task intent / evidence status / risk summary / trace / case status
-> 进入风险工作区
-> 查看工单或创建复核动作
```

### 2.2 比赛演示目标

演示时前端应能清楚表达 HydroGuardian 的核心价值：

- 自然语言任务被编译成可执行巡查任务。
- 三模态证据服务返回结构化 `EvidencePack`。
- 风险结果不是单纯 mask，而是可解释、可排序、可复核的业务对象。
- 工单闭环能够承接风险结果。
- 失败、低置信度、no-target、review-required 都有清晰状态展示。

### 2.3 工程目标

- 不推倒现有页面。
- 保留 mock 模式，方便无后端环境演示 UI。
- 新增 API 模式，支持真实联调。
- 通过统一 service/adaptor 层映射后端响应，避免组件直接拼后端字段。

## 3. 后端接口基线

当前 `api-gateway` 已暴露的主要接口：

| 能力 | 方法与路径 | 前端用途 |
| --- | --- | --- |
| 登录 | `POST /api/v1/auth/login` | 登录页 |
| 注册 | `POST /api/v1/auth/register` | 注册页 |
| 文件上传 | `POST /api/v1/files` | 上传图像、点云、样本 JSON |
| 文件查询 | `GET /api/v1/files/{fileId}` | 文件元数据回显 |
| 场景预处理 | `POST /api/v1/scenes/preprocess` | 图像 + 点云 -> SceneTensorSample |
| 注册 manifest | `POST /api/v1/scenes/{sceneId}/manifest` | 外部样本绑定 sceneId |
| 查询 manifest | `GET /api/v1/scenes/{sceneId}/manifest` | 场景资产状态 |
| 执行任务 | `POST /api/v1/tasks/execute` | 主智能体链路 |
| 查询工单 | `GET /api/v1/work-orders/{workOrderId}` | 工单详情 |
| 查询 case 工单 | `GET /api/v1/cases/{caseId}/work-orders` | case 关联工单列表 |
| 更新工单状态 | `PATCH /api/v1/work-orders/{workOrderId}/status` | 复核状态流转 |

需要注意：`/api/v1/tasks/execute` 当前返回的是摘要和诊断字段，不一定包含完整 `EvidencePack`、`RiskCard`、`RecommendationCard`、`WorkOrderCard`。完整快照落在 case-service 的 `case_agent_result.agent_result_json`。因此前端若要做完整风险卡和证据链展示，可能需要后端补一个 case agent-result 查询接口，或扩展 `tasks/execute` 响应。

## 4. 总体改造策略

### 4.1 保留现有页面结构

现有 UI 已经覆盖比赛叙事，不建议大改页面骨架。升级重点放在：

- 数据来源从 mock 切到 API。
- 页面状态从“模拟”切到“真实执行结果”。
- 风险和工单对象从本地假数据切到后端 case 快照。

### 4.2 增加 API Service 层

建议新增：

```text
src/api/
|- file-api.ts
|- scene-api.ts
|- task-api.ts
|- workorder-api.ts
|- case-api.ts
`- mappers.ts
```

职责划分：

- `*-api.ts` 只处理 HTTP 调用和接口类型。
- `mappers.ts` 负责后端 DTO 到前端现有数据模型的转换。
- 组件继续优先消费前端友好的 `TaskData`、`RiskEventData`、`WorkorderData`。

### 4.3 增加数据模式开关

建议新增环境变量：

```text
VITE_DATA_MODE=mock | api | hybrid
```

- `mock`：完全使用当前本地数据，适合无后端演示。
- `api`：真实调用后端，失败直接展示错误。
- `hybrid`：优先调用后端，失败时允许回退 mock，适合比赛现场兜底。

## 5. 阶段路线

## P0：稳定当前前端基线

目标：保证前端作为静态演示系统稳定可构建、可打开、可导航。

任务：

- 修复 `ui/select` circular chunk warning。
- 增加 `pnpm check` 或类型检查脚本。
- 确认所有页面入口和侧边栏链接有效。
- 保留 `placeholder.html` 兜底，但记录哪些链接仍然是占位。
- 清理不必要的大 chunk 或至少记录 chunk 来源。

验收：

- `pnpm build` 通过。
- 关键页面在本地开发服务中可打开。
- 无阻断级构建警告。

## P1：补齐 API 契约和请求封装

目标：先完成接口层，不急着改页面。

任务：

- 在 `api-contracts.ts` 中补齐业务 API 路径：
  - files
  - scenes preprocess / manifest
  - tasks execute
  - work-orders
  - cases agent result，若后端补接口
- 新增 `file-api.ts`：
  - `uploadFile(file, fileType)`
  - `getFile(fileId)`
- 新增 `scene-api.ts`：
  - `preprocessScene(payload)`
  - `createSceneManifest(sceneId, payload)`
  - `getSceneManifest(sceneId)`
- 新增 `task-api.ts`：
  - `executeTask({ taskText, sceneId, debug })`
- 新增 `workorder-api.ts`：
  - `getWorkOrder(id)`
  - `getCaseWorkOrders(caseId)`
  - `updateWorkOrderStatus(id, payload)`
- 新增统一错误展示工具，将 `ApiError` 映射成 toast、页面错误块和调试详情。

验收：

- 每个 API 封装有明确 TypeScript 类型。
- 能在独立调试函数或临时页面中完成接口冒烟。
- 后端不可用时错误信息可读，不出现空白页。

## P2：任务工作坊接入真实链路

目标：`task-studio.html` 从本地创建任务升级为真实发起执行。

当前状态：

- 用户输入任务文本、区域、优先级、sampleId。
- 点击执行后写入本地 `TaskService`，再跳转监控页。

升级任务：

- 增加“数据来源”区域：
  - 已有 `sceneId`
  - 上传正射图
  - 上传点云
  - 可选上传前后时相图像
  - 已有 `sceneSampleFileId` 高级模式
- 支持两条路径：
  - 真实预处理：上传文件 -> `/api/v1/scenes/preprocess`
  - 已有样本：注册 manifest -> `/api/v1/scenes/{sceneId}/manifest`
- 点击执行时调用 `/api/v1/tasks/execute`。
- 将返回结果保存为前端任务执行快照：
  - taskText
  - sceneId
  - targetType
  - parserSource
  - evidenceStatus
  - riskScore / riskLevel
  - reviewRequired
  - caseId / caseStatus
  - trace / errors
  - casePersistenceStatus
- 跳转到 `task-execution-monitor.html?taskId=...`，用本地 taskId 关联这次执行快照。

验收：

- 可通过页面上传文件并完成 preprocess。
- 可通过页面执行 `近水细长沟渠，并排除道路` 类任务。
- 后端返回失败时，页面展示失败阶段、错误信息和 traceId。
- 后端返回 `REVIEW_REQUIRED` 时，页面不把它渲染成“系统异常”。

## P3：执行监控页从模拟改为真实回放

目标：`task-execution-monitor.html` 展示真实执行结果和 trace。

当前状态：

- 页面用 `setInterval` 模拟进度。
- 日志来自本地 `TaskLogService`。

升级任务：

- 对同步执行模式做结果回放：
  - 如果 `tasks/execute` 已返回，按 trace 阶段渲染时间线。
  - progress 根据 trace 阶段映射，而不是随机增长。
- 建立阶段映射：

```text
parse_task -> 任务解析
build_program -> Program 构建
prepare_scene_sample -> 场景样本准备
execute_3d.discovery -> 3D 服务发现
execute_3d.health -> 3D 服务健康检查
execute_3d.execute -> 3D Program 执行
execute_3d.compile_evidence / compile_evidence -> 证据编译
maybe_detect_change -> 变化检测
assess_risk -> 风险研判
generate_recommendation -> 建议和工单生成
persist_case -> case 持久化
```

- 将 errors 独立渲染为诊断面板。
- 保留“模拟执行”仅作为 mock 模式。
- 后续如果后端提供异步任务或 SSE/WebSocket，再改为真实轮询/流式日志。

验收：

- 执行监控页能复现一次真实任务的完整 trace。
- 用户能从该页跳转到风险工作区或系统健康页。
- 失败任务能清楚看到失败阶段。

## P4：风险工作区接入 Evidence/Risk 真实数据

目标：`risk-workspace.html` 从 mock 风险列表升级为真实风险结果展示。

当前状态：

- `RiskWorkspaceContent.vue` 读取 `RiskEventService.getAll()`。
- 地图和风险详情均使用 mock 风险对象。

前端任务：

- 定义后端结果到 `RiskEventData` 的映射：
  - `RiskCard.risk_type` -> risk type/name
  - `RiskCard.risk_level` -> level
  - `RiskCard.risk_score` -> score
  - `RiskCard.trigger_evidence` -> evidence summary
  - `RiskCard.candidate_region_id` -> region id
  - `EvidencePack.candidate_regions[0].centroid/bbox` -> 地图定位和区域摘要
  - `EvidencePack.review_required` -> status
- 展示 `EvidencePack` 关键字段：
  - confidence
  - selectedVerifierScore
  - posteriorNoTargetMass
  - abstainProbability
  - candidateRegions
  - evidenceSummary
- 若后端还没有完整 case 快照查询接口，先用 `tasks/execute` 摘要生成一张“主风险卡”。

后端依赖建议：

- 新增 `GET /api/v1/cases/{caseId}/agent-result`。
- 或扩展 `POST /api/v1/tasks/execute` 的 `data`，返回完整 `riskCards`、`recommendationCards`、`workOrders`、`evidencePack`。

验收：

- 风险工作区能打开指定 task/case 的真实风险结果。
- `REVIEW_REQUIRED`、`LOW`、`MEDIUM`、`HIGH` 显示一致。
- 证据不足时页面展示为“待复核”，而不是空数据。

## P5：工单闭环接入真实 work-order API

目标：工单中心和复核页使用 case-service 的真实工单数据。

当前状态：

- 工单中心、详情、复核页都从本地 service 读取。

升级任务：

- `workorder-center.html`：
  - 支持按 `caseId` 查询 `/api/v1/cases/{caseId}/work-orders`。
  - 支持按 `riskId` 从本地/快照生成工单上下文。
- `workorder-detail.html`：
  - 查询 `/api/v1/work-orders/{workOrderId}`。
  - 展示风险类型、风险等级、建议动作、证据摘要。
- `workorder-review.html`：
  - 提交复核状态到 `PATCH /api/v1/work-orders/{workOrderId}/status`。
  - 本地附件上传仍可先保留为 mock；后续接 file-service。

验收：

- 从风险页进入工单页能看到真实工单。
- 工单状态能从 `todo` 更新为 `doing/review/closed`。
- 状态更新失败时有可读错误和重试入口。

## P6：Dashboard / History / System Health 升级

目标：让全局页面从静态数据变成真实系统状态入口。

Dashboard：

- 短期：从本地执行快照和 case/workorder API 聚合统计。
- 中期：后端提供聚合接口，如风险数量、待复核数量、最近任务、工单状态分布。

History：

- 短期：展示本地缓存的执行记录。
- 中期：接入 case 列表和 agent result 快照。
- 长期：接入多时相变化结果和历史复核记录。

System Health：

- 短期：前端主动请求关键 API 做轻量健康检测。
- 中期：后端提供统一健康接口，聚合 api-gateway、agent-service、case-service、file-service、hydro-program3d、change-detection。

验收：

- 首页统计和任务执行结果一致。
- 历史页能回放曾经执行过的任务。
- 系统健康页能帮助定位后端不可用、3D 服务不可用、case 持久化失败等问题。

## P7：比赛演示打磨

目标：让演示过程稳定、清楚、有冲击力。

任务：

- 准备 2-3 个固定 demo 场景：
  - 近水细长沟渠并排除道路
  - 高于水线的陡坡异常区
  - 坝体附近结构扰动区
- 增加“一键填充 demo”能力，避免现场手输。
- 任务执行结果页面突出：
  - program 编译结果
  - EvidencePack
  - 风险触发证据
  - 工单状态
- 对后端不可用准备友好降级：
  - mock 模式
  - 最近一次成功结果回放
  - 明确的系统健康提示
- 增加演示脚本文档：
  - 启动后端
  - 启动前端
  - 上传数据
  - 执行任务
  - 查看风险
  - 生成工单
  - 复核闭环

验收：

- 比赛现场 5 分钟内能完整演示闭环。
- 网络或 GPU 服务失败时仍能解释系统状态，不会尴尬空白。
- 观众能看懂“不是普通分割，而是证据到风险到闭环”的差异。

## 6. 页面/API 对接矩阵

| 页面 | 当前数据源 | 目标数据源 | 优先级 |
| --- | --- | --- | --- |
| 登录注册 | `auth-api` 部分接入 | `/api/v1/auth/*` | P1 |
| 任务工作坊 | `TaskService` mock | files + scenes + tasks API | P2 |
| 执行监控 | 模拟进度和日志 | `tasks/execute` trace/errors | P3 |
| 风险工作区 | `RiskEventService` mock | task result / case agent result | P4 |
| 工单中心 | `WorkorderService` mock | case work-orders API | P5 |
| 工单详情 | mock | work-order detail API | P5 |
| 工单复核 | mock + localStorage draft | work-order status API | P5 |
| Dashboard | mock 聚合 | case/task/workorder 聚合 | P6 |
| History | mock | case/agent-result 历史 | P6 |
| System Health | mock | 健康检测 API | P6 |
| Knowledge/Rules/Templates | mock | 后续知识库 API | P7+ |

## 7. 建议目录结构

```text
src/
|- api/
|  |- auth-api.ts          # 可从 src/lib/auth-api.ts 迁移或保留转发
|  |- file-api.ts
|  |- scene-api.ts
|  |- task-api.ts
|  |- workorder-api.ts
|  |- case-api.ts
|  `- mappers.ts
|- data/
|  |- mock/                # 后续可逐步整理 mock 数据
|  `- *.Service.ts         # 可保留现有接口，内部按 data mode 切换
|- lib/
|  |- api-contracts.ts
|  |- http-client.ts
|  `- runtime-mode.ts
`- components/
```

## 8. 类型和映射建议

后端 `ExecuteTask` 摘要建议映射为前端执行快照：

```ts
interface TaskExecutionSnapshot {
  localTaskId: string
  taskText: string
  sceneId: string
  targetType: string
  parserSource: string
  evidenceStatus: string
  riskScore: number
  riskLevel: string
  reviewRequired: boolean
  recommendationAction: string
  caseId: string
  caseStatus: string
  executionStatus: string
  traceTotal: number
  errorCount: number
  trace: AgentTraceItem[]
  errors: AgentErrorItem[]
  casePersistenceStatus: string
  casePersistenceError: string
  createdAt: string
}
```

当后端提供完整快照后，再补充：

```ts
interface AgentResultSnapshot {
  schemaVersion: string
  taskIntent: unknown
  programBundle: unknown
  selectedProgram: unknown
  evidencePack: unknown
  changePack?: unknown
  riskCards: unknown[]
  recommendationCards: unknown[]
  workOrders: unknown[]
  trace: AgentTraceItem[]
  errors: AgentErrorItem[]
}
```

## 9. 测试与验收

基础命令：

```bash
cd web
pnpm build
```

建议补充：

```bash
pnpm check
```

联调验收用例：

1. 后端未启动，打开前端，页面不崩溃，显示可读错误。
2. 上传图像和点云，成功拿到 `sceneSampleFileId`。
3. 执行任务，成功拿到风险等级、caseId、trace。
4. 3D 服务不可用，任务结果显示 `REVIEW_REQUIRED` 或结构化失败信息。
5. 从任务结果进入风险工作区，能看到风险摘要。
6. 从风险工作区进入工单中心，能看到工单并更新状态。
7. 刷新页面后，本地执行快照仍可回放。

## 10. 推荐实施顺序

第一周：

- P0 构建警告和基础检查。
- P1 API service 层。
- P2 任务工作坊最短真实链路。

第二周：

- P3 执行监控真实 trace 回放。
- P4 风险工作区接真实任务结果。

第三周：

- P5 工单闭环。
- P6 Dashboard/History/SystemHealth 的关键真实数据。

第四周：

- P7 比赛演示打磨、demo 数据、降级预案、演示脚本。

## 11. 最小下一步

建议从下面 4 个文件开始：

1. `src/lib/api-contracts.ts`：补齐业务 API path 和 DTO 类型。
2. `src/api/task-api.ts`：封装 `/api/v1/tasks/execute`。
3. `src/api/scene-api.ts`：封装 `/api/v1/scenes/preprocess` 和 manifest。
4. `src/components/task_studio/TaskStudioContent.vue`：把“立即执行”从本地 mock 改成可选 API 模式。

这样最快能把前端从“看起来完整”推进到“能跑真实智能体闭环”的状态。
