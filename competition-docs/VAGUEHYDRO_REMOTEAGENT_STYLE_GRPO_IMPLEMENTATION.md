# VagueHydro RemoteAgent-Style GRPO 实现方案

> 状态：当前有效实施方案（v2，2026-09-30）。
>
> 本方案取代 `VAGUEHYDRO_RL_IMPLEMENTATION_PLAN.md` 中“以 Verifier 和真实专家执行作为主要 RL 奖励”的原始路线。第一阶段以 Gold-Action GRPO 为正式主实验，Verifier 仅作为独立的第二阶段增强，不得混写实验结论。

## 0. 方案定位

本方案完整借鉴 RemoteAgent 的核心训练范式，但将任务、动作空间和专家工具替换为 HydroGuardian 的水利领域定义：

```text
Qwen3-VL-8B-Instruct
        ↓
VagueHydro LoRA 监督适配
        ↓
Gold-Action GRPO
        ↓
结构化 AgentRequest 规划
        ↓
HydroGuardian 专家执行与业务闭环
        ↓
Verifier 增强（第二阶段，可独立评估）
```

第一阶段不把复杂专家质量作为主要 RL 奖励，而是使用冻结的 VagueHydro 标准动作计算确定性奖励；这样可以复现 RemoteAgent 的训练逻辑，并将规划能力提升与 Verifier 质量解耦。第二阶段再将真实执行和 Verifier 反馈作为附加奖励，用于学习故障恢复和证据冲突处理。

最终方法名称建议为：

> **VagueHydro-R：RemoteAgent-style Gold-Action GRPO for Capability-Aware Hydrographic Agents**

### 0.1 本轮方向调整

| 原方案 | 当前方案 |
|---|---|
| Verifier 是主要奖励来源 | Gold AgentRequest 是主要奖励来源 |
| 训练期频繁调用真实专家 | 主训练阶段不调用真实专家 |
| 统一优化规划、执行和恢复 | 先证明规划增益，再独立验证执行增强 |
| 依赖复杂的在线环境质量 | 依赖确定、可复现的结构化规则奖励 |
| 完整闭环 RL 是主方法 | Gold-Action GRPO 是主方法，闭环 RL 是扩展 |

本方案需要依次回答两个互不混淆的研究问题：

1. Gold-Action GRPO 能否在不损害现有 LoRA 能力的前提下，提高模糊水利意图理解、结构化规划及未见工具任务的路由泛化？
2. 在第一阶段成立后，少量真实执行和 Verifier 反馈能否进一步改善故障恢复与证据冲突处理？

## 1. 现有基线冻结

在开始 RL 前，必须冻结以下内容，不得被训练脚本覆盖：

| 项目 | 冻结内容 |
|---|---|
| Base model | `Qwen3-VL-8B-Instruct` 的 revision 和本地路径 |
| SFT adapter | 当前 VagueHydro LoRA checkpoint |
| Prompt | system、user、ToolSpec 和示例模板 |
| Request schema | `AgentRequest`、`AgentAction`、`Arguments`、`Workflow` |
| Tool registry | 专家名称、输入模态、参数约束和输出类型 |
| Gold split | 训练集、验证集和 240 条冻结测试集 |
| Baseline report | 当前 LoRA 的结构化规划和五条件 E2E 报告 |

240 条冻结测试集只能用于最终评估，不得参与 SFT、GRPO、奖励权重选择或早停。

## 2. 目录和产物约定

建议在 Agent 训练仓库中新增以下目录；HydroGuardian 仓库保存协议、文档和展示材料。

```text
hydro_remote_agent/
├─ configs/
│  ├─ vaguehydro_lora_baseline.json
│  ├─ vaguehydro_grpo_gold_action.json
│  ├─ vaguehydro_grpo_verifier_augmented.json
│  └─ vaguehydro_rl_protocol_v1.json
├─ datasets/vaguehydro_rl/
│  ├─ train_gold_action.jsonl
│  ├─ valid_gold_action.jsonl
│  ├─ hard_cases_train.jsonl
│  ├─ hard_cases_valid.jsonl
│  └─ manifests.json
├─ environments/
│  ├─ agent_request_env.py
│  ├─ hydro_executor_env.py
│  └─ trajectory_schema.py
├─ rewards/
│  ├─ gold_action_reward.py
│  ├─ workflow_reward.py
│  ├─ verifier_reward.py
│  └─ reward_composer.py
├─ training/
│  ├─ train_grpo_gold_action.py
│  ├─ train_grpo_verifier_augmented.py
│  └─ callbacks.py
├─ evaluation/
│  ├─ evaluate_planning.py
│  ├─ evaluate_recovery.py
│  └─ compare_rl_conditions.py
└─ tools/
   ├─ prepare_vaguehydro_rl_data.py
   ├─ launch_vaguehydro_grpo.sh
   └─ audit_vaguehydro_rl.py
```

比赛仓库新增材料：

```text
HydroGuardian/competition-docs/
├─ VAGUEHYDRO_REMOTEAGENT_STYLE_GRPO_IMPLEMENTATION.md
├─ VAGUEHYDRO_RL_RESULTS.md
└─ figures/vaguehydro-grpo-framework.png
```

## 3. 训练数据格式

每条训练样本必须包含查询、资产摘要、ToolSpec 子集和 gold AgentRequest：

```json
{
  "id": "vh-train-000001",
  "query": "筛查近岸疑似新增堆砂并判断是否需要复核",
  "language": "zh",
  "difficulty": "L3",
  "assets": {
    "scene_id": "scene-001",
    "modalities": ["image_t1", "image_t2", "point_cloud"],
    "available_times": ["t1", "t2"]
  },
  "tool_registry": ["change_detection", "hydro_program3d", "geometry", "verifier"],
  "gold_request": {
    "action": {"type": "workflow"},
    "arguments": {"target": "sand_pile", "relation": "near_bank"},
    "workflow": {
      "steps": [
        {"id": "s1", "tool": "change_detection", "depends_on": []},
        {"id": "s2", "tool": "hydro_program3d", "depends_on": ["s1"]},
        {"id": "s3", "tool": "verifier", "depends_on": ["s2"]}
      ]
    }
  },
  "allowed_actions": ["workflow", "clarify"],
  "gold_provenance": {"source": "vaguehydro_builder_v1", "version": "..."}
}
```

### 3.1 数据生成和切分

1. 从现有 VagueHydro 标准动作读取 gold AgentRequest。
2. 重新渲染 system/user prompt，确保训练输入不泄露本地路径和测试答案。
3. 对训练集生成等价动作、参数顺序扰动和合法 Workflow 顺序扰动。
4. 生成非法 JSON、未知工具、循环依赖和缺少参数负样本。
5. 按场景、Tile、区域和语言进行分组切分，防止同一场景泄漏到训练和验证。
6. 生成独立困难集，但不得从 240 条冻结测试集反向改写。

训练/验证/测试按任务能力分层，而不是只做随机切分：

| 数据层 | 主要内容 | 用途 |
|---|---|---|
| Train-Intrinsic | direct、分类、属性、计数、定位及已见规划组合 | LoRA/GRPO 参数更新 |
| Valid-Intrinsic | 与训练同能力、不同场景和表达 | 奖励权重、KL、早停 |
| Valid-Planning-Hard | 信息缺失、复杂参数、等价 Workflow | 规划泛化与行为边界选择 |
| Test-Extrinsic | 未见或低频工具组合、复杂 dense 专家任务 | 检验能力边界和工具路由泛化 |
| Test-Frozen-240 | 现有正式冻结人口 | 最终 E2E 回归比较 |
| Test-Recovery | 专家故障、证据冲突、局部重试 | 仅用于 Verifier 增强评估 |

`Test-Extrinsic` 和 `Test-Frozen-240` 不得用于选择奖励权重、Prompt、checkpoint 或训练轮数。若对这两类结果进行人工观察后修改方法，必须创建新的盲测版本，不得继续沿用原测试结论。

### 3.2 轨迹数据

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

## 4. AgentRequest 规范化

GRPO 奖励不能直接比较原始 JSON 字符串，必须先规范化：

```python
normalized = {
    "action_type": request.action.type,
    "tools": sorted(unique_tools(request)),
    "arguments": canonicalize_arguments(request.arguments),
    "workflow_nodes": canonicalize_nodes(request.workflow),
    "workflow_edges": canonicalize_edges(request.workflow),
    "artifact_refs": canonicalize_artifact_refs(request.workflow),
    "stop_condition": canonicalize_stop_condition(request.stop_condition),
}
```

规范化要求：

- 不因 JSON 字段顺序不同而扣分；
- 不因等价的 Workflow 拓扑顺序不同而扣分；
- 对工具集合、参数集合和 DAG 边集合分别评分；
- 对非法结构直接标记为 invalid，不尝试自动修复后再给高分。

## 5. Gold-Action Reward

第一阶段只使用可复现的 gold action 奖励，不调用真实专家：

```text
Rgold = 0.20 R_schema
      + 0.20 R_action
      + 0.20 R_tool
      + 0.20 R_argument
      + 0.15 R_workflow
      + 0.05 R_stop
      - 0.20 P_invalid
```

### 5.1 Schema 奖励

- 完整解析、字段类型正确、通过 JSON Schema：`1.0`；
- 可解析但字段缺失：按缺失字段比例扣分；
- 无法解析：`0.0` 并触发 invalid penalty。

### 5.2 动作奖励

```text
exact action type → 1.0
allowed alternative action → 0.5
不允许的动作 → 0.0
```

`clarify`、`abstain` 和 `human_review` 不应被固定 gold 字符串限制，只要样本定义的 allowed action 集合允许，就可以获得部分奖励；但在信息完整任务上无意义澄清要扣分。

### 5.3 工具奖励

- 单工具：工具准确率；
- 多工具：工具集合 Precision/Recall/F1；
- 工具顺序错误但 DAG 等价：不扣顺序分；
- 使用未注册工具：工具奖励为零并触发 invalid penalty。

### 5.4 参数奖励

不同参数使用不同匹配器：

| 参数 | 评分方式 |
|---|---|
| 类别/属性标签 | 集合 F1 |
| 时相 | 离散准确率 |
| 数值阈值 | 相对误差衰减 |
| 坐标/范围 | IoU |
| 空间关系 | 谓词准确率 + 对象 F1 |
| 输出类型 | 精确匹配 |

### 5.5 Workflow 奖励

```text
Rworkflow = 0.30 × node_f1
           + 0.30 × edge_f1
           + 0.20 × artifact_ref_f1
           + 0.20 × topological_validity
```

合法但不同于 gold 的拓扑只要满足依赖约束，应获得部分奖励；存在循环依赖、未定义 Artifact 或不可执行节点时，拓扑有效性为零。

## 6. GRPO 训练流程

### 6.1 每个 batch 的处理

```text
读取一批 VagueHydro 任务
→ 每条任务采样 G=8 个 AgentRequest
→ 解析并规范化候选
→ 计算 Gold-Action Reward
→ 组内标准化 advantage
→ GRPO clipped objective
→ KL 约束 VagueHydro LoRA reference
→ 更新 RL LoRA adapter
```

### 6.2 关键配置

```yaml
base_model: Qwen3-VL-8B-Instruct
init_adapter: vaguehydro_lora
train_adapter: vaguehydro_grpo_rl
algorithm: grpo
group_size: 8
temperature: 0.85
top_p: 0.95
learning_rate: 1.0e-6
num_epochs: 8
bf16: true
lora_rank: 32
lora_alpha: 64
kl_coefficient: 0.05
max_new_tokens: 1536
max_workflow_steps: 8
seed: 20260930
```

实际配置必须根据验证集奖励方差和 KL 曲线调整，但每次调整都要生成新的 config、checkpoint 和报告，不允许覆盖旧结果。

第一轮只允许搜索以下有限配置，避免在验证集上进行无边界调参：

| 参数 | 候选值 |
|---|---|
| group size | `4`, `8` |
| temperature | `0.80`, `0.95` |
| KL coefficient | `0.02`, `0.05`, `0.10` |
| learning rate | `5e-7`, `1e-6` |
| LoRA rank | 默认 `32`，仅显存允许时对比 `64` |

主配置必须提前写入 protocol manifest；超出上述范围的实验只能作为探索性结果，不能替换预注册主结果。

### 6.3 伪代码

```python
for batch in train_loader:
    candidates = policy.sample_group(batch, group_size=8)
    rewards = []
    for request in candidates:
        parsed = parse_agent_request(request)
        normalized = normalize_agent_request(parsed)
        rewards.append(gold_action_reward(batch.gold, normalized))

    advantages = group_normalize(rewards)
    loss = grpo_clipped_loss(
        policy=policy,
        old_policy=old_policy,
        candidates=candidates,
        advantages=advantages,
    )
    loss += kl_coefficient * kl_divergence(policy, vaguehydro_lora_reference)
    loss.backward()
    optimizer.step()
```

## 7. 第二阶段：Verifier 增强训练

Gold-Action GRPO 稳定后，再引入真实执行反馈。此阶段不替换第一阶段模型，而是创建独立的 `vaguehydro_grpo_verifier` adapter。

### 7.1 额外奖励

```text
Rverifier = 0.35 R_execution
          + 0.35 R_quality
          + 0.15 R_artifact
          + 0.15 R_recovery
```

组合奖励为：

```text
Rtotal = 0.80 Rgold + 0.20 Rverifier
```

第一版 Verifier 增强不得让真实质量完全取代 gold action 奖励，以避免错误 Verifier 将策略带偏。

### 7.2 Verifier 增强范围

只训练以下新行为：

- 专家超时后的重试或切换；
- 参数不足时的修正；
- 证据冲突时增加验证步骤；
- 低质量结果时转人工复核；
- 质量达标后的提前停止。

不得用 Verifier 重新定义已经由 gold action 明确监督的基础动作类型和工具注册表。

## 8. 评估矩阵

必须比较以下条件：

| 条件 | 作用 |
|---|---|
| Qwen3-VL zero-shot | 通用模型基线 |
| Qwen3-VL + prompt | 提示工程基线 |
| VagueHydro LoRA | 当前正式基线 |
| LoRA + Gold-Action GRPO | RemoteAgent-style 主方法 |
| LoRA + Gold-Action GRPO + Verifier | 执行反馈增强 |
| Gold-policy | 专家执行参考 |

### 8.1 规划指标

- Schema 合法率；
- 动作类型准确率；
- 专家选择准确率；
- 参数槽位 Precision/Recall/F1；
- Workflow 节点、边和 Artifact 引用 F1；
- 严格 AgentRequest 匹配率；
- 澄清和拒答准确率。

### 8.2 真实执行指标

- 执行成功率；
- 输出覆盖率；
- Verified E2E；
- 平均任务分；
- 直接回答准确率；
- 点掩膜 Macro IoU/Dice；
- 关系任务准确率；
- 全场景 mIoU；
- Artifact 完整性。

### 8.3 策略指标

- 平均工具调用次数；
- 平均 Workflow 步数；
- 平均端到端时延；
- 故障恢复成功率；
- 无效调用率；
- 错误自信率；
- 置信度校准误差；
- 转人工准确率。

## 9. 必做消融

至少完成：

1. LoRA vs LoRA + Gold-Action GRPO；
2. `G=4` vs `G=8`；
3. 有 KL vs 无 KL；
4. 只奖励动作/工具 vs 加入参数/Workflow 奖励；
5. 严格字符串匹配 vs 规范化结构匹配；
6. 有效动作集合支持 vs 只允许单一 gold action；
7. Gold-Action GRPO vs Gold-Action GRPO + Verifier；
8. 正常集 vs 困难集 vs OOD 集。

主结论优先级固定为：规划泛化增益、冻结集无退化、工具路由保持、Verifier 增强收益。不得用单一 Schema 合法率提升替代前三项结论。

## 10. 实施阶段与准入门槛

| 阶段 | 主要工作 | 交付物 | 进入下一阶段的条件 |
|---|---|---|---|
| M0 基线冻结 | 固化 LoRA、Prompt、Schema、Tool registry 和数据哈希 | baseline manifest、240 条报告、环境清单 | 哈希和人口审计全部通过 |
| M1 数据与奖励 | 生成训练/验证/困难集，完成规范化和 Gold Reward | 数据 manifest、奖励单测、分布报告 | 人工抽检与单测通过，冻结集无泄漏 |
| M2 Rollout 冒烟 | 用小批量任务验证解析、分组采样和 reward decomposition | 50–100 条 rollout、异常清单 | 无系统性解析错误，组内奖励存在有效方差 |
| M3 Gold-Action GRPO | 训练独立 RL LoRA，监控 KL、长度和奖励 | checkpoint、曲线、验证报告 | 规划指标提升或持平，未出现 reward hacking |
| M4 主实验评测 | 在 Extrinsic、困难集和冻结 240 上统一比较 | 全指标表、配对统计、审计报告 | 冻结集无显著退化，至少一项泛化指标提升 |
| M5 Verifier 增强 | 只针对故障恢复与证据冲突训练独立 adapter | 恢复轨迹、成本报告、增强 checkpoint | 恢复提升且正常任务不显著退化 |
| M6 比赛材料 | 更新方法图、结果表、案例与答辩表述 | 文档、图表、回放案例 | 结论与实际完成阶段严格一致 |

任何阶段未达到准入门槛时，先记录负面结果并修复该阶段，不直接扩大到真实执行 RL。

## 11. 实验运行命令约定

以下命令为实现接口约定，实际脚本路径按训练仓库落地：

```bash
# 生成 RL 数据和 manifest
python -m hydro_remote_agent.tools.prepare_vaguehydro_rl_data \
  --source runs/hydro_remote_agent/agent_eval_v1 \
  --output datasets/vaguehydro_rl \
  --freeze-test-manifest configs/vaguehydro_rl_protocol_v1.json

# 训练 RemoteAgent-style Gold-Action GRPO
python -m hydro_remote_agent.training.train_grpo_gold_action \
  --config configs/vaguehydro_grpo_gold_action.json \
  --train datasets/vaguehydro_rl/train_gold_action.jsonl \
  --valid datasets/vaguehydro_rl/valid_gold_action.jsonl \
  --output runs/hydro_remote_agent/vaguehydro_grpo_gold_action_v1

# 评估规划能力
python -m hydro_remote_agent.evaluation.evaluate_planning \
  --checkpoint runs/hydro_remote_agent/vaguehydro_grpo_gold_action_v1/best \
  --input datasets/vaguehydro_rl/valid_gold_action.jsonl \
  --output runs/hydro_remote_agent/vaguehydro_grpo_gold_action_v1/planning_report.json

# 在冻结240条任务上运行最终比较
bash hydro_remote_agent/tools/run_vaguehydro_rl_comparison.sh \
  --conditions baseline,lora,gold_action_grpo,verifier_augmented \
  --gold runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl

# 完整性审计
python -m hydro_remote_agent.tools.audit_vaguehydro_rl \
  --protocol configs/vaguehydro_rl_protocol_v1.json \
  --run-root runs/hydro_remote_agent/vaguehydro_rl_comparison_v1
```

## 12. 验收门槛

### Gold-Action GRPO 必须满足

- 验证集 Schema 合法率不低于 LoRA 基线；
- 动作类型、工具选择和 Workflow 指标不低于 LoRA 基线；
- 240 条冻结测试的 Verified E2E 不得显著下降；
- 不能通过删除失败样本提高指标；
- 每条结果保留 model、prompt、config、输入和输出哈希。

### Verifier 增强必须满足

- 困难集故障恢复率提升；
- 证据冲突任务的错误自信率下降；
- 平均调用次数或平均时延不恶化，除非质量提升达到预设阈值；
- 正常任务质量不显著下降；
- 至少有一个可回放案例显示 LoRA 失败而 RL 成功。

## 13. 失败处理和回滚

出现以下情况时，回滚到 Gold-Action GRPO 或原始 VagueHydro LoRA，不把失败模型接入比赛演示：

- RL 只提升 Schema 合法率，不提升严格匹配或任务分；
- 240 条冻结任务出现显著退化；
- 训练模型出现无限 Workflow、重复工具调用或无意义澄清；
- KL 发散、生成长度失控或 reward hacking；
- Verifier 增强导致高风险任务错误自动闭环；
- 结果无法通过人口、ID、哈希和执行真实性审计。

所有失败 checkpoint、奖励曲线和审计报告仍需保留，作为消融和限制说明的一部分。

## 14. 比赛文档更新内容

只有 Gold-Action GRPO 和真实评测完成后，才在比赛文档中加入以下内容：

1. 新增“VagueHydro-R 训练方法”小节；
2. 给出 LoRA、Gold-Action GRPO 和 Verifier 增强三阶段关系；
3. 增加 GRPO 奖励组成图；
4. 增加 `LoRA vs LoRA+GRPO` 表格；
5. 增加一个故障恢复案例；
6. 明确区分规划奖励和执行质量奖励；
7. 报告训练集、验证集和冻结测试集的隔离方式；
8. 报告完整性审计和失败样本处理方式。

推荐最终表述：

> HydroGuardian 借鉴 RemoteAgent 的能力边界感知范式，以 VagueHydro 标准任务动作作为可验证监督信号，在 Qwen3-VL LoRA 领域适配基础上采用 Gold-Action GRPO 优化动作选择、专家调用、参数组织和 Workflow 构建；随后以真实专家执行和独立验证器作为附加反馈，学习失败恢复、证据冲突处理和成本约束策略。

## 15. 最终交付物

- RL 数据 manifest 和切分审计；
- Gold-Action Reward 单元测试；
- GRPO 配置和训练日志；
- LoRA、Gold-Action GRPO、Verifier 增强三个 checkpoint；
- 规划指标报告；
- 240 条冻结任务端到端报告；
- 困难/OOD/故障恢复报告；
- 统计比较和完整性审计；
- 训练与推理框架图；
- 比赛文档和答辩讲稿更新稿。
