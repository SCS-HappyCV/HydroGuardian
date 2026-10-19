# HydroGuardian（河图智巡）

HydroGuardian 是面向水利遥感巡查的多模态专家 Agent 系统。系统将自然语言巡查需求编译为结构化 `AgentRequest`，按任务需要调用点云语义分割、双时相变化检测、语言引导三维定位、几何分析和质量验证专家，并将通过验证的算法产物组织为证据、候选风险和现场工单。

项目采用“Agent 控制面 + 独立专家执行面”的架构。核心 Agent 负责理解任务、选择能力、生成参数和规划依赖；影像、点云等大体量数据直接交给外部专家处理，不进入大模型上下文。

## 核心能力

- 将自然语言请求转换为版本化、可校验的 `AgentRequest`。
- 支持 `direct_answer`、`tool_call`、动态多专家 `workflow`、`clarification` 和 `abstain`。
- 通过 ToolSpec 约束工具名称、输入模态、参数范围、产物类型和步骤依赖。
- 支持真实专家调用、Artifact 谱系、独立 Verifier 和任务回放。
- 提供 Web 研判端和 Mobile 现场复核端，形成风险发现、派单、核查、复核和归档闭环。
- 包含 VagueHydro 数据构建、Qwen3-VL LoRA SFT、结构化规划评测及端到端执行评测代码。

## 系统架构

```text
自然语言任务 + 资产清单
          |
          v
VagueHydro Agent（理解、选择、规划）
          |
          v
AgentRequest + ToolSpec Validator
          |
          +---------------- direct_answer / clarification / abstain
          |
          v
Workflow Executor
          |
          +-- GUFNet：点云语义分割
          +-- RFANet：双时相变化检测
          +-- HydroProgram3D：语言引导点云定位
          +-- Geometry：几何与空间关系分析
          +-- Verifier：真实性、完整性和一致性检查
          |
          v
Artifact -> EvidencePack -> RiskCard -> WorkOrder -> 人工复核
```

## 仓库结构

```text
HydroGuardian/
|-- backend/                 # Java/Python 多服务后端与中间件编排
|-- web/                     # Astro + Vue 3 Web 研判端
|-- mobile/                  # Ionic/Vue + Capacitor 现场复核端
|-- hydro_remote_agent/      # Agent 协议、训练、评测、运行时和专家适配器
|-- swagger/                 # API 文档
|-- competition-docs/        # 项目说明、实验口径和比赛材料
|-- figures/                 # 可公开的架构与流程图
`-- README.md
```

## Agent 训练与数据

正式 Agent 以 `Qwen3-VL-8B-Instruct` 为基础，通过 LoRA 监督微调学习结构化 `AgentRequest`。监督目标不是自由文本回答，而是动作类型、专家选择、类型化参数、Workflow 依赖和预期产物组成的严格 JSON。

Gold AgentRequest 由场景标注、任务规则和 ToolSpec 确定性构造；语言模型仅用于生成中英文 L0-L3 自然语言改写，不负责生成 Gold 工作流。相关代码位于：

- `hydro_remote_agent/data/`：规范任务、语言改写和 SFT 数据格式。
- `hydro_remote_agent/schemas/`：AgentAction 与 ToolSpec 协议。
- `hydro_remote_agent/training/`：Qwen3-VL LoRA SFT。
- `hydro_remote_agent/rewards/`：结构化动作规范化与奖励。
- `hydro_remote_agent/evaluation/`：路由、执行和任务质量评测。
- `hydro_remote_agent/tools/`：数据构建、训练、评测和审计入口。

更完整的研究代码说明见 [hydro_remote_agent/README.md](hydro_remote_agent/README.md)。

## 外置资产

仓库不提交模型权重、原始遥感数据、生成数据集、数据库文件和实验运行目录。运行完整系统前需要自行准备：

- Qwen3-VL-8B-Instruct 基础模型与 VagueHydro LoRA Adapter；
- GUFNet、RFANet 和 HydroProgram3D 权重；
- 已授权使用的正射影像、双时相影像和点云；
- VagueHydro 训练数据（需要训练或复现实验时）。

路径通过环境变量、配置文件或 Docker volume 提供。不要把本地绝对路径、API Key 或数据集凭据写入仓库。

## 环境要求

基础应用：

- Docker Desktop / Docker Engine + Compose
- Node.js 20+
- pnpm 9+
- JDK 17（不使用容器构建 Java 服务时）

Agent 和 GPU 专家：

- Python 3.10+
- PyTorch 与目标 CUDA 环境匹配
- NVIDIA Container Toolkit（使用 GPU 容器时）
- 具体依赖见 `hydro_remote_agent/deploy/requirements-*.txt`

## 快速启动

### 1. 启动业务后端

```bash
cd backend
docker compose up -d
```

主要入口：

- API Gateway：`http://localhost:8080`
- Agent gRPC：`localhost:9091`
- Case gRPC：`localhost:9092`
- File gRPC：`localhost:9093`
- Nacos：`http://localhost:8848/nacos`

后端说明见 [backend/README.md](backend/README.md)。

### 2. 启动 Web 端

```bash
cd web
pnpm install
pnpm dev
```

默认地址：`http://localhost:4321`。

生产构建：

```bash
pnpm build
pnpm preview
```

### 3. 启动 Mobile 端

```bash
cd mobile
pnpm install
pnpm dev
```

Android 工程通过 Capacitor 同步：

```bash
pnpm build
npx cap sync android
npx cap open android
```

详见 [mobile/README.md](mobile/README.md)。

### 4. 验证 Agent 核心协议

在仓库根目录创建 Python 环境并安装基础依赖后执行：

```bash
python -m hydro_remote_agent.tools.validate_registry \
  --registry hydro_remote_agent/configs/tool_registry.yaml

python -m pytest hydro_remote_agent/tests/test_vague_hydro_data.py \
  hydro_remote_agent/tests/test_rule_router.py
```

`test_sft_data.py` 依赖未随仓库分发的 `data/vague_hydro/source_manifest.jsonl`；准备完整
VagueHydro 数据后可单独运行该测试。

Agent 服务和分布式 Worker 部署见 [hydro_remote_agent/deploy/README.md](hydro_remote_agent/deploy/README.md)。

## 配置与安全

- 从各模块的 `.env.example` 创建本地 `.env`，不要提交真实凭据。
- 模型权重和数据目录已被 `.gitignore` 排除。
- 对外发布数据前应确认遥感影像、点云、现场照片及地图瓦片的授权与脱敏要求。
- `competition-docs` 中的材料用于说明项目与实验口径，不等同于可执行训练数据。

## 当前边界

- 当前部署的 GUFNet 在线评估路径主要使用点云分支；不能将其描述为已完成在线影像—点云融合推理。
- Verifier 提供质量记录和诊断覆盖，不替代水利专业人员作最终工程判断。
- 算法输出是候选风险或待复核线索，风险定级和处置由人工闭环确认。
- 完整复现依赖未随仓库分发的模型权重和授权数据。

## 文档导航

- [Agent 研究与运行说明](hydro_remote_agent/README.md)
- [Agent 架构与部署指南](hydro_remote_agent/PROJECT_ARCHITECTURE_DEPLOYMENT_GUIDE.md)
- [后端总览](backend/README.md)
- [后端架构文档](backend/docs/README.md)
- [Web 端说明](web/README.md)
- [Mobile 端说明](mobile/README.md)
- [Agent 实验数据表](competition-docs/Agent实验数据表-PPT版.md)
