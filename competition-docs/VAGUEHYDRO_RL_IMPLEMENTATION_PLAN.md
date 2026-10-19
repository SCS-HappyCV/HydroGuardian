# VagueHydro 强化学习完整实施方案

> **历史方案，已停止作为当前实验执行依据。**
>
> 最新实验方向已调整为以 Gold-Action GRPO 为主、Verifier 为后置增强。请以 `VAGUEHYDRO_REMOTEAGENT_STYLE_GRPO_IMPLEMENTATION.md` 为当前权威实施方案。本文件仅保留用于记录方案演进，不应据此启动新的训练或修改正式实验结论。

> 目标：在现有 VagueHydro LoRA 与 HydroGuardian 真实专家执行链之上，引入面向任务规划、证据验证、失败恢复和执行成本的强化学习，形成可复现、可审计、可写入比赛材料的完整研究增量。
>
> 方法暂定名：**VagueHydro-R：Verifier-Guided Reinforcement Learning for Capability-Aware Hydrographic Agents**。

## 1. 现有基线与强化学习边界

当前已有成果作为不可污染的基线和最终比较对象：

- 基础模型：`Qwen3-VL-8B-Instruct`。
- 领域适配：VagueHydro 任务数据上的 LoRA 监督微调。
- 结构化输出：`AgentRequest`，包含 `AgentAction`、`Arguments`、`Workflow` 和 Artifact 依赖。
- 专家链路：GUFNet、RFANet、HydroProgram3D、Geometry、Verifier 等能力服务。
- 正式测试：240 条冻结任务、五条件对照、真实专家执行、任务质量评分和完整性审计。
- 现有主结果：VagueHydro LoRA 严格请求匹配率 `96.67%`，执行成功率和输出覆盖率 `100%`，平均任务分 `0.6401`。

强化学习不得使用 240 条冻结测试请求进行参数更新。该集合只用于最终比较；所有 RL 超参数、奖励权重和早停策略只能依据训练集、验证集和新增困难集确定。

## 2. 最终研究问题

强化学习需要回答以下问题，而不是只证明模型能够生成合法 JSON：

1. 能否提高信息不完整、表达模糊和跨区域任务的规划泛化？
2. 能否让 Agent 根据数据和专家能力判断“执行、澄清、降级或拒答”？
3. 能否利用 Verifier 反馈修正错误参数、替换专家或局部重试？
4. 能否在任务质量不下降的前提下减少无效工具调用、Workflow 步数和响应时延？
5. 能否在影像、点云和几何证据冲突时保持可校准、可解释的谨慎行为？

## 3. 总体系统架构

```text
用户任务 Query + 场景资产元数据
              ↓
VagueHydro-R Policy（Qwen3-VL + LoRA）
              ↓
AgentRequest：动作、参数、Workflow、置信度、停止条件
              ↓
ToolSpec 校验器 + Workflow DAG 校验器
              ↓
真实专家服务执行（影像 / 点云 / 变化 / 几何）
              ↓
EvidencePack：掩膜、属性、关系、质量、来源和 Artifact
              ↓
独立 Verifier：质量、完整性、冲突、失败原因和恢复建议
              ↓
继续执行 / 修改参数 / 更换专家 / 澄清 / 降级 / 人工复核 / 拒答
              ↺
```

RL 训练环境需要同时记录三类状态：任务状态、证据状态和系统状态。

- 任务状态：原始 Query、解析出的对象、属性、时相、空间关系和风险等级。
- 证据状态：已完成步骤、Artifact、证据质量、模态支持/冲突关系。
- 系统状态：专家在线状态、GPU/CPU资源、队列长度、当前时延、调用预算和重试次数。

## 4. 数据集建设

### 4.1 正常任务

复用 VagueHydro 的训练集和验证集，覆盖：

- `direct_answer`、`tool_call`、`workflow`；
- 属性、类别、关系、空目标、全场景和双时相变化；
- `L0–L3` 四级表达难度；
- 中文、英文和中英文混合表达。

### 4.2 困难任务

在训练集和验证集之外新增独立困难集，至少包含：

| 子集 | 典型情况 | 正确策略 |
|---|---|---|
| 信息缺失 | 缺少时相、资产或空间范围 | 澄清或拒答 |
| 专家故障 | 服务离线、超时、显存不足 | 重试、换专家或降级 |
| 参数扰动 | 属性、阈值或关系条件被改写 | 修正参数 |
| 证据冲突 | 影像变化与点云形态不一致 | 增加验证或人工复核 |
| Workflow故障 | Artifact缺失、依赖错误、循环依赖 | 局部重规划 |
| OOD区域 | 新河段、新设施、新表达风格 | 可靠泛化或谨慎拒答 |

每条困难任务必须保存 gold policy、允许动作集合、失败原因、推荐恢复动作和最终验收条件。

### 4.3 轨迹数据

为每条任务保存完整轨迹，而不是只保存最终答案：

```json
{
  "request_id": "...",
  "state_before": {},
  "agent_request": {},
  "validator": {},
  "tool_result": {},
  "evidence_pack": {},
  "verifier": {},
  "recovery_action": {},
  "state_after": {},
  "reward_components": {}
}
```

## 5. Agent 动作空间

强化学习的动作不限制为工具调用，必须包含完整的业务决策空间：

- `direct_answer`：内部可靠回答；
- `call_expert`：单专家调用；
- `compose_workflow`：多专家 DAG；
- `ask_clarification`：请求最小必要补充信息；
- `retry_with_modified_arguments`：修改参数后重试；
- `switch_expert`：切换同能力备用专家；
- `degrade_output`：降低结果粒度并显式说明局限；
- `submit_for_human_review`：转人工复核；
- `abstain`：能力或证据不足时拒绝自动结论。

输出必须通过统一的 `AgentRequest` Schema，不允许 RL 直接生成无法进入现有 Executor 的自由文本轨迹。

## 6. 奖励函数

采用可解释的分解式奖励，每个 episode 同时记录子奖励和总奖励：

```text
Rtotal = 0.10 R_schema
       + 0.15 R_action
       + 0.10 R_tool
       + 0.10 R_argument
       + 0.15 R_workflow
       + 0.25 R_quality
       + 0.10 R_recovery
       + 0.05 R_calibration
       - 0.03 C_tool
       - 0.03 C_latency
       - 0.02 C_steps
       - 0.02 P_hallucination
```

各项定义：

- `R_schema`：Schema、ToolSpec 和 DAG 静态校验是否通过。
- `R_action`：动作类型是否属于 gold 或允许动作集合。
- `R_tool`：专家选择和输入模态是否正确。
- `R_argument`：目标、属性、时相、空间约束和阈值的槽位质量。
- `R_workflow`：步骤顺序、依赖、Artifact 引用和停止条件是否正确。
- `R_quality`：直接回答准确率、掩膜 IoU/Dice、关系质量、全场景 mIoU 和 Verifier 评分。
- `R_recovery`：失败后是否通过有效修改恢复，且没有重复无效调用。
- `R_calibration`：置信度是否与实际正确率一致。
- `C_tool`、`C_latency`、`C_steps`：工具次数、端到端时延和无必要步骤。
- `P_hallucination`：数据不足时自信给出无证据结论。

信息不足时，正确澄清或谨慎拒答应获得高于错误执行的奖励；信息完整时的无意义澄清应受惩罚。

## 7. Verifier 设计

Verifier 必须输出可供策略学习的错误归因，而不仅是一个通过/失败布尔值：

```json
{
  "schema_valid": true,
  "route_correct": true,
  "arguments_correct": false,
  "workflow_valid": true,
  "artifact_complete": true,
  "quality_score": 0.71,
  "failure_type": "attribute_under_specification",
  "evidence_conflict": false,
  "recommended_recovery": "refine_arguments"
}
```

错误类型至少包括：意图错误、专家错误、参数缺失、属性过宽、时相错误、空间关系错误、Artifact 缺失、专家超时、证据冲突、验证不足和需人工确认。

## 8. 训练阶段

### 阶段 A：LoRA 基线冻结

1. 固化当前 VagueHydro LoRA checkpoint、Tokenizer、Prompt、ToolSpec 和推理参数。
2. 用独立验证集重跑结构化规划指标。
3. 保存基线哈希、环境信息和结果清单。
4. 禁止后续 RL 训练覆盖该 checkpoint。

### 阶段 B：结构化策略初始化

1. 用正常任务、困难任务和故障恢复样本补充 `AgentRequest` 轨迹。
2. 对非法 JSON、错误工具、错误依赖和错误停止条件构造负样本。
3. 进行拒绝采样或短轮次 SFT，使输出稳定进入 Executor。
4. 通过 Schema、ToolSpec 和 DAG 静态校验后才进入 RL。

### 阶段 C：离线 GRPO

1. 每个请求采样 `G=8` 个候选 AgentRequest。
2. 只使用静态奖励：Schema、动作、参数、Workflow、成本。
3. 使用 KL 正则约束 RL Policy 不偏离 LoRA Reference Policy。
4. 训练过程中同步监控合法率、熵、KL、奖励方差和长度。

### 阶段 D：模拟执行 GRPO

1. 使用历史真实执行记录和代理专家模拟工具结果。
2. 加入执行成功、Artifact 完整性和 Verifier 反馈。
3. 训练失败恢复、专家切换、参数修正和人工转移动作。
4. 对每条轨迹记录完整 reward decomposition。

### 阶段 E：真实执行 GRPO

1. 在独立训练任务上调用真实专家服务。
2. 采用并行候选执行，但对同一任务共享只读资产缓存。
3. 真实计算质量、时延、GPU成本和证据完整性。
4. 将 Verifier 的错误归因反馈给下一轮策略。
5. 对高风险任务设置安全门：未通过验证不得获得正向终止奖励。

### 阶段 F：轨迹偏好优化

对完整轨迹进行排序：

```text
质量达标、证据完整、步骤短、成本低、可恢复
>
质量相同但调用更多
>
执行成功但证据不足
>
格式合法但任务错误
>
无效调用或错误自信回答
```

可在 GRPO 后增加 DPO/ORPO 作为稳定化阶段，但必须单独记录为独立实验条件。

## 9. 训练配置建议

初始配置应与 RemoteAgent 的公开设定保持可解释对应，同时根据 HydroGuardian 的结构化动作长度进行扩展：

| 配置 | 建议值 |
|---|---:|
| Policy backbone | Qwen3-VL-8B-Instruct + VagueHydro LoRA |
| RL adapter | 独立 LoRA，不覆盖监督基线 |
| LoRA rank | 32 或 64 |
| LoRA alpha | 64 或 128 |
| Candidate group size | 8 |
| Sampling temperature | 0.7–0.95 |
| KL coefficient | 0.02–0.10，验证集选择 |
| Max planning tokens | 1024–2048 |
| Max workflow steps | 8 |
| Max retries | 2 |
| Precision | bfloat16 |
| Optimizer | AdamW |
| RL algorithm | GRPO，后续可加 DPO/ORPO |

所有配置必须写入版本化 JSON/YAML，不允许依赖 shell 环境中的隐式默认值。

## 10. 实验矩阵与验收指标

正式结果至少包括：

| 条件 | 目的 |
|---|---|
| Base Qwen3-VL | 通用模型基线 |
| Base + Prompt | 提示工程基线 |
| VagueHydro LoRA | 当前主基线 |
| LoRA + 静态 GRPO | 规划合法性增量 |
| LoRA + 模拟执行 GRPO | 执行反馈增量 |
| LoRA + Verifier GRPO | 验证反馈增量 |
| LoRA + Verifier GRPO + Cost | 完整方法 |
| Gold-policy | 专家执行参考 |

每个条件都要报告：

- 路由严格匹配率；
- 参数槽位 F1；
- Workflow 图准确率；
- 执行成功率；
- 输出覆盖率；
- Verified E2E；
- 平均任务分及分层任务分；
- 故障恢复成功率；
- 澄清准确率和拒答准确率；
- 平均专家调用次数；
- 端到端时延和资源成本；
- 置信度校准误差。

统计方法继续采用配对 Bootstrap 和 McNemar 精确检验；所有条件必须共享相同任务人口、相同工具注册表和相同 Verifier。

## 11. 必做消融与负面结果记录

必须完成以下消融：

1. 去掉 Verifier 奖励；
2. 去掉故障恢复奖励；
3. 去掉成本惩罚；
4. 去掉证据冲突任务；
5. 去掉 `clarify/abstain` 动作；
6. 只用正常任务训练，不加入困难任务；
7. 不使用 KL 正则；
8. 不使用真实执行，仅使用静态奖励。

如果 RL 在正常 240 条任务上提升很小，但在故障、冲突或 OOD 集上显著提升，应将其作为主要结论，而不是视为失败。反之，如果只提升 JSON 合法率、没有提升最终任务质量，应停止扩大模型训练并如实记录。

## 12. 工程落地清单

### Agent/训练侧

- 新增 RL 配置目录：Policy、Reward、Environment、Dataset、Evaluator 分离。
- 新增 `AgentGym` 环境适配层，统一 reset、step、trajectory 和终止状态。
- 新增 `RewardComposer`，输出总奖励和全部子奖励。
- 新增 `VerifierFeedback` 错误归因协议。
- 新增 rollout 记录器，保存模型、Prompt、工具、专家和 Artifact 哈希。
- 新增训练 checkpoint、Tokenizer、ToolSpec、代码版本和环境清单。

### HydroGuardian 后端

- 扩展 Agent 执行接口，支持中间状态、重规划和局部重试。
- 扩展 Verifier 返回结构化失败原因和恢复建议。
- 为每次专家调用记录时延、资源、输入哈希、输出哈希和成本。
- 支持同一任务的多轮轨迹回放。
- 增加高风险任务的人工复核强制门。

### Web/移动端

- 展示 Agent 当前动作、置信度和澄清原因。
- 展示专家失败、重规划和证据冲突。
- 展示“自动完成 / 降级完成 / 转人工 / 拒答”的最终状态。
- 在历史回放中显示 RL Policy 版本、Verifier 结果和完整轨迹。

## 13. 里程碑与交付物

### M0：基线冻结

交付：LoRA checkpoint、240 条结果哈希、环境清单、基线报告。

### M1：环境与奖励可运行

交付：`AgentGym`、静态验证器、奖励分解测试、10 条端到端冒烟轨迹。

### M2：离线 GRPO 完成

交付：训练日志、checkpoint、验证集曲线、合法率和奖励变化。

### M3：模拟执行闭环完成

交付：故障恢复轨迹、模拟执行报告、恢复成功率和调用成本报告。

### M4：真实执行 RL 完成

交付：真实专家轨迹、Verifier 报告、资源成本和异常清单。

### M5：正式对比与审计

交付：完整实验矩阵、Bootstrap/McNemar 统计、完整性审计和可复现实验脚本。

### M6：比赛材料升级

交付：项目文档新小节、方法框架图、失败恢复案例、答辩演示脚本和一页结果摘要。

## 14. 成功判据

只有同时满足以下条件，才能把强化学习作为 HydroGuardian 的正式创新点：

1. 240 条冻结任务的 Verified E2E 和平均任务分不低于 VagueHydro LoRA 基线，或差异经统计检验不显著下降；
2. 困难/OOD 集上的故障恢复率、澄清准确率或证据冲突处理至少一项显著提升；
3. 无效工具调用或平均执行成本下降，或者在成本不变时任务质量提升；
4. 所有训练数据、模型版本、奖励配置和执行轨迹可追溯；
5. 完整性审计通过，失败样本不被删除或隐藏；
6. 能展示至少一个“LoRA 失败、RL 成功”的真实可回放案例。

## 15. 最终比赛表述

完成上述实验后，推荐将方法表述为：

> HydroGuardian 在 VagueHydro 任务动作监督和 LoRA 领域适配的基础上，引入由独立 Verifier 驱动的 Group Relative Policy Optimization，使核心 Agent 不仅能够选择专家和组织多步 Workflow，还能够根据证据质量、执行失败和资源状态进行参数修正、专家切换、澄清、降级或人工转移，从而形成面向水利模糊意图的能力边界感知与自适应执行闭环。

若只完成静态规划 RL，不得声称已经实现完整的“执行反馈强化学习”；应明确区分 `static-planning GRPO`、`simulated-execution GRPO` 和 `real-execution Verifier-Guided GRPO` 三种阶段。
