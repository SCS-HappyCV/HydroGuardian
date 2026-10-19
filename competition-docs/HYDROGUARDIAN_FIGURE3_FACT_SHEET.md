# HydroGuardian / VagueHydro Agent 科研框架图事实底稿

## 1. 图的核心论点

HydroGuardian 不是用一个大模型直接完成所有遥感计算，而是训练一个面向水利场景的多模态 Agent，使其把自然语言巡查任务转化为合法、可执行、可验证的结构化动作，再按任务需要动态调用外部专家并组织依赖工作流。

建议图题：

> **VagueHydro: Capability-Aware Planning and Verified Expert Collaboration for Complex Hydrological Remote-Sensing Tasks**

中文图题可写：

> **VagueHydro：面向复杂水利遥感任务的能力感知规划与可信专家协作框架**

图中应突出四个区别于普通“LLM + Tools”示意图的机制：

1. 水利任务专用的结构化 AgentAction 学习；
2. 五种决策动作，而非任何请求都调用模型；
3. 根据 ToolSpec 与依赖关系动态生成单专家调用或多专家 DAG；
4. 专家产物经过独立质量验证后，才进入风险候选与人工业务决策。

---

## 2. 推荐总体版式

采用与 RemoteAgent Figure 3 相近的“双阶段科研框架”结构，但内容必须替换为本项目真实机制。

### 左侧：Training — Learning to Plan

表现“通用视觉语言模型如何成为水利任务专用 Agent”。

从左到右：

```text
VagueHydro supervision
  ├─ natural-language query
  ├─ orthophoto / visual context
  ├─ asset manifest
  ├─ six ToolSpecs
  └─ gold AgentRequest
            ↓
Qwen3-VL-8B-Instruct + BF16 LoRA SFT
            ↓
Structured AgentRequest / AgentAction
  ├─ intent
  ├─ action type
  ├─ tool selection
  ├─ typed arguments
  ├─ dependencies
  └─ expected outputs
```

训练侧画面可以用三层卡片：输入上下文、Agent Backbone、结构化监督目标。不要把专家模型画入反向传播链，因为专家并未与 Agent 端到端联合训练。

训练侧允许标注的关键事实：

- Backbone：`Qwen3-VL-8B-Instruct`；
- 训练方式：BF16 LoRA SFT，rank 16，alpha 32；
- 只训练语言层 attention 与 MLP projection；
- 可训练参数 43,646,976，占总参数 0.4954%；
- 16,360 条课程训练样本，覆盖全部 1,145 个训练 tile；
- 训练动作比例 direct / tool / workflow = 25% / 35% / 40%；
- 中英文及 L0–L3 基本均衡；
- 监督目标是完整、严格的 JSON `AgentRequest`，不是自由文本答案。

主图只建议保留以下精简标签：

```text
Qwen3-VL-8B + LoRA SFT
16,360 curriculum samples
Structured AgentRequest supervision
```

其余数字放图注或旁注，避免主图过密。

### 右侧：Inference — Plan, Execute, Verify

表现“一条自然语言水利任务如何被自主分流、规划并执行”。

推荐主链：

```text
Query + visual/asset context
            ↓
VagueHydro Agent
  intent understanding
  capability matching
  parameter grounding
  dependency planning
            ↓
Schema & ToolSpec Validator
            ↓
Five-way Action Router
```

路由器分出五种真实动作：

```text
direct_answer  → textual response
clarification  → request missing inputs
abstain        → refusal with reason
tool_call      → one-step expert workflow
workflow       → dependency-aware expert DAG
```

`tool_call` 与 `workflow` 汇入统一 `Workflow Executor`。`direct_answer`、`clarification`、`abstain` 不进入专家执行链。

---

## 3. 输入边界：必须画清楚的两条数据通路

这是框架图最容易误画的地方。

### 控制与语义上下文通路

进入 Agent Backbone：

- 用户自然语言查询；
- 当前正射影像或视觉编码；
- 点云、前后时相影像、配准状态等资产描述；
- 六个 ToolSpec；
- 可选历史对话或上次执行摘要。

### 重型遥感数据通路

直接进入外部专家或 Artifact Store：

- 百万级原始点云；
- 原始前后时相影像；
- 中间掩膜、概率图与几何结果。

图中应使用一条粗实线或独立数据总线，把“Raw Remote-Sensing Assets”连接到 Expert Pool；不要画成原始点云先进入 Qwen3-VL。Agent 接收的是路径、元数据和必要视觉上下文，实际点级计算由专家执行。

---

## 4. 外部专家池：五类专家、六个 ToolSpec

建议把专家池画成五张并列的紧凑卡片；GUFNet 卡片内部包含两个接口角标。

### Expert 1 — GUFNet Semantic Perception

ToolSpec：

- `point_semantic_segmentation`
- `multimodal_semantic_segmentation`

输入：点云；或影像 + 已配准点云。

输出：

- point labels；
- class masks；
- class probabilities；
- class summary；
- projection metadata（派生接口）。

必须附带的真实性限定：当前在线 `multimodal_semantic_segmentation` 接口验证影像资产，但实际推理复用 GUFNet 点云分支，`image_used=false`，不能画成当前部署已完成独立影像融合推理。

### Expert 2 — RFANet Change Detection

ToolSpec：`image_change_detection`

输入：已配准且同尺寸的前、后时相正射影像。

输出：

- change mask；
- change probability map；
- change regions。

### Expert 3 — HydroProgram3D Language-Guided Segmentation

ToolSpec：`language_guided_point_segmentation`

输入：影像、点云与自然语言目标描述。

输出：

- target mask；
- target probabilities；
- compiled spatial program；
- sampling metadata；
- point visualization。

### Expert 4 — Geometry Relation Analysis

ToolSpec：`geometry_relation_analysis`

输入：点云与上游分割产物。

能力：

- near / above；
- pair distance；
- elevation difference；
- class / region statistics。

输出：relation mask 与 geometry report。

### Expert 5 — Quality Verifier

ToolSpec：`result_quality_verification`

输入：专家 manifest、产物清单及可选原始资产。

检查：

- 掩膜、概率与源点数一致性；
- 概率有限性、范围与归一化；
- 平均置信度与低置信度比例；
- 变化掩膜和概率图对齐；
- 空结果、缺失产物与异常类别主导。

输出：quality report、diagnostic overlay，以及 passed / warning / abstention recommendation。

---

## 5. 动态 Workflow 的正确画法

工作流不是固定八步，也不是固定顺序调用全部专家。应画成由 Agent 动态产生的有向无环图。

### 示例 A：双时相变化巡查

```text
Before / After Orthophotos
            ↓
RFANet Change Detection
            ↓
Quality Verifier
            ↓
Change Evidence + Risk Candidate
```

### 示例 B：自然语言空间关系巡查

```text
Query + Image + Point Cloud
            ↓
HydroProgram3D Target Segmentation
            ↓ artifact reference
Geometry Relation Analysis
            ↓
Quality Verifier for each expert output
            ↓
Spatial Evidence + Risk Candidate
```

### 示例 C：全场语义识别

```text
Point Cloud
     ↓
GUFNet Semantic Segmentation
     ↓
Quality Verifier
     ↓
Semantic Evidence
```

执行器的真实职责：

- 解析步骤依赖；
- 解析 `${step.artifacts.name}` 产物引用；
- 顺序执行已拓扑排序的步骤；
- 自动验证每个需要验证的专家结果；
- 依赖失败时跳过下游步骤；
- 汇总终端产物、warning、耗时与 manifest。

图中可以用“小型 DAG 芯片”表示动态计划，不要把工作流画成固定流水线。

---

## 6. 质量门控与业务输出

Verifier 的真实作用不是自动重新训练或自动更换专家，而是为产物建立独立质量证据并限制后续自动化。

正确逻辑：

```text
Expert Artifacts
       ↓
Independent Verification
       ↓
Quality Gate
  ├─ passed → automation allowed
  └─ warning / low score / abstention recommended
                 → review required
```

系统随后依据已验证的变化、几何和证据产物编译 `risk_candidates`。风险候选包含：

- 风险类型、标题和等级；
- evidence score；
- evidence references；
- region scope；
- quality gate；
- `review_required` 与业务确认要求。

主图右下角建议画成三层输出：

```text
Verified Artifacts
        ↓
Evidence-backed Risk Candidates
        ↓
Human Review / Work-order Decision
```

这样能够与 HydroGuardian 前端的风险研判、工单生成和人工复核闭环衔接，同时不把业务判断错误地归因给算法模型。

---

## 7. 适合放入主图的实验依据

主框架图最多放两个小型结果标注，不要塞入完整实验页。

建议优先选择：

1. `Workflow graph accuracy: 0.00% → 100.00%`
2. `Verified E2E: 2% → 96%`（50 条真实 Tool Observation ReAct 与 VagueHydro LoRA 对比）

可选替代：

- Tool selection accuracy：41.25% → 100.00%；
- Argument F1：30.06% → 99.66%；
- Output coverage：66% → 100%；
- Mask Macro IoU：0.24 → 0.46；
- Average task score：0.21 → 0.57。

不要在框架图中写“整体识别准确率 100%”。路由、执行、验证和像素级预测是不同指标。

---

## 8. 图中禁止出现的错误表述

1. 不画 GRPO、DPO 或 reward optimization 为已完成训练流程；当前正式训练是 LoRA SFT。
2. 不画专家模型与 Agent Backbone 端到端联合训练。
3. 不画原始百万点点云直接输入大语言模型。
4. 不画固定八阶段多智能体流程。
5. 不画所有任务都会调用全部五类专家。
6. 不把五类专家误写为六类专家；真实结构是五类专家、六个 ToolSpec。
7. 不把当前 GUFNet 派生接口画成已经在线融合影像与点云。
8. 不画 Verifier 自动修改参数、替换专家或触发重规划；当前实现只负责验证、告警、拒答建议与质量门控。
9. 不给 RFANet 添加未经正式标注评测支持的准确率。
10. 不把 `100% execution success` 表述成 `100% semantic prediction accuracy`。
11. 不把风险候选直接等同于最终业务风险；它仍需业务确认或人工复核。

---

## 9. 视觉语言与配色规范

目标风格：科研论文中的精密系统框架图，而不是比赛宣传海报。

- 画布：横向 16:9 或论文双栏宽图；
- 背景：纯白或极浅灰蓝；
- 主色：深海军蓝；
- Agent / planning：青蓝；
- Expert tools：橙色；
- Artifact / data：紫灰；
- Verification / trusted outputs：绿色；
- warning / review required：琥珀色；
- 禁止大面积渐变、发光、3D 金属质感和装饰性大坝背景；
- 节点使用细描边圆角矩形，箭头保持等粗；
- 实线表示控制或数据流，虚线表示验证、约束或质量门控；
- 每个模块控制在两行标签以内，详细解释放图注。

---

## 10. 建议最终图层级

```text
┌──────────────────── Training: Learn Structured Planning ────────────────────┐
│ VagueHydro Data → Qwen3-VL-8B + LoRA SFT → Structured AgentRequest         │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────── Inference: Plan, Execute, Verify ───────────────────────┐
│ Query + Context → VagueHydro Agent → Validator → Five-way Action Router     │
│                                  ├─ Direct / Clarify / Abstain               │
│                                  └─ Tool Call / Dynamic Workflow DAG         │
│                                              ↓                               │
│ Raw Assets ───────────────────────────→ Five Expert Families                 │
│                                              ↓                               │
│                                     Artifact & Manifest Store                │
│                                              ↓                               │
│                                      Independent Verifier                    │
│                                              ↓                               │
│                              Quality-gated Evidence & Risk Candidates        │
│                                              ↓                               │
│                                   Human Review / Work Order                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

这份层级可直接转换为可编辑 SVG，后续再根据 PPT 版式压缩文字，并把 GUFNet、RFANet 网络图作为专家卡片内的缩略图或单独方法页素材，而不塞进 Agent 总体框架图。
