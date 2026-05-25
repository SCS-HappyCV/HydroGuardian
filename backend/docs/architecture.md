# 架构说明

## 目标

面向水利隐患闭环处置的 4 服务 MVP。

## 服务边界

- `api-gateway`：对外 HTTP 入站，转发到 agent
- `agent-service`：LangGraph 编排，gRPC 服务
- `case-service`：工单/风险 gRPC 服务
- `file-service`：文件/元数据 gRPC 服务

## 通信

- 对外：HTTP
- 对内：gRPC
- Nacos：用于 `api-gateway`、`agent-service`、`case-service`、`file-service` 的注册发现

## 启动

```bash
docker compose down -v
docker compose up -d --build
```

## 入口

- API Gateway: `http://localhost:8080`
- Agent gRPC: `localhost:9091`
- Case gRPC: `localhost:9092`
- File gRPC: `localhost:9093`
- Nacos: `http://localhost:8848/nacos`

# 相关命令

- 只生成 proto 相关 Java 代码
```bash
mvn protobuf:compile protobuf:compile-custom
```

- 生成 + 编译
```bash
mvn clean compile
```

- 生成 + 打包（项目里 Dockerfile 用的就是这个）
```bash
mvn -DskipTests clean package
```
