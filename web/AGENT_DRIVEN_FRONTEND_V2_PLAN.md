# HydroGuardian 核心 Agent 驱动前端 V2 改造方案

## 1. 改造背景

HydroGuardian 网页端已经完成第一轮比赛化改造，当前具备：

- 自然语言巡查任务创建；
- AI 意图编译预览；
- 多阶段执行过程展示；
- 正射影像、点云、变化检测与风险区域联动；
- 风险解释、人工复核、处置建议和工单闭环；
- 比赛案例、历史回放与离线展示保障。

后续核心能力将逐步迁移到 `hydro_remote_agent`。该 Agent 不再只是固定执行一条分析链，而是会根据任务和资产情况选择：

```text
直接回答 direct_answer
工具调用 tool_call
组合工作流 workflow
请求澄清 clarification
谨慎拒答 abstain
```

因此 V2 改造不重做现有视觉框架，重点是让前端能够稳定承接动态 Agent 决策、专家工具执行、质量验证和业务结果，同时避免 Agent 内部模型、工具或训练方式变化时反复修改页面。

## 2. 总体目标

### 2.1 比赛展示目标

评委应能在一次 3—5 分钟演示中看懂：

1. Agent 理解了什么任务；
2. Agent 为什么选择当前处理方式；
3. Agent 调用了哪些水利遥感专家能力；
4. 每一步产生了什么证据；
5. 系统如何验证结果是否可靠；
6. 结果如何进入风险研判、人工复核和工单闭环。

### 2.2 工程目标

- 前端只依赖稳定展示协议，不直接依赖 Agent 内部 Python 对象；
- 同时兼容当前 LangGraph 固定链路和未来 `AgentAction` 动态工作流；
- 新旧快照可以在历史页面正常回放；
- 未完成或未启用的工具不会导致页面空白或报错；
- 比赛样例与真实接口使用同一套展示组件；
- 页面不暴露服务器文件路径、模型路径或内部异常栈。

### 2.3 不在本轮范围内

- 不在浏览器中执行模型推理；
- 不直接展示 SFT、GRPO 等训练过程；
- 不承诺尚未上线的语言引导点云分割或真实在线多模态融合；
- 不推倒重做首页、风险工作区和工单系统；
- 不让前端自行解释底层模型原始输出。

## 3. 设计原则

### 3.1 稳定协议优先

页面消费 `AgentPresentationSnapshot`，不直接消费 `AgentAction`、`ExpertResult` 或任意模型响应。后端负责把不同版本 Agent 结果转换为统一快照。

### 3.2 动态流程优先

现有固定八阶段流程保留为旧协议和比赛案例兜底。新协议到达后，执行页根据实际步骤动态生成节点，不虚构未发生的过程。

### 3.3 证据与结论分离

前端明确区分：

- Agent 决策；
- 专家计算结果；
- 质量验证结论；
- 业务风险结论；
- 人工复核结果。

避免把“模型置信度”直接表述成“风险概率”。

### 3.4 能力状态真实

工具在能力面板中使用 `available / degraded / unavailable / mock` 状态。比赛主界面只重点展示真实可用能力，模拟或未启用能力进入技术详情。

### 3.5 渐进兼容

每项改造都必须有旧数据降级路径，不能要求核心 Agent 全部完成后网页端才能运行。

## 4. 目标信息架构

现有导航结构继续保留：

```text
智巡总览
→ 发起巡查
→ 智能执行
→ 风险研判
→ 处置闭环
→ 案例复盘
```

本轮在页面内部增加五个 Agent 展示层：

| 展示层 | 核心问题 | 主要页面 |
| --- | --- | --- |
| 任务理解 | Agent 听懂了什么 | 发起巡查 |
| 决策路由 | Agent 为什么这样处理 | 发起巡查、智能执行 |
| 专家执行 | 调用了什么能力 | 智能执行 |
| 质量门控 | 结果是否可信 | 智能执行、风险研判 |
| 业务闭环 | 结果如何被采用 | 风险研判、处置闭环 |

## 5. 页面改造设计

## 5.1 发起巡查：增加 Agent 决策预检

### 保留

- 三步式任务创建；
- 自然语言输入；
- 场景资产选择；
- 当前意图编译预览；
- 高级设置折叠区。

### 新增

在用户点击执行前增加“Agent 预检”区域：

- 任务目标：识别对象或需要回答的问题；
- 已提供资产：正射影像、点云、前后时相影像；
- 缺少资产：说明哪个能力无法运行；
- 推荐处理模式：直接回答、专家工具或组合工作流；
- 计划调用能力：只展示计划，不伪装为已经执行；
- 安全提示：是否可能需要澄清或人工复核。

### 五类决策的界面行为

| 决策 | 页面行为 |
| --- | --- |
| `direct_answer` | 不进入长流程，展示回答及依据，可保存为任务记录 |
| `tool_call` | 展示单个专家卡，执行后进入结果页 |
| `workflow` | 进入动态工作流执行页 |
| `clarification` | 保留当前表单，突出一个明确问题和建议选项 |
| `abstain` | 展示无法可靠处理的原因、缺失条件和可执行的下一步 |

### 比赛展示文案

界面不直接把英文枚举作为主标题，转换为：

- 已具备直接研判条件；
- 将调用单项专家能力；
- 将执行多专家协同分析；
- 需要补充任务信息；
- 当前条件不足，建议补采或人工复核。

## 5.2 智能执行：从固定流程升级为动态工作流

### 当前问题

现有 `AgentWorkflowGraph` 固定显示八个节点。接入新 Agent 后，不同任务可能只执行一个工具，也可能执行多步工作流，继续固定显示会造成能力虚构。

### 目标布局

顶部：Agent 决策摘要。

- 本次处理模式；
- 决策原因；
- 输入资产完整度；
- 当前总体状态；
- 总耗时。

中部：动态专家工作流。

- 每个实际步骤生成一个节点；
- 节点之间显示依赖关系；
- 并行步骤可并排展示；
- 自动质量验证显示为独立门控节点；
- 跳过步骤显示原因，不标记为失败；
- 失败步骤显示可恢复建议。

右侧或下方：实时产物流。

- 点云分割掩码；
- 变化检测掩码；
- 几何关系统计；
- 质量验证报告；
- EvidencePack；
- 风险卡和工单草稿。

### 专家节点展示字段

每个节点只展示稳定业务字段：

```text
步骤名称
专家能力
输入摘要
状态
耗时
核心结果
置信/质量状态
产物数量
警告
```

模型名称、适配器名称、GPU、checkpoint 和原始参数放入“技术详情”抽屉。

### 动态流程兼容策略

```text
存在 presentation.workflow.steps
→ 使用动态步骤

不存在动态步骤但存在旧 trace
→ 使用当前八阶段 mapper

两者均不存在
→ 展示任务状态与结果摘要，不生成虚假节点
```

## 5.3 新增 Agent 决策说明卡

在任务执行页增加 `AgentDecisionCard`：

- 用户原始问题；
- 规范化目标；
- 选择的动作类型；
- 选择原因；
- 使用的工具；
- 未选择能力及原因；
- 是否触发澄清、拒答或复核。

该卡只展示后端提供的可公开解释文本，不要求前端生成或展示模型思维链。

## 5.4 新增专家能力状态面板

增加 `ExpertCapabilityPanel`，建议放在智能执行页技术详情和系统健康页：

| 能力 | 展示名称 | 当前状态 |
| --- | --- | --- |
| `point_semantic_segmentation` | 点云语义分割 | 可用性由后端返回 |
| `image_change_detection` | 前后时相变化检测 | 可用性由后端返回 |
| `language_guided_point_segmentation` | 语言引导点云定位 | 未真实上线时不进入主演示 |
| `geometry_relation_analysis` | 空间几何关系分析 | 可用性由后端返回 |
| `result_quality_verification` | 结果质量验证 | 可用性由后端返回 |

状态文案：

- `available`：能力可用；
- `degraded`：能力受限，系统已降级；
- `unavailable`：暂不可用；
- `mock`：仅在技术详情显示“验证环境”，主演示不展示。

## 5.5 风险研判：增加质量门控与来源追踪

### 保留

- 风险候选列表；
- 多模态证据画布；
- 点云、正射影像、前后对比和掩码；
- EvidencePack 指标；
- 风险详情和工单入口。

### 新增质量验证卡

新增 `QualityGateCard`：

- 验证结果：通过、有限通过、需复核、不可用；
- 数据完整性；
- 掩码有效性；
- 点数与区域规模；
- 置信度；
- 模型不确定性；
- 警告列表；
- 推荐动作。

### 结果来源追踪

风险详情增加“来源链”：

```text
候选区域
→ 点云/变化/几何专家产物
→ 质量验证
→ EvidencePack
→ 风险卡
→ 建议或工单
```

点击任一来源可联动到对应画布图层，但默认不显示内部文件路径。

### 复核状态统一

全站统一四种业务状态：

- 证据充分，可流转；
- 证据有限，谨慎采用；
- 证据冲突，建议复核；
- 条件不足，无法可靠研判。

禁止仅凭一个置信度阈值在前端自行决定复核状态。

## 5.6 直接回答、澄清和拒答结果页

为了覆盖 Agent 的完整行为，增加轻量结果组件 `AgentResponsePanel`，不新增独立路由：

### 直接回答

- 回答正文；
- 使用的场景信息或证据摘要；
- 回答可信状态；
- 保存记录或继续发起分析。

### 请求澄清

- 一个主要澄清问题；
- 2—4 个后端建议选项；
- 保留原任务和已选资产；
- 用户补充后重新提交，不创建重复任务。

### 谨慎拒答

- 明确说明当前无法可靠完成；
- 显示原因分类：缺少数据、能力不支持、质量不足或参数冲突；
- 提供补采数据、修改任务或转人工复核的按钮；
- 拒答记录进入历史回放，体现 Agent 安全能力。

## 5.7 案例复盘：支持动态 Agent 轨迹

历史回放页升级为协议版本感知：

- 显示当时的 Agent 版本和展示协议版本；
- 回放实际决策类型和专家步骤；
- 支持查看步骤产物、警告和质量门控；
- 旧快照继续通过固定阶段映射展示；
- 新旧任务对比时重点比较决策、证据、质量和业务结果，不比较内部 checkpoint。

## 5.8 首页与总览的小幅调整

现有首页无需重构，只调整能力表达：

- “固定多智能体流程”改为“自主选择专家能力并组织工作流”；
- 能力指标从固定 Agent 数量改为“五类专家能力”或不显示数量；
- 总览增加“自动完成 / 待澄清 / 待复核 / 主动停止”任务分布；
- 不展示尚未上线能力的夸张描述。

## 6. 前后端展示协议

## 6.1 协议边界

推荐由 HydroGuardian `agent-service` 提供展示快照：

```text
hydro_remote_agent 原始结果
→ HydroAgentBridge
→ Result/Evidence Compiler
→ AgentPresentationSnapshot
→ API Gateway
→ Web Adapter
→ Vue 组件
```

Web 不直接读取：

- Python dataclass；
- 本地文件系统路径；
- checkpoint 路径；
- 未规范化的工具输出；
- Agent 内部推理文本；
- 任意结构的 `dataJson`。

## 6.2 推荐协议结构

```ts
interface AgentPresentationSnapshot {
  schemaVersion: 'agent-presentation.v2'
  task: AgentTaskView
  decision: AgentDecisionView
  capabilities: AgentCapabilityView[]
  workflow?: AgentWorkflowView
  response?: AgentResponseView
  evidence: AgentEvidenceView
  quality: AgentQualityView
  business: AgentBusinessView
  trace: AgentTraceView[]
  errors: AgentDisplayError[]
  createdAt: string
}

type AgentDecisionType =
  | 'direct_answer'
  | 'tool_call'
  | 'workflow'
  | 'clarification'
  | 'abstain'

interface AgentDecisionView {
  type: AgentDecisionType
  title: string
  summary: string
  reasonCode?: string
  selectedTools: string[]
  missingInputs: string[]
  reviewRequired: boolean
}

interface AgentWorkflowStepView {
  stepId: string
  title: string
  capabilityId: string
  dependsOn: string[]
  status: 'pending' | 'running' | 'completed' | 'skipped' | 'failed'
  summary: string
  durationMs?: number
  artifactRefs: string[]
  warnings: string[]
}

interface AgentQualityView {
  verdict: 'passed' | 'limited' | 'review_required' | 'unavailable'
  confidence?: number
  uncertainty?: number
  checks: Array<{
    id: string
    label: string
    status: 'passed' | 'warning' | 'failed' | 'unknown'
    summary: string
  }>
  warnings: string[]
  recommendedAction?: string
}
```

## 6.3 资产协议

所有可视化资产统一使用文件服务引用：

```ts
interface AgentArtifactView {
  artifactId: string
  role: string
  mediaType: string
  fileId?: string
  previewUrl?: string
  downloadUrl?: string
  coordinateMode?: string
  metadata?: Record<string, unknown>
}
```

要求：

- 后端本地路径不得返回网页端；
- URL 由文件服务或网关生成；
- 每个产物具有稳定 `artifactId`；
- 区域、风险卡和产物通过 ID 关联；
- 预览失败时显示业务空状态，而不是破图。

## 6.4 错误协议

错误按用户可处理性分类：

```text
INPUT_REQUIRED      需要补充任务或资产
CAPABILITY_OFFLINE  专家能力不可用
QUALITY_REJECTED    质量验证未通过
EXECUTION_FAILED    执行失败
ARTIFACT_MISSING    结果产物缺失
PERSIST_FAILED      业务结果保存失败
```

每个错误必须包含：

- 用户可读标题；
- 简短说明；
- 是否可重试；
- 建议动作；
- 技术追踪 ID。

内部异常栈只进入服务日志。

## 6.5 协议兼容

新增 `agent-presentation-adapter.ts`：

```text
agent_result_snapshot.v1
→ LegacySnapshotAdapter
→ AgentPresentationViewModel

agent-presentation.v2
→ V2SnapshotAdapter
→ AgentPresentationViewModel
```

Vue 组件只接收 `AgentPresentationViewModel`。当后端协议继续升级时，只修改 adapter 和类型，不修改核心页面。

## 7. 前端组件与文件改造

## 7.1 建议新增

```text
src/lib/agent-presentation-types.ts
src/lib/agent-presentation-adapter.ts
src/lib/agent-capability-catalog.ts
src/lib/agent-quality-mapper.ts

src/components/agent/AgentDecisionCard.vue
src/components/agent/AgentResponsePanel.vue
src/components/agent/DynamicWorkflowGraph.vue
src/components/agent/WorkflowStepCard.vue
src/components/agent/ExpertCapabilityPanel.vue
src/components/agent/QualityGateCard.vue
src/components/agent/ArtifactFeed.vue
src/components/agent/AgentSourceChain.vue
```

## 7.2 优先修改

```text
src/lib/api-contracts.ts
src/lib/agent-stage-mapper.ts
src/api/mappers.ts
src/api/agent-result-visualization.ts

src/components/task_studio/IntentCompilerPreview.vue
src/components/task_studio/TaskStudioContent.vue

src/components/task_execution_monitor/TaskExecutionMonitor.vue
src/components/task_execution_monitor/AgentWorkflowGraph.vue
src/components/task_execution_monitor/LiveEvidenceFeed.vue

src/components/risk_workspace/RiskWorkspaceContent.vue
src/components/risk_workspace/EvidenceMetricsPanel.vue
src/components/risk_workspace/RiskDetailCard.vue
src/components/risk_workspace/MultiModalEvidenceCanvas.vue

src/components/history_playback/HistoryPlaybackContent.vue
src/components/dashboard/DashboardContent.vue
```

## 7.3 组件迁移策略

- `AgentWorkflowGraph.vue` 暂不删除，作为旧协议兼容组件；
- 新增 `DynamicWorkflowGraph.vue`，由容器根据协议选择；
- `EvidenceMetricsPanel.vue` 保留现有指标，新 `QualityGateCard.vue` 负责质量结论；
- `RiskDetailCard.vue` 不解析专家结果，只消费编译后的证据和来源链；
- 旧本地演示数据通过 adapter 转换，不复制一套新页面。

## 8. 后端配套改造

前端 V2 能否稳定落地，取决于以下后端能力：

### 8.1 HydroAgentBridge

负责：

- HydroGuardian 任务与场景资产转换为 Agent 输入；
- `AgentAction` 校验与执行；
- 文件 ID 与运行时路径转换；
- 运行产物上传文件服务；
- 统一错误和追踪 ID。

### 8.2 Result/Evidence Compiler

负责：

- 点云掩码转换为候选区域；
- 生成三维包围盒、像素包围盒和多边形；
- 变化区域、几何分析和质量验证聚合；
- 生成 EvidencePack、风险卡和展示快照；
- 映射 Agent 15 类标签与 HydroGuardian 业务风险类型。

### 8.3 Presentation Snapshot Builder

负责：

- 对外生成 `agent-presentation.v2`；
- 过滤内部路径和敏感调试信息；
- 生成业务可读标题、摘要和错误；
- 保存完整快照用于历史回放；
- 保证执行中快照和终态快照结构一致。

### 8.4 执行状态更新

比赛阶段可以先使用轮询；后续再升级 SSE 或 WebSocket：

```text
GET /api/v1/tasks/{taskId}/agent-presentation
```

终态包括：

- `completed`
- `review_required`
- `clarification_required`
- `abstained`
- `failed`

其中 `review_required`、`clarification_required` 和 `abstained` 不应在前端统一显示成“执行失败”。

## 9. 分阶段实施计划

## P0：协议与兼容底座（1—2 天）

### 任务

- 定义 `AgentPresentationSnapshot` TypeScript 类型；
- 建立统一 `AgentPresentationViewModel`；
- 实现 v1 和 v2 两套 adapter；
- 建立能力、状态、错误和质量文案字典；
- 为五种 Agent 决策准备标准演示快照。

### 验收

- 当前网页数据经过 adapter 后展示不变；
- v2 示例快照无需改页面即可解析；
- 未知工具、未知字段和缺失可选字段不会导致页面崩溃；
- 页面中不出现本地文件路径。

## P1：动态决策与工作流（2—3 天）

### 任务

- 增加 Agent 决策说明卡；
- 增加五类动作对应的页面状态；
- 实现动态工作流与依赖线；
- 增加 `skipped`、`clarification`、`abstain` 状态样式；
- 改造实时产物流；
- 保留固定八阶段兼容路径。

### 验收

- 单工具任务只显示真实执行节点；
- 多工具任务正确显示先后依赖和质量验证；
- 澄清、拒答不会显示成系统异常；
- 旧比赛案例仍可完整执行和回放。

## P2：质量门控与证据来源（2—3 天）

### 任务

- 新增质量验证卡；
- 增加风险来源链；
- 建立产物 ID 与候选区域、风险卡的联动；
- 统一复核和不确定性文案；
- 在风险画布中增加专家产物图层状态。

### 验收

- 每个风险能追溯到至少一个专家产物；
- 质量结论与后端 verifier 一致；
- 缺失证据会给出明确降级说明；
- 前端不自行改变后端复核结论。

## P3：能力状态与历史回放（1—2 天）

### 任务

- 增加专家能力状态面板；
- 系统健康页接入专家 health 信息；
- 历史回放支持 v1/v2 协议；
- 增加 Agent 版本和协议版本；
- 更新历史对比维度。

### 验收

- 能力降级或不可用时页面状态明确；
- 未上线能力不进入主演示叙事；
- 新旧案例均能回放；
- 回放内容与任务当时的快照一致，不读取当前实时能力状态。

## P4：联调、演示数据与稳定性（1—2 天）

### 任务

- 接入真实 Presentation Snapshot API；
- 准备五种决策类型的本地兜底快照；
- 完成加载、空数据、超时、失败和重试状态；
- 检查 1280×720、1440×900、1920×1080；
- 完成比赛演示脚本和彩排；
- 校准所有能力文案与真实实现。

### 验收

- 后端正常、缓慢和不可用三种情况下页面均可解释；
- 主比赛案例 3—5 分钟内完成演示；
- 页面刷新后恢复任务和执行状态；
- 无阻断错误、死链和遮罩层残留；
- `pnpm check` 与 `pnpm build` 通过。

## 10. 推荐比赛主案例

继续使用“近水扰动与疑似沟渠筛查”，但将叙事升级为动态 Agent：

```text
用户提出自然语言任务
→ Agent 判断需要组合工作流
→ 点云语义分割定位水体与道路
→ 几何分析筛选近水、细长候选区域
→ 变化检测判断是否为新增扰动
→ 质量验证发现一个证据冲突区域
→ 输出一个高风险对象和一个待复核对象
→ 高风险对象生成工单
→ 待复核对象进入人工复核
```

这一案例能够同时展示：

- 自主决策；
- 专家协同；
- 多源证据；
- 质量验证；
- 主动保守；
- 业务闭环。

备用短案例：

1. 资产不足，Agent 请求补充前时相影像；
2. 查询当前场景支持哪些分析，Agent 直接回答；
3. 点云质量不足，Agent 拒绝强行输出并建议补采。

## 11. 测试方案

### 11.1 单元测试

- v1/v2 adapter；
- 决策类型映射；
- 工作流拓扑与状态；
- 质量状态映射；
- 错误分类；
- 缺失字段和未知工具降级。

### 11.2 组件测试

- 五类 `AgentResponsePanel` 状态；
- 动态工作流的单步、串行、并行、跳过和失败；
- 质量卡四种结论；
- 产物加载失败；
- 风险与来源链联动。

### 11.3 端到端检查

```text
发起任务
→ Agent 决策
→ 动态执行
→ 风险研判
→ 人工复核/工单
→ 历史回放
```

覆盖：

- 在线接口；
- 本地比赛快照；
- 接口超时；
- 页面刷新；
- 浏览器返回；
- 重复进入弹窗或详情页；
- 移动端窄屏只做基本可用，比赛桌面端优先。

## 12. 风险与控制

| 风险 | 控制措施 |
| --- | --- |
| Agent 协议持续变化 | 通过展示协议和 adapter 隔离 |
| 工具数量或名称变化 | 使用 capability catalog 和未知工具兜底 |
| 模型结果不能直接绘制 | 由 Result Compiler 生成统一可视化产物 |
| 实时执行时间过长 | 显示真实阶段、耗时和已产生证据，保留本地案例 |
| 能力未上线却被页面宣传 | 所有能力文案由状态和功能开关控制 |
| 质量指标含义混乱 | 区分模型置信、质量验证和业务风险 |
| 旧历史数据失效 | 保存 schemaVersion 并保留 v1 adapter |
| 服务端路径泄露 | 文件服务引用和快照过滤双重控制 |

## 13. 总体验收标准

### 展示

- 评委可以看懂 Agent 为什么选择当前动作；
- 实际调用的专家能力和执行关系清晰；
- 每个结论能够追溯到证据和质量验证；
- 澄清、拒答和人工复核被表达为安全能力；
- 不展示超出真实实现范围的能力。

### 工程

- 新旧协议共存；
- Agent 工具增减不要求重构页面；
- 组件不解析原始模型输出；
- 所有资产通过文件服务访问；
- 刷新、返回和历史回放状态连续；
- 核心页面构建和类型检查通过。

### 比赛

- 主案例 3—5 分钟讲完；
- 最多 8 次主要点击完成任务到工单；
- 后端不可用时可切换到结构一致的本地快照；
- 现场不出现 Mock、内部路径、异常栈或未实现能力提示；
- 投影环境下核心结论、工作流和风险区域清晰可读。

## 14. 推荐实施顺序

```text
P0 展示协议与 adapter
→ P1 动态决策和工作流
→ P2 质量门控与证据来源
→ P3 能力状态和历史回放
→ P4 真接口联调与比赛彩排
```

预计总工作量为 7—12 个开发日。建议先完成 P0 和 P1，再等待核心 Agent 输出协议稳定；这样既能立刻提升网页端的 Agent 表达，也不会因为底层模型继续完善而重复返工。
