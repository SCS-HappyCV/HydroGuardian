# HydroGuardian

HydroGuardian 是一个“水利隐患发现与处置闭环”项目，包含：
- `backend`：多服务后端（gRPC + HTTP 网关 + 中间件）
- `web`：Astro + Vue 3 前端控制台

## 仓库结构

```text
HydroGuardian/
├─ backend/   # 后端服务与 docker-compose
├─ web/       # 前端项目
└─ README.md
```

## 环境要求

- Docker Desktop（建议已配置镜像加速）
- Node.js 20+
- pnpm 9+

## 快速启动

### 1) 启动后端

```bash
cd backend
docker compose up -d
```

开发热更新模式（后端服务代码映射 + 自动重启）：

```bash
docker compose watch
```

后端主要入口：
- API Gateway: `http://localhost:8080`
- Agent gRPC: `localhost:9091`
- Case gRPC: `localhost:9092`
- File gRPC: `localhost:9093`
- Nacos: `http://localhost:8848/nacos`
- MySQL(宿主机): `localhost:33069`

说明：
- 中间件数据与配置持久化在 `backend/data/`
- `docker compose down -v` 不会删除 `backend/data/` 中的绑定目录数据

### 2) 启动前端

```bash
cd web
pnpm install
pnpm dev
```

默认访问（以终端输出为准）：`http://localhost:4321`

前端构建：

```bash
pnpm build
pnpm preview
```

## 文档导航

- 后端总览：`backend/README.md`
- 后端架构与规范：`backend/docs/README.md`
- 前端说明：`web/README.md`

## 常见问题

- 拉取镜像失败（EOF）：先看 `backend/docs/docker.md`，配置镜像加速或使用加速源镜像。
- 端口冲突：检查本机占用端口（如 `8080/9091/9092/9093/33069`）后重启容器。
