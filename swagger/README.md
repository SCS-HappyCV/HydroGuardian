# HydroGuardian 前端接口需求（按业务分组）

本目录用于沉淀前端业务页面所需的后端接口草案。每个业务目录下提供一个 `swagger.json`（OpenAPI 3.0）文件，便于：
- 后端实现前统一接口契约
- 前后端联调时对齐字段与分页参数
- 后续生成 API 文档或 SDK

## 总 Swagger

- `swagger.json`：合并后的总接口文件，包含 Bearer/JWT 鉴权与统一错误码规范

## 目录索引

- `00-公共基础数据/swagger.json`
- `01-首页与全局总览/swagger.json`
- `02-任务工作坊与执行监控/swagger.json`
- `03-风险分析区/swagger.json`
- `04-工单中心/swagger.json`
- `05-历史回溯与对比/swagger.json`
- `06-知识库与规则管理/swagger.json`
- `07-用户权限与系统设置/swagger.json`
- `08-认证与会话/swagger.json`

## 约定

- 统一前缀：`/api/v1`
- 统一返回：`code/message/traceId/data`
- 分页参数：`page`、`pageSize`
- 时间字段：ISO8601，例如 `2026-05-26T10:00:00Z`

> 说明：当前为需求草案，后续可根据后端落地方案调整路径、字段与鉴权方式。
