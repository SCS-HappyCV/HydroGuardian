# HydroGuardian Web

HydroGuardian 前端项目，基于 **Astro + Vue 3 + Tailwind CSS**，当前以静态站点方式构建，页面主要用于任务编排、风险分析、工单流转和系统管理的可视化演示。

## 技术栈

- Astro 5（静态构建）
- Vue 3（页面交互组件）
- Tailwind CSS + reka-ui 组件体系
- TypeScript
- 本地数据层：`src/data/*Service.ts` + `localStorage`

## 目录结构

```text
web/
├─ src/
│  ├─ pages/                 # Astro 页面入口（最终产出 *.html）
│  ├─ layouts/               # Base/Standard/Detail 布局
│  ├─ components/            # 业务组件与通用 UI 组件
│  ├─ data/                  # Mock 数据与 Service 封装
│  ├─ styles/global.css      # 全局样式与设计令牌
│  └─ lib/utils.ts           # 工具函数（如 cn）
├─ scripts/inject-source-info.ts   # 构建时注入 source 信息
├─ astro.config.mjs
├─ tailwind.config.mjs
└─ package.json
```

## 本地开发

```bash
cd web
pnpm install
pnpm dev
```

默认启动 Astro 开发服务（通常是 `http://localhost:4321`）。

## 构建与预览

```bash
pnpm build
pnpm preview
```

- 当前配置为 `output: "static"`，构建产物是静态 HTML/JS/CSS。
- 根路由 `index.astro` 直接渲染首页 `HomePage.vue`。

## 页面说明（主要模块）

- `dashboard.astro`：全局总览
- `task-studio.astro`：任务工作坊
- `task-execution-monitor.astro`：任务执行监控
- `risk-workspace.astro`：风险分析区
- `workorder-center.astro` / `workorder-detail.astro` / `workorder-review.astro`：工单闭环
- `history*.astro`：历史回溯与对比
- `knowledge.astro` / `template-editor.astro` / `rule-editor.astro`：知识与模板管理
- `settings.astro` / `system-health.astro` / `user-perm-management.astro`：系统侧管理

## 数据层现状

- 当前前端没有直接调用后端 API。
- 业务数据主要在 `src/data/*Service.ts` 中以内存数组初始化，并提供：
  - `getAll/getById/query` 查询能力
  - `loadPersisted/savePersisted` 的本地持久化能力（`localStorage`）
- 适合原型开发和联调前阶段；后续可逐步替换为真实 API 请求。

## 开发约定

- 页面间导航统一使用 `*.html` 相对路径（例如 `./task-studio.html`）。
- 交互型 Vue 组件通过 `client:load` 挂载。
- 若代码中引用了不存在的页面，构建后会由 `astro.config.mjs` 的自定义集成自动重定向到 `placeholder.html`，避免 404。
