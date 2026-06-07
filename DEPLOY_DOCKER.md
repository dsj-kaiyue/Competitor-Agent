# Docker Compose 部署说明

本文档用于说明如何在一台 Linux 服务器上使用 Docker Compose 一键部署本项目。

当前部署方案会同时启动前端、后端 API、Celery Worker、MySQL、Redis、Milvus standalone，以及 Milvus 依赖的 etcd 和 MinIO。服务器不需要提前安装 MySQL、Redis、Milvus 或 Nginx，只需要安装 Docker Engine 和 Docker Compose v2。

## 1. 部署架构

`docker-compose.yml` 会启动以下长期运行的容器：

| 服务 | 容器职责 | 是否对外暴露 |
| --- | --- | --- |
| `frontend` | Nginx 容器，托管前端页面并反向代理 API | 是，默认 `80` |
| `api` | FastAPI 后端服务 | 否，由 `frontend` 反向代理 |
| `worker` | Celery 后台任务 Worker | 否 |
| `mysql` | 项目业务数据库 | 否 |
| `redis` | Celery Broker 和结果缓存 | 否 |
| `milvus` | 向量数据库 standalone | 默认暴露 `19530`、`9091` |
| `etcd` | Milvus 元数据依赖 | 否 |
| `minio` | Milvus 对象存储依赖 | 默认暴露 `9000`、`9001` |

另外还有一个一次性容器：

| 服务 | 容器职责 |
| --- | --- |
| `migrate` | 执行数据库迁移 `python -m alembic upgrade head`，执行完成后退出 |

说明：

- 本文中的 “Nginx” 是 Docker 容器里的 Nginx，不需要在宿主机上安装 Nginx。
- Docker Compose 使用的是 “container”，不是 Kubernetes 的 “pod”。
- 默认部署面向单服务器场景，所有服务运行在同一台服务器上。

## 2. 服务器要求

服务器建议配置：

- Linux x86_64
- Docker Engine
- Docker Compose v2
- 建议至少 4 核 CPU、8 GB 内存
- 建议准备足够磁盘空间用于 MySQL、Milvus、MinIO 数据卷

确认 Docker 和 Compose 是否可用：

```bash
docker version
docker compose version
```

如果当前用户没有 Docker 权限，可以使用 `sudo docker ...` 和 `sudo docker compose ...` 执行命令。

## 3. 端口说明

默认端口如下：

| 端口 | 用途 | 是否建议开放公网 |
| --- | --- | --- |
| `80` | Web 页面和 API 入口 | 是 |
| `19530` | Milvus 服务端口 | 仅外部工具需要直连 Milvus 时开放 |
| `9091` | Milvus 健康检查端口 | 否 |
| `9000` | MinIO API | 否 |
| `9001` | MinIO 控制台 | 否 |

如无特殊需求，公网安全组只需要开放 `80`。

MySQL 和 Redis 没有映射宿主机端口，因此不会和服务器上已有的 systemctl Redis 或 MySQL 端口冲突。

## 4. 准备项目文件

将项目代码上传到服务器，例如：

```bash
cd /home/ubuntu/code
git clone <your-repo-url> Competitor-Agent
cd Competitor-Agent
```

如果不是通过 Git 上传，也需要确保服务器项目根目录包含以下文件：

```text
docker-compose.yml
.env.docker.example
backend/Dockerfile
frontend/Dockerfile
frontend/nginx.conf
milvus/user.yaml
```

## 5. 配置环境变量

在服务器项目根目录创建生产环境配置：

```bash
cp .env.docker.example .env.docker
```

编辑 `.env.docker`：

```bash
nano .env.docker
```

至少需要修改以下配置：

```env
AUTH_SECRET_KEY=换成一串足够长的随机密钥

MYSQL_ROOT_PASSWORD=换成强密码
MYSQL_PASSWORD=换成强密码
DATABASE_URL=mysql+pymysql://competitor_agent:这里要和MYSQL_PASSWORD一致@mysql:3306/competitor_agent?charset=utf8mb4

FIRECRAWL_API_KEY=你的Firecrawl Key

LLM_BASE_URL=你的LLM接口地址
LLM_API_KEY=你的LLM Key
LLM_MODEL=你的LLM模型名

EMBEDDING_BASE_URL=你的Embedding接口地址
EMBEDDING_API_KEY=你的Embedding Key
EMBEDDING_MODEL=你的Embedding模型名
EMBEDDING_DIM=你的Embedding维度
```

### 5.1 Milvus 配置

默认 Compose 会在服务器上启动一套新的 Milvus：

```env
MILVUS_URI=http://milvus:19530
MILVUS_TOKEN=root:Milvus
MILVUS_COLLECTION=evidence_chunks
```

`MILVUS_URI=http://milvus:19530` 是容器内部服务名地址。即使宿主机端口改成 `19531:19530`，应用容器内部仍然应使用这个地址。

当前 `milvus/user.yaml` 开启了 Milvus 鉴权：

```yaml
common:
  security:
    authorizationEnabled: true
```

因此默认 token 使用 Milvus standalone 初始账号：

```env
MILVUS_TOKEN=root:Milvus
```

如果后续修改了 Milvus root 密码，需要同步修改 `.env.docker` 中的 `MILVUS_TOKEN`。

### 5.2 构建镜像源配置

`.env.docker.example` 默认使用腾讯云 CVM 访问较快的镜像源：

```env
APT_DEBIAN_MIRROR=http://mirrors.tencentyun.com/debian
APT_DEBIAN_SECURITY_MIRROR=http://mirrors.tencentyun.com/debian-security
PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
PIP_TRUSTED_HOST=mirrors.cloud.tencent.com
NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/
```

如果部署在其他云厂商或海外服务器，可以改成对应云厂商镜像源，也可以改回官方源：

```env
APT_DEBIAN_MIRROR=http://deb.debian.org/debian
APT_DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
PIP_INDEX_URL=https://pypi.org/simple
PIP_TRUSTED_HOST=pypi.org
NPM_REGISTRY=https://registry.npmjs.org/
```

## 6. 首次启动

在服务器项目根目录执行：

```bash
docker compose --env-file .env.docker up -d --build
```

如果需要 sudo：

```bash
sudo docker compose --env-file .env.docker up -d --build
```

首次启动会自动完成：

- 构建后端镜像
- 构建前端 Nginx 镜像
- 拉取 MySQL、Redis、Milvus、etcd、MinIO 镜像
- 创建 Docker 数据卷
- 启动 MySQL、Redis、Milvus 等基础服务
- 执行 Alembic 数据库迁移
- 启动 API、Worker、Frontend

启动完成后访问：

```text
http://服务器IP/
```

健康检查地址：

```text
http://服务器IP/health
```

## 7. 初始化账号

API 服务启动时会自动初始化默认用户。

默认账号包括：

| 用户名 | 密码 | 说明 |
| --- | --- | --- |
| `Admin` | `Admin` | 管理员用户 |
| `User1` | `User1` | 测试用户 |
| `User2` | `User2` | 测试用户 |
| `User3` | `User3` | 测试用户 |

如果这些账号已经存在，启动逻辑不会覆盖已有账号的密码和状态。

生产环境上线后建议尽快修改默认密码，或在确认不需要测试用户后删除测试账号。

## 8. 验证部署

查看容器状态：

```bash
docker compose --env-file .env.docker ps
```

正常情况下，以下服务应处于 running 或 healthy 状态：

```text
frontend
api
worker
mysql
redis
milvus
etcd
minio
```

检查健康接口：

```bash
curl http://127.0.0.1/health
```

预期返回：

```json
{"status":"ok"}
```

查看关键日志：

```bash
docker compose --env-file .env.docker logs -f api worker frontend milvus
```

如果使用 sudo：

```bash
sudo docker compose --env-file .env.docker logs -f api worker frontend milvus
```

## 9. 常用运维命令

查看服务状态：

```bash
docker compose --env-file .env.docker ps
```

查看所有日志：

```bash
docker compose --env-file .env.docker logs -f
```

查看某个服务日志：

```bash
docker compose --env-file .env.docker logs -f api
```

重启服务：

```bash
docker compose --env-file .env.docker restart api worker frontend
```

重新构建并启动后端：

```bash
docker compose --env-file .env.docker up -d --build api worker
```

重新构建并启动全部服务：

```bash
docker compose --env-file .env.docker up -d --build
```

手动执行数据库迁移：

```bash
docker compose --env-file .env.docker run --rm migrate
```

停止服务但保留数据卷：

```bash
docker compose --env-file .env.docker down
```

停止服务并删除数据卷：

```bash
docker compose --env-file .env.docker down -v
```

`down -v` 会删除 MySQL、Redis、Milvus、MinIO、etcd 的数据卷。生产环境慎用。

## 10. 数据持久化

Compose 使用 Docker named volumes 保存数据：

| 数据卷 | 保存内容 |
| --- | --- |
| `mysql_data` | MySQL 业务数据 |
| `redis_data` | Redis AOF 数据 |
| `milvus_data` | Milvus 本地数据 |
| `milvus_etcd_data` | Milvus etcd 元数据 |
| `milvus_minio_data` | Milvus MinIO 对象数据 |

只要不执行 `docker compose down -v` 或手动删除 Docker volume，重启容器不会丢失数据。

建议定期备份：

- MySQL 数据库
- Milvus 相关数据卷
- `.env.docker`

## 11. 从 Windows 本机 MySQL 迁移数据

生产环境不建议让服务器容器直接连接 Windows 本机 MySQL。推荐将数据导入 Compose 内的 MySQL。

在 Windows 本机导出：

```powershell
mysqldump -uroot -p --default-character-set=utf8mb4 competitor_agent > competitor_agent.sql
```

上传到服务器项目目录后导入：

```bash
docker compose --env-file .env.docker exec -T mysql mysql -ucompetitor_agent -p competitor_agent < competitor_agent.sql
```

如果数据库已有数据，导入前请先备份，避免覆盖生产数据。

## 12. 关于外部 Redis、MySQL 或 Milvus

默认部署方案使用 Compose 内置的 MySQL、Redis 和 Milvus，这是推荐的单服务器部署方式。

如果确实要连接外部服务，可以修改 `.env.docker`：

```env
DATABASE_URL=mysql+pymysql://用户名:密码@数据库地址:3306/数据库名?charset=utf8mb4
CELERY_BROKER_URL=redis://Redis地址:6379/0
CELERY_RESULT_BACKEND=redis://Redis地址:6379/1
MILVUS_URI=http://Milvus地址:19530
MILVUS_TOKEN=用户名:密码
```

如果使用外部服务，还应同步调整 `docker-compose.yml` 中的依赖关系，避免 `api` 和 `worker` 继续等待 Compose 内部的 `mysql`、`redis` 或 `milvus` 健康检查。

## 13. 已有服务和端口冲突

如果服务器上已经有旧的 Milvus、MinIO 或其他服务占用了端口，Compose 启动时会报端口冲突。

可在 `.env.docker` 中调整宿主机端口：

```env
MILVUS_PORT=19531
MILVUS_HEALTH_PORT=9092
MINIO_API_PORT=9010
MINIO_CONSOLE_PORT=9011
WEB_PORT=8088
```

注意：

- 改 `MILVUS_PORT` 只影响宿主机访问 Milvus 的端口。
- 应用容器内部仍然通过 `MILVUS_URI=http://milvus:19530` 访问 Milvus。
- Redis 没有映射宿主机端口，因此不会和 systemctl 启动的宿主机 Redis 冲突。
- MySQL 没有映射宿主机端口，因此不会和宿主机 MySQL 冲突。

## 14. 更新部署

更新代码后，在服务器项目根目录执行：

```bash
git pull
docker compose --env-file .env.docker up -d --build
```

如果使用 sudo：

```bash
git pull
sudo docker compose --env-file .env.docker up -d --build
```

该命令会重新构建有变化的镜像，并保持数据卷不变。

## 15. 故障排查

### 15.1 apt-get update 很慢或卡住

确认 `.env.docker` 中的镜像源适合当前服务器网络。

腾讯云服务器建议使用：

```env
APT_DEBIAN_MIRROR=http://mirrors.tencentyun.com/debian
APT_DEBIAN_SECURITY_MIRROR=http://mirrors.tencentyun.com/debian-security
```

其他云服务器可以改成官方源或对应云厂商镜像源。

### 15.2 前端能打开，但接口报错

查看 API 日志：

```bash
docker compose --env-file .env.docker logs -f api
```

重点检查：

- `.env.docker` 中 LLM、Embedding、Firecrawl 配置是否正确
- MySQL 是否 healthy
- Milvus 是否 healthy
- 数据库迁移是否成功

### 15.3 Worker 没有执行任务

查看 Worker 日志：

```bash
docker compose --env-file .env.docker logs -f worker
```

重点检查：

- Redis 是否 healthy
- `CELERY_BROKER_URL` 是否为 `redis://redis:6379/0`
- API 和 Worker 是否使用同一份 `.env.docker`

### 15.4 Milvus 启动失败

查看 Milvus、etcd、MinIO 日志：

```bash
docker compose --env-file .env.docker logs -f milvus etcd minio
```

常见原因：

- 服务器内存不足
- `9000`、`9001`、`19530`、`9091` 端口冲突
- Milvus 数据卷损坏或版本不兼容

### 15.5 端口 80 被占用

如果服务器已有 Nginx、Apache 或其他服务占用 `80`，可以修改：

```env
WEB_PORT=8088
```

然后重新启动：

```bash
docker compose --env-file .env.docker up -d
```

访问地址变为：

```text
http://服务器IP:8088/
```

## 16. 生产环境安全建议

上线前建议完成以下事项：

- 修改 `.env.docker` 中所有默认密码和密钥。
- 修改默认管理员账号密码。
- 删除或禁用不需要的测试用户。
- 公网安全组只开放必要端口，通常只开放 `80`。
- 不要将 `.env.docker` 提交到 Git 仓库。
- 定期备份 MySQL 和 Milvus 数据。
- 如需 HTTPS，建议在服务器前置云厂商负载均衡、证书服务，或另行配置反向代理。
