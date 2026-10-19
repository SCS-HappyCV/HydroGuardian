# HydroGuardian 前端 Agent 展示版实施方案

## 1. 方案定位

本阶段只修改 `web` 前端，不修改 HydroGuardian 后端，也不连接正在开发的 `hydro_remote_agent`。

目标是在无后端服务、无 GPU、无网络的环境中，通过真实页面交互完整展示未来核心 Agent 的产品形态：

```text
自然语言任务
→ Agent 任务理解
→ 决策路由
→ 专家能力协作
→ 多模态证据
→ 质量验证
→ 风险研判
→ 人工复核或工单闭环
```

这是一套前端场景驱动的比赛展示实现，不伪造网络请求，不在浏览器中运行模型，不把模拟数据描述为实时模型结果。

## 2. 界面表达约束

`offline`、`mock`、`离线演示`、`模拟执行`仅作为代码和开发文档内部概念，不写入比赛界面。

界面统一使用：

- 标准场景；
- 智能分析；
- Agent 决策；
- 专家协同；
- 证据生成；
- 质量验证；
- 案例复盘；
- 重新分析。

技术详情中也不显示：

- Mock adapter；
- 本地 JSON；
- 定时器模拟；
- API 失败回退；
- 本地文件系统路径；
- 尚未实现的训练能力。

## 3. 实施目标

### 3.1 比赛目标

评委在 3—5 分钟内能够看懂：

1. Agent 能理解自然语言巡查需求；
2. Agent 会根据任务选择专家工具或组织工作流；
3. 专家工具会生成点云、变化和几何证据；
4. 质量验证会阻止不可靠结果直接流转；
5. 风险可以进入人工复核和处置工单。

### 3.2 前端目标

- 不发起任何业务 API 请求；
- 所有核心图像、图标和附件均来自构建产物；
- 页面刷新、前进和返回后状态连续；
- 一键恢复比赛初始状态；
- 同一案例在任务、执行、风险、工单和回放页面保持一致；
- 后续接真实 Agent 时保留组件，只替换数据提供者。

### 3.3 本阶段不做

- 不实现真实 Agent Planner；
- 不执行真实分割或变化检测模型；
- 不实现真实文件上传和预处理；
- 不修改 API Gateway、agent-service 或数据库；
- 不实现 SSE、WebSocket 或远程任务队列；
- 不增加新的后台管理页面。

## 4. 总体技术架构

前端增加一个本地 Agent 场景运行层：

```text
Demo Scenario
     ↓
Local Agent Runtime
     ↓
Agent Presentation Snapshot
     ↓
Presentation Adapter
     ↓
现有 Vue 页面与新增 Agent 组件
     ↓
localStorage 状态仓库
```

核心原则是“页面与数据来源解耦”：

```ts
interface AgentPresentationProvider {
  createTask(input: AgentTaskInput): Promise<AgentPresentationSnapshot>
  getSnapshot(taskId: string): AgentPresentationSnapshot | undefined
  advance(taskId: string): AgentPresentationSnapshot
  resetScenario(scenarioId: string): void
}
```

当前阶段实现 `LocalAgentPresentationProvider`。将来接入真实 Agent 时增加 `ApiAgentPresentationProvider`，页面组件不重写。

## 5. 场景设计

## 5.1 主比赛场景：近水扰动与疑似沟渠筛查

任务：

> 筛查近水扰动区域，重点识别细长沟渠并排除道路，按风险高低排序。

Agent 决策：

```text
workflow
```

执行步骤：

1. 解析目标、空间约束与排除条件；
2. 检查正射影像、点云和前后时相资产；
3. 点云语义分析定位水体、岸坡和道路；
4. 几何关系分析筛选近水细长区域；
5. 时相变化检测识别新增扰动；
6. 结果质量验证；
7. 生成 EvidencePack 和风险结果；
8. 生成处置建议与工单草稿。

预设结果：

- 一个高风险对象：证据充分，可生成工单；
- 一个待复核对象：点云几何与影像变化存在冲突；
- 一个被排除对象：道路特征明显，不进入风险列表。

主场景必须贯穿：

```text
taskId
caseId
sceneId
riskId
artifactId
workorderId
```

## 5.2 辅助场景一：请求补充信息

任务：

> 看一下这里最近有没有异常。

Agent 决策：

```text
clarification
```

页面展示：

- 需要明确“这里”对应的场景范围；
- 需要选择异常类型或使用综合筛查；
- 用户选择建议项后可重新生成任务计划；
- 不进入虚假的专家执行流程。

## 5.3 辅助场景二：数据条件不足

任务：

> 判断该岸段是否出现了新增施工扰动。

场景仅包含当前影像，缺少前时相影像。

Agent 决策：

```text
abstain
```

页面展示：

- 当前条件不足以完成可靠的时相变化判断；
- 缺少前时相影像；
- 建议补充数据或转人工核验；
- 可进入待复核记录，但不生成高置信风险。

## 5.4 辅助场景三：单工具分析

任务：

> 统计候选沟渠距离水线的最近距离。

Agent 决策：

```text
tool_call
```

仅显示“空间几何关系分析”节点，不显示完整八阶段流程。

## 5.5 辅助场景四：直接回答

任务：

> 当前标准场景包含哪些可用于研判的数据？

Agent 决策：

```text
direct_answer
```

展示场景资产摘要及支持的分析能力，不进入执行监控。

## 6. 数据结构

## 6.1 场景定义

```ts
interface AgentDemoScenario {
  scenarioId: string
  title: string
  taskText: string
  decisionType:
    | 'direct_answer'
    | 'tool_call'
    | 'workflow'
    | 'clarification'
    | 'abstain'
  taskInput: AgentTaskInput
  snapshots: AgentPresentationSnapshot[]
  assets: AgentArtifactView[]
  finalRoute: string
}
```

每个场景包含一组按时间顺序排列的快照，不在组件中散落硬编码进度和文案。

## 6.2 展示快照

沿用 V2 方案的统一协议：

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
```

本地场景和未来 API 必须返回相同结构。

## 6.3 时间线快照

主场景建议准备 10 个确定性快照：

| 序号 | 时间 | 状态 |
| --- | ---: | --- |
| 0 | 0ms | 任务已创建 |
| 1 | 500ms | Agent 正在理解任务 |
| 2 | 1200ms | 已选择组合工作流 |
| 3 | 2000ms | 场景资产检查完成 |
| 4 | 3000ms | 点云语义结果生成 |
| 5 | 4100ms | 几何分析结果生成 |
| 6 | 5200ms | 变化检测结果生成 |
| 7 | 6300ms | 质量验证完成 |
| 8 | 7200ms | 风险和建议生成 |
| 9 | 8000ms | 工单草稿完成 |

时间可在配置中整体使用 `0.5x / 1x / 1.5x` 倍速，不能用随机进度。

## 7. 本地 Agent 运行层

## 7.1 状态机

新增确定性状态机：

```text
idle
→ preparing
→ running
→ completed

clarification_required
abstained
review_required
failed
```

要求：

- 每次运行产生完全一致的结果；
- 暂停后可继续；
- 刷新页面后从持久化位置恢复；
- 返回任务页再进入时不会重复启动多个定时器；
- 页面卸载时清理定时器；
- 终态不会继续推进。

## 7.2 运行控制

提供：

- `startScenario(scenarioId)`；
- `pauseScenario(taskId)`；
- `resumeScenario(taskId)`；
- `seekScenario(taskId, stepIndex)`；
- `completeScenario(taskId)`；
- `resetScenario(scenarioId)`；
- `getCurrentSnapshot(taskId)`。

比赛主路径默认自动播放；历史回放使用同一组快照但改为手动或倍速播放。

## 7.3 本地持久化

新增统一状态：

```ts
interface AgentDemoSession {
  version: 1
  scenarioId: string
  taskId: string
  currentStep: number
  status: string
  playbackRate: number
  startedAt?: string
  updatedAt: string
}
```

建议存储键：

```text
hydroguardian_agent_demo_session
hydroguardian_agent_presentation_snapshots
hydroguardian_demo_business_state
```

业务状态包含：

- 当前风险复核状态；
- 已生成的工单；
- 现场反馈；
- 复核结论；
- 闭环时间线。

## 7.4 状态恢复

页面挂载时：

1. 读取 session；
2. 校验版本和 scenarioId；
3. 恢复当前快照；
4. 只有状态为 `running` 时才重新建立一个定时器；
5. 已完成、待澄清或已拒答状态不自动重跑。

## 8. 页面实施

## 8.1 首页

改造范围较小：

- 主按钮进入主比赛场景；
- 次按钮进入任务工作台；
- 文案强调“自主选择专家能力并组织分析流程”；
- 增加“一键重置案例”入口；
- 不显示运行模式。

## 8.2 发起巡查

### 改造

- 标准场景默认选中；
- 提供五个预设任务卡；
- 输入内容与场景匹配时选择对应场景剧本；
- 自定义输入无法命中时使用“综合分析”主剧本，不生成任意模型结果；
- 增加 Agent 决策预检卡；
- 保留自然语言到结构化任务的编译效果。

### 文件上传

纯前端阶段不做真实分析：

- 允许选择文件并展示文件名、类型、大小和本地预览；
- 明确提示“已加入当前任务数据”；
- 不声称文件已经完成模型处理；
- 页面刷新后文件对象无法恢复时提示重新选择；
- 主比赛案例始终使用内置场景资产。

## 8.3 智能执行

### 改造

- 用 `DynamicWorkflowGraph` 替代主展示区的固定八阶段图；
- 固定图保留为旧场景兼容；
- 增加 Agent 决策说明；
- 节点状态由快照驱动；
- 实时证据流由 artifact 出现时间驱动；
- 增加暂停、继续和直接完成控制，默认放进演示控制区；
- 技术日志根据快照生成，不再在组件中拼接随机内容。

### 执行完成

- `workflow` 和 `tool_call` 跳转风险研判；
- `direct_answer` 在当前页显示回答；
- `clarification` 返回任务输入区域并保留上下文；
- `abstain` 显示安全停止卡和后续建议；
- `review_required` 仍属于有效终态，不显示为执行失败。

## 8.4 风险研判

### 改造

- 风险数据统一来自主场景 final snapshot；
- 增加质量门控卡；
- 增加来源链；
- 风险、证据图层和产物使用同一 ID 联动；
- 被道路规则排除的候选区域可在“分析说明”中展示，但不进入风险列表；
- 待复核对象明确显示证据冲突位置。

### 视觉资产

至少本地准备：

- 正射影像或高质量场景底图；
- 点云投影/点云示意；
- 前时相影像；
- 后时相影像；
- 变化掩码；
- 风险轮廓；
- 现场反馈照片；
- 用户头像占位图。

所有文件进入项目构建产物，禁止核心路径引用外网 URL。

## 8.5 处置闭环

继续使用现有本地工单服务：

- 高风险对象生成工单；
- 现场反馈更新本地业务状态；
- 人工复核形成结论；
- 关闭后更新风险和工单时间线；
- 返回上级页面时确保弹窗遮罩完全销毁；
- 一键重置时恢复初始工单和复核状态。

## 8.6 案例复盘

- 复用主场景快照；
- 支持播放、暂停、倍速和拖动步骤；
- 按真实场景节点显示 Agent 决策和产物生成；
- 可切换到风险结果和工单闭环；
- 导出功能仅导出本地结构化摘要或 CSV。

## 9. 建议新增文件

```text
src/lib/agent-presentation-types.ts
src/lib/agent-presentation-adapter.ts
src/lib/local-agent-runtime.ts
src/lib/local-agent-storage.ts
src/lib/agent-scenario-matcher.ts
src/lib/agent-capability-catalog.ts

src/data/agent-demo/scenarios.ts
src/data/agent-demo/workflow-case.ts
src/data/agent-demo/tool-case.ts
src/data/agent-demo/clarification-case.ts
src/data/agent-demo/abstain-case.ts
src/data/agent-demo/direct-answer-case.ts
src/data/agent-demo/assets.ts

src/components/agent/AgentDecisionCard.vue
src/components/agent/AgentResponsePanel.vue
src/components/agent/DynamicWorkflowGraph.vue
src/components/agent/WorkflowStepCard.vue
src/components/agent/ArtifactFeed.vue
src/components/agent/QualityGateCard.vue
src/components/agent/AgentSourceChain.vue
src/components/agent/DemoPlaybackControls.vue

src/assets/demo/*
```

## 10. 优先修改文件

```text
src/lib/runtime-mode.ts
src/lib/competition-demo-reset.ts
src/lib/api-contracts.ts

src/data/CompetitionDemoData.ts
src/data/TaskExecutionSnapshotService.ts

src/components/task_studio/TaskStudioContent.vue
src/components/task_studio/IntentCompilerPreview.vue
src/components/task_studio/SceneAssetPanel.vue

src/components/task_execution_monitor/TaskExecutionMonitor.vue
src/components/task_execution_monitor/AgentWorkflowGraph.vue
src/components/task_execution_monitor/LiveEvidenceFeed.vue

src/components/risk_workspace/RiskWorkspaceContent.vue
src/components/risk_workspace/RiskDetailCard.vue
src/components/risk_workspace/MultiModalEvidenceCanvas.vue
src/components/risk_workspace/EvidenceMetricsPanel.vue

src/components/history_playback/HistoryPlaybackContent.vue
src/components/workorder_detail/*
```

## 11. 静态资源本地化

当前源码中仍有外部头像和工单附件 URL。本阶段需要：

1. 搜索所有 `http://` 和 `https://`；
2. 核心演示资源全部替换为 `src/assets/demo` 中的本地文件；
3. PDF、Word 等非必要附件改为本地缩略卡，不依赖在线下载；
4. 登录头像和用户头像提供本地 SVG/PNG；
5. API 配置页可以保留示例地址，但比赛模式默认不进入；
6. 构建后断网检查所有页面，不允许出现破图。

不建议把大型原始点云放入网页包。点云页面使用经过抽样压缩的 JSON、二进制数据或可交互的轻量可视化数据。

## 12. 分阶段实施计划

## P0：离线运行底座（1—2 天）

### 任务

- 定义 Agent Presentation 类型；
- 建立五类场景数据；
- 实现本地 Provider、状态机和存储；
- 将运行模式固定为标准场景；
- 扩展一键重置；
- 清理核心路径中的 API 调用入口。

### 验收

- 关闭所有后端服务后可创建并运行任务；
- 页面不发起业务 API 请求；
- 刷新执行页后状态可恢复；
- 重复进入页面不会启动多个执行定时器；
- 界面不出现 `Mock` 或“离线演示”字样。

## P1：Agent 决策与动态执行（2—3 天）

### 任务

- 增加决策预检和决策说明卡；
- 实现动态工作流；
- 实现五类 Agent 行为；
- 证据流改为快照驱动；
- 增加确定性播放控制；
- 保留旧固定流程作为兼容。

### 验收

- 五个预设任务进入正确的决策状态；
- 单工具任务不展示无关专家；
- 澄清和拒答不显示为系统错误；
- 主工作流按配置稳定完成；
- 所有节点、耗时和产物每次运行一致。

## P2：证据、质量和风险联动（2—3 天）

### 任务

- 本地化所有核心场景资产；
- 增加质量门控卡和来源链；
- 建立风险、区域和产物 ID 联动；
- 展示高风险、待复核和被排除区域；
- 完善多模态画布切换。

### 验收

- 断网后所有核心图片正常；
- 点击风险能够联动影像、点云和变化图层；
- 质量验证结果和风险状态一致；
- 待复核对象能说明证据冲突；
- 不展示浏览器本地文件路径。

## P3：业务闭环与历史回放（1—2 天）

### 任务

- 工单生成接入本地 Agent 结果；
- 现场反馈、人工复核和关闭状态统一持久化；
- 历史回放复用 Agent 快照；
- 增加倍速、拖动和快速完成；
- 修复页面返回后的弹窗遮罩和交互锁定风险。

### 验收

- 从风险生成工单后可以完成整个闭环；
- 页面前进、返回和刷新后仍可操作；
- 不出现透明遮罩残留；
- 历史回放内容与主任务一致；
- 重置后所有业务状态恢复。

## P4：资源审计与比赛彩排（1 天）

### 任务

- 清理外部资源依赖；
- 检查所有空状态和失败状态；
- 完成静态构建；
- 使用本地静态服务器断网运行；
- 检查三种比赛分辨率；
- 按 3—5 分钟脚本彩排。

### 验收

- `pnpm check` 通过；
- `pnpm build` 通过；
- 关闭网络和后端后主流程完整；
- 控制台无阻断错误和持续网络重试；
- 从首页到闭环不超过 8 次主要点击；
- 1280×720 投影环境下核心信息完整。

## 13. 比赛演示脚本

### 主路径

1. 首页说明自然语言驱动和专家协同；
2. 进入标准场景并展示巡查任务；
3. 展示 Agent 识别目标、近水约束和排除道路；
4. 启动分析，观察动态专家工作流；
5. 看到点云、几何和变化证据依次生成；
6. 质量验证将一个对象转入人工复核；
7. 进入风险研判并切换多模态画布；
8. 对高风险对象生成工单；
9. 展示现场反馈和复核关闭。

### 安全能力补充

主路径结束后可用 20—30 秒快速展示：

- 信息不清时 Agent 主动追问；
- 数据不足时 Agent 不强行输出；
- 单一问题只调用必要工具。

## 14. 测试方案

### 14.1 单元测试

- 场景匹配；
- 状态机推进；
- 暂停和恢复；
- session 版本迁移；
- 五类决策映射；
- 质量状态映射；
- 重置逻辑。

### 14.2 组件测试

- 动态工作流的单节点、串行、跳过和失败；
- Agent 回答、澄清和拒答；
- 质量门控四种状态；
- 图像资源失败兜底；
- 风险与来源链联动；
- 弹窗关闭后遮罩销毁。

### 14.3 手工检查

```text
断网启动
→ 创建任务
→ 执行中刷新
→ 返回任务页
→ 再进入执行页
→ 风险研判
→ 工单详情
→ 现场反馈
→ 人工复核
→ 返回主页
→ 一键重置
```

每一步均应可点击且状态一致。

## 15. 风险控制

| 风险 | 控制方式 |
| --- | --- |
| 演示数据散落在组件 | 统一放入场景与快照文件 |
| 定时器导致返回后页面锁死 | 单实例 runtime、卸载清理、终态停止 |
| `localStorage` 脏数据污染演示 | schema version、一键重置、解析失败回退 |
| 外部图片断网失效 | 核心资源全部本地化 |
| 页面宣称超过真实 Agent 能力 | 文案基于已规划能力，未上线能力不出现 |
| 后续接 API 需要重写 | Provider 接口和统一 Presentation Snapshot |
| 自定义输入产生不可信结果 | 使用有限场景匹配和综合分析兜底，不自由生成结论 |
| 静态 HTML 直接打开存在模块限制 | 使用 `pnpm preview` 或便携本地静态服务器运行 |

## 16. 交付物

完成后应交付：

- 五类 Agent 决策场景；
- 一条完整比赛主案例；
- 本地 Agent 状态机；
- 动态专家工作流；
- 多模态证据与质量门控；
- 本地风险、复核和工单闭环；
- 历史回放；
- 一键重置；
- 全部本地化核心资产；
- 静态构建产物；
- 比赛操作脚本和断网检查清单。

## 17. 工期与推荐顺序

预计工作量为 7—11 个开发日：

```text
P0 离线运行底座
→ P1 Agent 决策与动态执行
→ P2 证据、质量和风险联动
→ P3 业务闭环与历史回放
→ P4 资源审计与比赛彩排
```

第一批建议先完成 P0。P0 完成后，网页端将拥有统一的本地 Agent 数据源和稳定状态恢复机制，后续页面改造以及未来真实 Agent 接入都可以建立在同一协议上。
