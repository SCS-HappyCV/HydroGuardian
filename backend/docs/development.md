# 开发规范

## 目录

- `src/main/proto/`：Java 服务 proto
- `grpc/`：gRPC 实现
- `entity/`：实体
- `mapper/`：Mapper
- `dto/`：DTO
- `main.py`：Python 服务入口

## Proto

- package：`hydro.<domain>.v1`
- `java_package`：`com.hydro.grpc.<domain>v1`
- 字段名：`snake_case`
- 变更原则：优先追加字段，不要重命名老字段

## gRPC 生成代码

- `src/main/proto/*.proto` 是唯一接口定义源
- Maven 在构建阶段自动生成 Java 消息类和 `*Grpc` 服务基类
- 生成代码通常位于 `target/generated-sources/`，不要手工修改
- 业务实现类只负责 `extends ...ImplBase` 并实现具体方法
- 修改接口时先改 `proto`，再重新构建生成代码，最后调整业务实现

## 返回

- HTTP 成功：`code=0`
- HTTP 错误：`40000/40400/50200/50000`
- HTTP 必带 `traceId`
- gRPC：`INVALID_ARGUMENT / NOT_FOUND / UNAVAILABLE / INTERNAL`

## 约定

- 新增接口必须先改 proto，再改实现，再改文档
- 内部服务不再新增 REST 接口
- 业务逻辑不放在 controller 里
- gRPC 服务直接返回标准 status，不抛裸异常
- 服务间 gRPC 地址通过 Nacos 服务发现获取

## 中间件数据与配置
中间件的数据和配置都改为映射
- MySQL：./data/mysql/data、./data/mysql/init、./data/mysql/conf/my.cnf
- Nacos：./data/nacos/data、./data/nacos/logs、./data/nacos/conf/custom.properties
- Redis：./data/redis/data、./data/redis/conf/redis.conf（并启用自定义配置启动）
- RabbitMQ：./data/rabbitmq/data、./data/rabbitmq/conf/rabbitmq.conf
- MinIO：./data/minio/data、./data/minio/conf
MySQL 的初始化 SQL 只会在数据目录首次为空时执行一次。
