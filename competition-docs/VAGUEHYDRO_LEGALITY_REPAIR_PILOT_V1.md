# VagueHydro Legality Repair Pilot v1

> 状态：预注册实施协议。该方案用于解决上一轮 preference pilot 中“真实生成严格合法率为零”的问题，独立于旧实验目录，不覆盖旧结果，不读取 frozen-240。

## 1. 研究问题

上一轮实验已经证明：当前 LoRA 在 pair-level 偏好指标上没有明显增益，但 A/B/C 三臂的真实 free generation 均无法稳定输出可解析的 `AgentRequest`。本轮只回答一个更窄的问题：

> 在线结构约束和短程合法序列 SFT，能否把模型从“几乎不能生成合法请求”恢复到可评估状态，同时不牺牲 AgentRequest 的语义正确性？

本轮不是 GRPO，也不扩大 DPO；它是为后续 hard-negative SFT/GRPO 建立合法输出底座的诊断性 pilot。

## 2. 独立性和禁止事项

- 新目录：`runs/hydro_remote_agent/vaguehydro_legality_repair_pilot_v1/`。
- 旧目录 `vaguehydro_preference_training_pilot_v1` 只读，不写回，不覆盖。
- `frozen-240` 只允许通过已有 manifest 的 ID 排除逻辑出现；不得读取样本内容、gold 或预测。
- 所有预测必须来自真实 `model.generate()` free generation；禁止 gold/forced completion、后处理修复、非法候选过滤和事后重采样。
- B 臂的约束必须在生成过程中逐 token mask；不能在生成后 parse、repair、filter。
- C 臂只做合法 AgentRequest JSON 的 serialization SFT，不使用 rejected 作为 target，不使用 held-out/M1 validation。
- 本轮不启动正式训练；只有所有放行门槛通过后，才建议下一轮 hard-negative SFT。

## 3. 预注册三臂

| 臂 | 初始化 | 训练 | 生成 | 目的 |
|---|---|---|---|---|
| A | 当前 VagueHydro LoRA | 0 step | unconstrained | 原始基线 |
| B | 当前 VagueHydro LoRA | 0 step | 在线 `SchemaConstrainedLogitsProcessor` + EOS processor | 测试推理期约束的直接修复能力 |
| C | 当前 VagueHydro LoRA | 短程 legality/serialization SFT | unconstrained | 测试模型是否能学会唯一合法 JSON 序列 |

D（C + schema decoder）本轮关闭，不作为隐藏组合臂；若未来启用，必须新建协议并在训练前冻结。

所有臂固定：

- seeds：`20261031, 20261032, 20261033`；
- `do_sample=false`、`temperature=0.0`、`top_p=1.0`；
- `max_new_tokens=512`；
- 相同 base model、初始 LoRA adapter、prompt、tool registry、token budget 和 evaluation IDs；
- C 的优化器、学习率、最大 step、梯度累积、checkpoint step 在运行前写入 `CONFIG_FREEZE.json`。

## 4. 数据构造与隔离

### 4.1 评估集

- held-out：沿用 preference pilot v1 已冻结的 12 个 pair/6 个 scene，复制为本实验的 `heldout_pairs.jsonl` 并重新计算 SHA256；不读取 frozen-240。
- M1 validation：沿用同一批 8 个固定 ID，复制为 `m1_validation.jsonl` 并重新计算 SHA256；只用于固定评估，不调参。
- 两个评估集分别报告，不合并平均。

### 4.2 C 臂 serialization SFT 集

数据来源只能是：

1. M1 train 中与 stress-v2 审计通过记录对应的 legal chosen/gold；
2. stress-v2 `PAIR_SCORES`/preference manifest 中 `audit_status=passed`、`ambiguous=false` 的 chosen。

每条训练记录必须保留：`source_id`、`source_scene`、`pair_id`、`chosen_sha256`、来源文件 SHA256、prompt hash、target hash 和生成时间。训练 target 是 canonical、唯一的 `AgentRequest` JSON；不得把 rejected 序列写入 C 的 target 字段。

构造规则：

- 先排除 held-out source IDs、M1 validation IDs 和任何 frozen-240 ID；
- 按 `source_id`、`source_scene`、`chosen_sha256`、canonical JSON 去重；
- 训练/评估不得共享 source scene；
- 记录 `train_source_ids ∩ heldout_source_ids`、`train_source_ids ∩ m1_validation_ids`、`train_source_ids ∩ frozen_ids`，三者必须为空；
- 保存 `DATA_MANIFEST.json`、`SPLIT_AUDIT.json` 和 `serialization_train.jsonl`。

## 5. 在线 schema decoder

B 臂复用 `AgentRequestPrefixParser`、`SchemaConstrainedLogitsProcessor` 与 `CompleteJsonEosLogitsProcessor`：

1. 每个生成 step 解码当前 completion prefix；
2. 用 parser 检查 JSON、字段、枚举、tool 名、argument 类型和 workflow 结构；
3. 对候选 token 逐个试探，仅保留能形成合法 prefix 的 token；
4. 顶层对象完整且通过 `AgentRequest.from_dict` 时，只允许 EOS；
5. 到达 token budget 仍未完成时记录 `clipped=true`，不得补全或修复。

报告中必须出现 `decoder_active=true`、`token_masking=true`、`posthoc_repair=false`、`candidate_filtering=false` 和 processor 类名。preflight 需要用一个故意会诱发非法 token 的 toy prompt 验证非法 token 被 mask，而不是只检查 import。

## 6. C 臂训练与 checkpoint

- 建议 8 个 optimizer steps、batch 1、gradient accumulation 4、LoRA learning rate `5e-6`、weight decay `0`、max length `4096`；最终数值以 `CONFIG_FREEZE.json` 为准。
- 训练目标只计算 assistant target token 的 causal LM loss。
- 在 step 4 保存 checkpoint，释放模型后 reload，检查 optimizer/state/adapter hash，再完成 step 8。
- 保存 `TRAIN_SCHEDULE.json`、`TRAINING_LOG.json`、`checkpoint-4/`、`checkpoint-8/`、`CHECKPOINT_MANIFEST.json`；记录 initial/final adapter SHA256 和 resume 验证结果。
- A/B 不更新 adapter；其 adapter hash 必须与初始 LoRA 完全一致。

## 7. 指标

每个 arm/seed/评估集保存逐样本 prediction 和结构化报告：

- `strict_legality_rate`：解析成功、EOS 正确、无 clipping、通过 `AgentRequest.from_dict`；
- `parse_rate`、`eos_rate`、`clipping_rate`、completion token length；
- Reward A、Reward B 及各 component；
- schema/action/tool/argument/workflow/stop 字段准确率；
- exact match；
- equivalence preservation：对 stress-v2 等价控制样本比较 canonical semantics，作为独立控制，不将 gold 强行作为模型预测；
- C 的 `train_source_id_exact_match_rate`，用于排查 train-ID 记忆。

所有指标按 held-out 与 M1 validation 分开汇总，并给出三 seed 均值、标准差、每 seed 明细。无效 completion 的 Reward A/B 必须记为 0，不能让 reward adapter 异常中断评估。

## 8. Preflight 放行门槛

在任何 pilot 训练前执行 `preflight_vaguehydro_legality_repair_pilot_v1.py`，以下检查全部 PASS 才能运行：

- 数据源和 split hash 可复现，训练/held-out/M1/frozen ID 无交集；
- 只存在 A/B/C，D 明确 disabled；
- A/B/C 使用同一 prompt、seed、token budget 和 evaluator；
- A 为真实 unconstrained generation；
- B 的 processor 在实际 `generate()` 路径生效，存在在线 token masking 证据；
- C serialization SFT 可完成 forward/backward；
- checkpoint 保存、reload、hash 和 resume 均成功；
- 评估入口没有 gold completion、forced completion、post-hoc repair 或 candidate filtering；
- GPU、显存、磁盘预算和代码依赖 hash 已记录；
- 旧实验目录和 frozen-240 读取计数均为 0。

产物：`PREFLIGHT_REPORT.json`、`PREFLIGHT_REPORT.md`、`CONFIG_FREEZE.json`、`DATA_MANIFEST.json`、`SPLIT_AUDIT.json`、`PRE_REGISTERED_PROTOCOL.md`。

## 9. Pilot 放行门槛

聚合脚本只在以下条件同时满足时输出 `PASS_ELIGIBLE_FOR_HN_SFT_RETEST`：

1. 至少一个修复臂（B 或 C）在 held-out 和 M1 validation 两个集合上的 strict legality 都高于 A，且绝对值 `>= 0.80`；
2. 至少两个 seed 达到上述修复条件；
3. 修复臂 Reward A、Reward B 均非零，并达到预注册阈值 `>= 0.50`；
4. B 没有 post-hoc repair/filtering；
5. C 的 train-ID exact match rate 不超过预注册上限 `0.20`；
6. 所有审计、checkpoint hash、split audit 和环境记录完整。

否则输出 `BLOCKED_NO_HN_SFT_RETEST`，只能形成诊断结论，不得自动启动 hard-negative SFT 或正式 GRPO。

## 10. 目录与交付物

```text
runs/hydro_remote_agent/vaguehydro_legality_repair_pilot_v1/
├─ PRE_REGISTERED_PROTOCOL.md
├─ CONFIG_FREEZE.json
├─ DATA_MANIFEST.json
├─ SPLIT_AUDIT.json
├─ serialization_train.jsonl
├─ heldout_pairs.jsonl
├─ m1_validation.jsonl
├─ PREFLIGHT_REPORT.json / .md
├─ arm_A/seed_*/ARM_SEED_REPORT.json / .md
├─ arm_B/seed_*/ARM_SEED_REPORT.json / .md
├─ arm_C/seed_*/ARM_SEED_REPORT.json / .md
├─ PILOT_REPORT.json / .md
├─ EXPERIMENT_AUDIT.json / .md
├─ RESULT_TO_CLAIM.json / .md
└─ GAP_LIST.md
```

建议脚本：

- `prepare_vaguehydro_legality_repair_pilot_v1.py`
- `preflight_vaguehydro_legality_repair_pilot_v1.py`
- `run_vaguehydro_legality_repair_arm_v1.py`
- `launch_vaguehydro_legality_repair_pilot_v1.py`
- `aggregate_vaguehydro_legality_repair_pilot_v1.py`
- `seal_vaguehydro_legality_repair_pilot_v1.py`

## 11. 解释边界

即使 B 达到 100% strict legality，也只能说明 schema decoder 能保证可解析输出，不能证明模型语义规划正确；只有 Reward A/B、字段准确率、exact match 和 equivalence preservation 同时改善，才可声称“合法性修复没有以语义退化为代价”。若只有 C 改善而 B 不改善，结论应写成“serialization SFT 有效”；若只有 B 改善，结论应写成“推理约束有效”，不能泛化为 LoRA 学习能力提升。
