# HydroGuardian Backend

## 启动

```bash
docker compose up -d
```

## 热更新开发模式

```bash
docker compose up -d
docker compose watch
```

说明：`docker compose watch` 需要在单独终端保持运行，监听到代码变化后会自动重启对应服务（无需再次 `docker compose up --build`）。

如果有报错：
```bash
拉取镜像时报错：error pulling image configuration: download failed after attempts=6: EOF

先单独拉 minio 的镜像加速源并打回原标签
docker pull docker.m.daocloud.io/minio/minio:latest
docker tag docker.m.daocloud.io/minio/minio:latest minio/minio:latest
```

## MySQL 初始化说明

`./data/mysql/init` 目录下的 SQL 只会在 MySQL 数据目录首次初始化时执行一次。
如果容器已经启动过，后续再新增 `001_init.sql`、`002_add_app_user.sql` 这类脚本，不会自动补执行到现有数据库。

如果只是补 `app_user` 表，建议直接手动执行 SQL：

如果需要让 `init` 目录里的脚本重新执行，需要删除当前 MySQL 数据卷或清空 `./data/mysql/data` 后重新初始化。

## 调试

- API Gateway: `http://localhost:8080`
- Agent gRPC: `localhost:9091`
- Case gRPC: `localhost:9092`
- File gRPC: `localhost:9093`
- MinIO Console: `http://localhost:9001` (`hydro` / `hydro12345`)
- RabbitMQ Console: `http://localhost:15672` (`hydro` / `hydro123`)
- Nacos Console: `http://localhost:8848/nacos`

```bash
curl -X POST http://localhost:8080/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d "{\"taskText\":\"筛查近水扰动区域并排序\",\"sceneId\":\"demo-scene-001\",\"debug\":true}"
```

更多规范与架构说明请看 `docs/README.md`。
