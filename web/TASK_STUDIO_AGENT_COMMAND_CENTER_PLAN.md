# HydroGuardian 发起巡查页 Agent 指挥台改造方案

## 1. 改造定位

将现有“发起巡查”三步表单重构为一屏式 **Agent 任务指挥台**。

页面不再以“填写参数并提交任务”为核心，而是完整展示：

```text
用户描述水利问题
→ Agent 理解目标与约束
→ 检查场景数据条件
→ 选择处理方式与专家能力
→ 用户确认启动
```

本轮仍只修改 `web` 前端，继续使用已经完成的：

- `AgentPresentationSnapshot` 展示协议；
- 五类 Agent 决策场景；
- `LocalAgentRuntime`；
- `localStorage` 会话与快照恢复；
- 当前真实 API 和混合模式代码。

本轮主要改变页面信息架构、交互和视觉，不重写数据底座。

## 2. 比赛展示目标

评委进入页面后 10 秒内应理解：

1. 用户可以直接用自然语言提出水利巡查要求；
2. Agent 会理解目标、空间关系、排除条件和输出要求；
3. Agent 会检查当前场景是否具备所需影像与点云数据；
4. Agent 会自主选择直接回答、单工具或多专家工作流；
5. 数据或任务条件不足时，Agent 会澄清或谨慎停止；
6. 用户确认的是一套可解释的分析计划，而不是黑盒按钮。

页面核心价值主张：

> 用自然语言下达巡查任务，由 Agent 自主组织水利遥感专家能力。

## 3. 改造原则

### 3.1 自然语言为第一入口

输入任务必须是页面第一视觉焦点。模板、样例、参数和文件上传都不能与任务输入争夺主视觉。

### 3.2 场景数据可见

场景不能只表现为 `Scene ID` 和上传控件，而应显示影像缩略图、点云覆盖、时相完整度和巡查边界。

### 3.3 决策过程可解释

只展示结构化理解和选择理由，不展示模型思维链、原始 Prompt 或内部 JSON。

### 3.4 计划与结果分离

任务启动前统一使用：

- Agent 任务理解；
- 建议分析计划；
- 计划调用；
- 预计产物。

禁止在尚未执行时使用“分析完成”“已发现风险”等结果文案。

### 3.5 单一主操作

页面任何状态下只保留一个主按钮：

- 启动智能分析；
- 执行空间计算；
- 查看场景回答；
- 补充任务信息；
- 检查当前条件。

### 3.6 比赛界面不暴露实现模式

比赛模式不显示：

- Mock、API、Hybrid；
- Scene ID、File ID；
- 本地 JSON、定时器、数据回退；
- 模型路径、checkpoint；
- “离线演示”等字样。

## 4. 目标页面结构

## 4.1 桌面比赛布局

推荐页面内容区控制在一屏或轻微纵向滚动：

```text
┌──────────────────────────────────────────────────────────────────┐
│ 发起智能巡查           当前场景：滨河岸段 A01      数据 4/4 就绪 │
├────────────────────────────────┬─────────────────────────────────┤
│ 任务对话区                      │ 场景数据舱                       │
│                                │                                 │
│ 告诉 Agent 你想检查什么         │ 正射影像主预览                   │
│ ┌────────────────────────────┐ │ 风险巡查范围叠加                 │
│ │ 筛查近水扰动区域……         │ │                                 │
│ └────────────────────────────┘ │ 影像 · 点云 · 前时相 · 后时相   │
│ 决策示例 / 历史任务             │ 数据完整度与支持能力             │
├────────────────────────────────┴─────────────────────────────────┤
│ Agent 任务理解：目标 / 空间关系 / 几何约束 / 排除项 / 输出目标   │
├──────────────────────────────────────────────────────────────────┤
│ 建议分析计划：任务理解 → 专家节点 → 质量验证 → 风险结果           │
│                                               [启动智能分析]      │
└──────────────────────────────────────────────────────────────────┘
```

推荐比例：

- 上半区任务输入：55%；
- 上半区场景数据舱：45%；
- 下半区任务理解和分析计划：通栏；
- 页面主内容最大宽度：1600px；
- 1280×720 时允许下半区轻微滚动，但主按钮必须可快速看见。

## 4.2 页面层级

第一层：任务与场景。

第二层：Agent 理解与决策。

第三层：分析计划与启动操作。

参数和上传作为第四层技术操作，默认折叠。

## 5. 模块详细设计

## 5.1 顶部任务状态栏

替代当前三步进度条。

展示：

- 页面标题：发起智能巡查；
- 一句价值说明；
- 当前场景名称；
- 数据完整度；
- Agent 状态：等待任务、理解中、计划就绪、需要补充、条件不足；
- 更换场景；
- 重置任务。

不再显示“01、02、03”固定步骤，因为 Agent 决策并不总是线性三步。

## 5.2 任务对话区

### 主输入

将当前 `TaskInputSection` 改造成大尺寸任务输入组件：

- 标题：“告诉 Agent 你想检查什么”；
- 输入高度 150—190px；
- 支持多行自然语言；
- 支持粘贴巡查通知或检查要求；
- 显示字符数，但不作为主信息；
- 输入时实时更新任务理解和决策预检；
- 500ms 防抖，避免每个字符引起大量视图变化。

推荐占位文案：

> 例如：筛查近水扰动区域，重点识别细长沟渠并排除道路，结合前后时相变化按风险高低排序。

### 快捷动作

输入框下方提供：

- 决策示例；
- 最近任务；
- 清空；
- 语音入口视觉预留；
- 从巡查要求导入视觉预留。

语音和文档解析当前没有真实能力时，仅保留可扩展位置，不做不可用按钮。

## 5.3 决策示例

现有五张大卡改为紧凑的横向示例条或弹出面板。

示例只是帮助体验不同 Agent 行为，不作为任务能力分类：

| 示例 | 对应决策 |
| --- | --- |
| 近水扰动综合筛查 | 多专家工作流 |
| 候选沟渠近水距离 | 单工具调用 |
| 当前场景数据查询 | 直接回答 |
| 模糊巡查要求 | 请求澄清 |
| 时相数据不足 | 谨慎停止 |

每项显示：

- 一句用户任务；
- 小型决策标签；
- 点击后回填任务；
- 不使用“仅支持五类”等限制性表达。

当用户开始自定义输入后，示例区自动收起为“查看决策示例”。

## 5.4 场景数据舱

替代当前比赛模式下以三个小图标为主的 `SceneAssetPanel`。

### 主视觉

- 正射影像或场景底图；
- 巡查范围边界；
- 水线示意；
- 点云覆盖区域；
- 当前场景名称；
- 拍摄或采集时间。

### 数据资产条

以四个资产状态展示：

- 正射影像；
- 点云；
- 前时相影像；
- 后时相影像。

状态：

- 可用；
- 覆盖不完整；
- 缺失；
- 用户已加入。

### 场景能力提示

根据资产状态计算：

- 可执行语义分析；
- 可执行几何分析；
- 可执行时相变化检测；
- 数据不足，需补充；
- 某项结果可能需要人工复核。

### 场景操作

主界面只保留：

- 更换场景；
- 添加数据。

点击后打开侧边抽屉，复用现有：

- 区域选择；
- 样本选择；
- 文件选择；
- Scene ID；
- 运行模式。

`Scene ID` 和运行模式只在高级设置可见。

## 5.5 Agent 任务理解区

将当前 `IntentCompilerPreview` 中的结构化结果移动到通栏区域，并增强可编辑性。

展示六类语义：

1. 目标对象；
2. 空间关系；
3. 几何条件；
4. 排除条件；
5. 所需证据；
6. 输出目标与安全策略。

示例：

```text
目标对象：近水细长沟渠、新增扰动
空间关系：距水线 30m 内
几何条件：连续、细长、局部高差明显
排除条件：道路、既有硬化带
所需证据：正射影像、点云、前后时相
输出目标：风险排序、证据包、处置建议
安全策略：证据冲突时转人工复核
```

### 可编辑交互

标签支持轻量编辑：

- 距离阈值；
- 排除条件；
- 排序方式；
- 是否启用时相变化；
- 输出是否需要工单建议。

编辑结果写回 `AgentTaskInput` 的前端扩展字段，不修改原始用户任务文本，并在页面标记“已人工调整”。

## 5.6 Agent 决策摘要

现有 `AgentDecisionPreview` 拆为简洁决策摘要，不与任务理解重复。

展示：

- 决策类型；
- 选择理由；
- 当前是否具备执行条件；
- 缺失输入或资产；
- 安全提示。

五种状态：

```text
多专家协同分析
单项专家分析
直接形成回答
需要补充信息
当前条件不足
```

## 5.7 建议分析计划

这是页面最重要的 Agent 展示模块。

### 动态计划图

工作流任务示例：

```text
理解任务
   ↓
检查场景数据
   ↓
点云语义分析 ───→ 空间几何关系分析
   └────────────→ 前后时相变化检测
                         ↓
                    结果质量验证
                         ↓
                    风险与处置建议
```

单工具任务只显示：

```text
理解任务 → 空间几何关系分析 → 返回结果
```

直接回答不显示专家工作流：

```text
读取场景信息 → 形成回答
```

澄清和谨慎停止不生成虚假流程。

### 计划节点字段

- 能力名称；
- 调用原因；
- 输入资产；
- 预计产物；
- 当前可用状态；
- 上下游依赖。

### 计划视觉

- 蓝色：Agent 决策；
- 紫色：点云与空间计算；
- 青色：影像与时相证据；
- 绿色：质量通过；
- 黄色：需要补充；
- 红色只用于真实错误，不用于谨慎停止。

## 5.8 主操作区

主按钮随决策变化：

| 决策 | 主按钮 | 行为 |
| --- | --- | --- |
| `workflow` | 启动智能分析 | 创建本地 Agent 任务并进入执行页 |
| `tool_call` | 执行空间计算 | 创建单工具任务并进入执行页 |
| `direct_answer` | 查看场景回答 | 在当前页面展开回答 |
| `clarification` | 补充任务信息 | 展开内联问题与建议项 |
| `abstain` | 查看补充建议 | 展开缺失条件和后续动作 |

按钮旁只展示必要状态：

- 场景数据完整；
- 预计调用能力数；
- 是否可能需要人工复核。

不显示虚构执行时长。

## 5.9 直接回答、澄清与谨慎停止

### 直接回答

在任务页底部展开回答卡：

- 回答内容；
- 信息来源；
- 支持的下一步操作；
- “转为分析任务”。

### 请求澄清

以内联对话形式只问一个关键问题：

- 问题；
- 2—4 个建议项；
- 自定义补充；
- 保留原始任务和场景；
- 补充后重新规划。

### 谨慎停止

展示：

- 为什么当前不能可靠判断；
- 缺少的数据；
- 未执行的能力；
- 补充数据；
- 改写任务；
- 转人工核验。

安全停止使用黄色/青色安全提示，不使用“执行失败”的红色视觉。

## 6. 页面状态设计

页面应有明确状态机：

```text
empty
→ understanding
→ plan_ready
→ submitting

clarification_required
direct_answer_ready
abstain_ready
```

### `empty`

- 显示大输入框和决策示例；
- 场景数据舱显示默认场景；
- 任务理解和计划区显示引导空状态。

### `understanding`

- 使用 300—600ms 轻量骨架或扫描动画；
- 不随机变化；
- 结束后进入确定的预检结果。

### `plan_ready`

- 展示完整理解、决策和计划；
- 主按钮可用；
- 用户修改任务后重新计算。

### `submitting`

- 锁定重复提交；
- 显示正在创建 Agent 任务；
- 跳转完成前不清空页面状态。

### 其他结果状态

- 直接回答、澄清、谨慎停止留在当前页；
- 页面刷新后从本地快照恢复；
- 修改任务后清除旧结果，但保留场景选择。

## 7. 组件拆分

## 7.1 建议新增组件

```text
src/components/task_studio/AgentCommandHeader.vue
src/components/task_studio/AgentTaskComposer.vue
src/components/task_studio/DecisionExampleStrip.vue
src/components/task_studio/SceneDataCockpit.vue
src/components/task_studio/SceneAssetStatus.vue
src/components/task_studio/SceneSettingsDrawer.vue
src/components/task_studio/TaskUnderstandingBoard.vue
src/components/task_studio/UnderstandingToken.vue
src/components/task_studio/AgentDecisionSummary.vue
src/components/task_studio/ProposedWorkflowGraph.vue
src/components/task_studio/ProposedWorkflowNode.vue
src/components/task_studio/AgentPlanActionBar.vue
src/components/task_studio/InlineAgentResponse.vue
```

## 7.2 现有组件处理

| 现有组件 | 处理方式 |
| --- | --- |
| `TaskStudioContent.vue` | 保留为页面状态和数据编排容器，精简模板 |
| `TaskInputSection.vue` | 升级或由 `AgentTaskComposer` 替代 |
| `AgentScenarioPresets.vue` | 改造为紧凑 `DecisionExampleStrip` |
| `IntentCompilerPreview.vue` | 拆分为任务理解板和底部操作栏 |
| `AgentDecisionPreview.vue` | 改造为决策摘要与内联响应 |
| `SceneAssetPanel.vue` | 主界面替换为场景数据舱，原组件放入抽屉 |
| `TaskParameterPanel.vue` | 移入场景设置抽屉 |
| `TaskTemplateList.vue` | 比赛模式隐藏，业务模式保留 |

## 7.3 容器职责

`TaskStudioContent.vue` 只负责：

- 当前任务文本；
- 当前场景与资产；
- 场景匹配；
- 页面状态；
- `LocalAgentRuntime` / API Provider 选择；
- 任务创建和跳转；
- 历史任务恢复。

组件只接收 ViewModel，不直接读写 `localStorage` 或调用 API。

## 8. 数据流与 ViewModel

## 8.1 数据流

```text
AgentTaskComposer
→ taskText
→ scenario matcher / future planner
→ AgentPresentationSnapshot preview
→ Task Studio ViewModel
→ understanding / decision / proposed workflow / action
```

提交后：

```text
ViewModel
→ LocalAgentRuntime.createTask
→ localStorage session + snapshot
→ workflow/tool 跳转执行页
→ answer/clarification/abstain 留在当前页
```

## 8.2 建议新增 ViewModel

```ts
interface TaskStudioAgentViewModel {
  pageState:
    | 'empty'
    | 'understanding'
    | 'plan_ready'
    | 'submitting'
    | 'direct_answer_ready'
    | 'clarification_required'
    | 'abstain_ready'
  taskText: string
  scene: SceneCockpitView
  understanding: TaskUnderstandingView
  decision: AgentDecisionView
  proposedWorkflow?: AgentWorkflowView
  response?: AgentResponseView
  primaryAction: {
    label: string
    enabled: boolean
    reason?: string
  }
}
```

新增：

```text
src/lib/task-studio-agent-view-model.ts
```

将页面中的多个 `computed` 和状态文案集中管理，避免模板继续膨胀。

## 8.3 计划快照

当前场景的第一个 snapshot 主要表达初始状态，不足以完整表达计划。建议场景数据新增：

```ts
interface AgentDemoScenario {
  ...
  preview: AgentPresentationSnapshot
  timeline: AgentDemoTimelineItem[]
}
```

`preview` 中：

- 所有计划步骤为 `pending`；
- 包含完整 `decision`；
- 包含任务理解和资产要求；
- 不包含执行结果、风险和质量结论。

这样任务页不用从执行时间线猜测计划。

## 8.4 场景资产 ViewModel

```ts
interface SceneCockpitView {
  sceneId: string
  name: string
  location: string
  capturedAt?: string
  previewImage?: string
  boundary?: Array<{ x: number; y: number }>
  assets: Array<{
    role: string
    label: string
    status: 'available' | 'partial' | 'missing' | 'added'
    summary: string
  }>
  completeness: number
  supportedCapabilities: string[]
  warnings: string[]
}
```

纯前端阶段数据来自 `agent-demo/assets.ts`，未来由场景 API 转换为相同 ViewModel。

## 9. 交互细节

## 9.1 输入防抖

- 输入停止 500ms 后更新理解结果；
- 用户持续输入时保持上一版结果并显示“正在重新理解”；
- 不显示随机文本；
- 场景匹配只在防抖后执行。

## 9.2 场景联动

更换场景后：

- 保留任务文本；
- 重新计算资产完整度；
- 重新判断决策；
- 更新建议计划；
- 如果缺少必要资产，主按钮切换为补充信息或查看建议。

## 9.3 用户修改理解结果

手动修改标签后：

- 显示“已人工调整”；
- 更新计划预览；
- 原始自然语言保持不变；
- 提交时将调整项作为结构化覆盖参数保存；
- 一键恢复 Agent 理解结果。

## 9.4 防重复提交

- 提交按钮点击后立即进入 `submitting`；
- 同一任务只允许一个进行中的本地 Runtime；
- 跳转前保存 session；
- 返回任务页时读取原任务，不自动重复启动；
- 修改任务后才允许创建新任务。

## 9.5 响应式

### 1440px 以上

- 输入与场景左右双栏；
- 理解和计划通栏。

### 1024—1439px

- 保持双栏但压缩场景舱高度；
- 计划节点允许横向滚动。

### 768—1023px

- 输入区在上、场景舱在下；
- 理解标签两列；
- 计划改为纵向。

### 小于 768px

- 保证基本可用；
- 比赛展示不以手机网页为重点；
- 主按钮固定在底部安全区域。

## 10. 视觉规范

### 页面主视觉

- 输入区：深蓝透明面板，聚焦边框使用品牌蓝；
- 场景舱：真实影像或高质量场景资产；
- Agent 决策：蓝青渐变；
- 空间计算：紫色；
- 影像变化：青色；
- 质量验证：绿色/黄色；
- 安全停止：黄色，不使用错误红色。

### 动效

保留：

- 输入后任务理解标签依次出现；
- 场景资产状态轻量点亮；
- 建议计划节点依赖线绘制；
- 主按钮状态平滑切换。

避免：

- 无限扫描线；
- 多处脉冲；
- 节点无意义旋转；
- 800ms 以上的大面积入场动画。

### 可访问性

- 所有颜色状态同时提供文字和图标；
- 按钮有清晰焦点状态；
- 计划节点支持键盘浏览；
- 动效尊重 `prefers-reduced-motion`；
- 关键正文最小 12px，比赛主信息不低于 14px。

## 11. 实施阶段

## P0：ViewModel 与计划数据（1—2 天）

### 任务

- 新增 `TaskStudioAgentViewModel`；
- 场景数据增加 `preview`；
- 建立场景资产 ViewModel；
- 将五类决策、主按钮和页面状态映射集中管理；
- 保留现有 Runtime 和 API 分支。

### 验收

- 页面状态不再由模板内多个条件零散判断；
- 五类决策均有正确预检、计划和主按钮；
- 计划快照不包含执行结果；
- 自定义输入仍能匹配最接近场景；
- 刷新后可恢复任务和结果状态。

## P1：任务输入与场景数据舱（2—3 天）

### 任务

- 重构页面上半区；
- 新增大尺寸任务对话区；
- 将决策示例改为紧凑示例条；
- 新增场景图像、边界和资产状态；
- 将参数与上传移动到场景设置抽屉；
- 比赛模式隐藏模板列表和技术字段。

### 验收

- 任务输入是页面第一视觉焦点；
- 场景数据完整度一眼可见；
- 更换场景后任务文本不丢失；
- 核心操作无需接触 Scene ID；
- 1280×720 可看到输入、场景和主要状态。

## P2：任务理解与计划图（2—3 天）

### 任务

- 新增任务理解板；
- 支持部分条件轻量编辑；
- 新增动态建议分析计划；
- 显示专家调用原因、资产和产物；
- 五类决策使用不同计划结构；
- 增加数据不足和能力不可用状态。

### 验收

- 评委能说明 Agent 理解了什么；
- 工作流只展示真正计划调用的能力；
- 直接回答、澄清和停止不显示虚假专家流程；
- 手动调整约束后计划同步变化；
- 页面不展示模型思维链或内部 JSON。

## P3：操作状态与结果交互（1—2 天）

### 任务

- 重构主操作栏；
- 完善直接回答；
- 完善内联澄清；
- 完善谨慎停止建议；
- 加入输入防抖、提交锁和恢复逻辑；
- 删除现有重复意图/决策展示。

### 验收

- 每种状态只有一个主操作；
- 澄清后可重新规划；
- 谨慎停止不显示为失败；
- 连续点击不会创建重复任务；
- 返回、刷新后页面可继续操作。

## P4：视觉、资源与比赛彩排（1—2 天）

### 任务

- 本地化场景主视觉；
- 完善节点动效与响应式布局；
- 检查投影分辨率；
- 检查断网运行；
- 完成五类决策演示；
- 按比赛主案例彩排。

### 验收

- `pnpm check` 通过；
- `pnpm build` 通过；
- 断网和关闭后端后页面完整；
- 无外部核心图片依赖；
- 主案例从输入到执行不超过 3 次主要点击；
- 页面中不出现 Mock、API、离线演示等技术词；
- 3—5 分钟内能讲清任务理解、决策和专家计划。

## 12. 文件改造清单

### 优先修改

```text
src/components/task_studio/TaskStudioContent.vue
src/components/task_studio/TaskInputSection.vue
src/components/task_studio/AgentScenarioPresets.vue
src/components/task_studio/AgentDecisionPreview.vue
src/components/task_studio/IntentCompilerPreview.vue
src/components/task_studio/SceneAssetPanel.vue
src/components/task_studio/TaskParameterPanel.vue
src/data/agent-demo/scenarios.ts
src/data/agent-demo/*-case.ts
src/lib/agent-presentation-types.ts
src/lib/agent-scenario-matcher.ts
```

### 建议新增

```text
src/lib/task-studio-agent-view-model.ts
src/data/agent-demo/assets.ts

src/components/task_studio/AgentCommandHeader.vue
src/components/task_studio/AgentTaskComposer.vue
src/components/task_studio/DecisionExampleStrip.vue
src/components/task_studio/SceneDataCockpit.vue
src/components/task_studio/SceneSettingsDrawer.vue
src/components/task_studio/TaskUnderstandingBoard.vue
src/components/task_studio/AgentDecisionSummary.vue
src/components/task_studio/ProposedWorkflowGraph.vue
src/components/task_studio/AgentPlanActionBar.vue
src/components/task_studio/InlineAgentResponse.vue
```

## 13. 测试方案

### 单元测试

- 页面状态映射；
- 五类决策按钮；
- 场景完整度计算；
- 场景匹配；
- 任务理解覆盖参数；
- 计划图节点生成；
- 防重复提交。

### 组件测试

- 空任务；
- 自定义任务输入；
- 选择决策示例；
- 更换场景；
- 缺少时相数据；
- 直接回答；
- 内联澄清；
- 谨慎停止；
- 场景设置抽屉关闭后遮罩销毁。

### 手工回归

```text
进入发起巡查
→ 输入主案例
→ 修改空间距离
→ 更换场景再返回
→ 启动分析
→ 浏览器返回
→ 再次进入执行页
→ 重置任务
→ 分别执行直接回答、澄清和谨慎停止
```

全程不应出现重复任务、状态丢失、透明遮罩或页面无法点击。

## 14. 主要风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 一屏内容过多 | 信息分三层，高级设置使用抽屉 |
| 任务理解与决策重复 | 理解板展示“理解了什么”，决策摘要展示“为什么这样处理” |
| 计划图看起来像已执行 | 统一标记“建议分析计划”和 `pending` 状态 |
| 五个示例被误解为能力上限 | 使用“决策示例”，并突出自由输入 |
| 自定义输入在纯前端阶段不够智能 | 明确有限场景匹配，使用稳定预览，不自由生成虚假结果 |
| 页面容器继续膨胀 | 引入 ViewModel 和专职组件 |
| 场景设置抽屉产生遮罩残留 | 使用受控 open 状态、路由卸载清理和专项回归 |
| 未来接真实 Agent 返工 | 页面只消费统一展示协议和 Provider |

## 15. 最终验收标准

### 产品表达

- 页面看起来是 Agent 指挥台，不是参数表单；
- 自然语言、场景数据、任务理解和专家计划关系清楚；
- 五类决策是动态结果，不是固定任务分类；
- 能表达 Agent 的安全边界和人工复核意识。

### 视觉

- 正射场景是核心视觉元素；
- 任务输入是第一交互焦点；
- 计划图是核心技术亮点；
- 主按钮唯一且明确；
- 投影环境下主要文字和节点无需缩放。

### 工程

- 保留现有本地 Runtime、快照恢复和 API 分支；
- 组件不直接依赖 `localStorage`；
- 不重复创建任务和定时器；
- 返回、刷新和重置稳定；
- 类型检查和静态构建通过。

## 16. 推荐实施顺序

```text
P0 ViewModel 与计划快照
→ P1 任务输入和场景数据舱
→ P2 任务理解板和动态计划图
→ P3 五类结果交互与状态恢复
→ P4 视觉完善和比赛彩排
```

预计总工作量为 7—12 个开发日。即使不考虑时间和难度，也应按这个顺序实施，因为先稳定 ViewModel 和计划数据，才能避免视觉组件完成后再次因数据结构变化而返工。
