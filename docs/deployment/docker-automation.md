# Pixelle-Video Docker 自动化部署方案

本方案按 `geo-platform` 已跑通的方式实现，不使用 GitHub Actions 构建镜像，也不使用 systemd Python webhook。

## 部署目标

- 生产分支：`dev`。
- GitHub Actions：只做基础检查和飞书“ACR 构建中”通知。
- ACR：从 GitHub `dev` 分支自动构建镜像。
- 服务器：通过 Docker webhook 容器接收 ACR webhook。
- 宝塔：反代网页端和 webhook。
- 飞书：GitHub push 通知 + 服务器部署结果通知。

## 服务

```text
pixelle-web      React 静态页面 + Nginx，宿主机 127.0.0.1:18080
pixelle-api      FastAPI 后端，宿主机 127.0.0.1:8000
pixelle-streamlit 旧 Streamlit 页面，可选启动，宿主机 127.0.0.1:8501
pixelle-webhook  接收 ACR webhook，宿主机 0.0.0.0:9877/deploy
```

容器内部端口：

```text
web: 8080
api: 8000
streamlit: 8501
webhook: 9877
```

宿主机端口：

```text
WEB_PORT=18080
API_PORT=8000
STREAMLIT_PORT=8501
WEBHOOK_PORT=9877
```

`18080` 和 `9877` 是为了避开 `geo-platform` 已使用的 `8080` 和 `9876`。

## 核心文件

```text
Dockerfile.api
Dockerfile.web
Dockerfile.streamlit
Dockerfile.webhook
docker-compose.prod.yml
scripts/deploy.sh
scripts/rollback.sh
scripts/webhook-server.js
.github/workflows/deploy.yml
.env.example
docs/deployment/web-auto-deploy-runbook.md
```

## ACR 镜像

```text
acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech/pixelle-video-web:${IMAGE_TAG}
acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech/pixelle-video-api:${IMAGE_TAG}
acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech/pixelle-video-streamlit:${IMAGE_TAG}
```

两个 ACR 仓库都监听 GitHub `dev` 分支，tag 规则一致：

```text
${Branch}-${CommitID}
```

`pixelle-video-web`：

```text
Dockerfile: Dockerfile.web
构建上下文: /
构建架构: linux/amd64
构建参数:
  NODE_BASE=node:20-alpine
  NGINX_BASE=nginx:alpine
  VITE_API_BASE_URL=/api
Webhook: https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

建议 web 镜像显式使用 `Dockerfile.web`。为了兼容 ACR 默认读取根目录 `Dockerfile` 的情况，根 `Dockerfile` 也已经改为 React Web 镜像入口。旧的一体化 Python 镜像入口保留在 `Dockerfile.legacy`。

`pixelle-video-api`：

```text
Dockerfile: Dockerfile.api
构建上下文: /
构建架构: linux/amd64
构建参数:
  PYTHON_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/python:3.11-slim
  USE_CN_MIRROR=true
Webhook: https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

`pixelle-video-streamlit`（可选旧页面）：

```text
Dockerfile: Dockerfile.streamlit
构建上下文: /
构建架构: linux/amd64
构建参数:
  PYTHON_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/python:3.11-slim
  USE_CN_MIRROR=true
Webhook: 仅当 DEPLOY_STREAMLIT=true 时配置同一个 webhook
```

默认生产部署不等待、不拉取、不启动 Streamlit 镜像。需要旧页面时：

```env
DEPLOY_STREAMLIT=true
STREAMLIT_HOST=127.0.0.1
STREAMLIT_PORT=8501
```

并在 ACR 建立 `pixelle-video-streamlit` 仓库，tag 规则与 web/api 一致。如果开启 `DEPLOY_STREAMLIT=true`，必须给 streamlit 仓库也配置同一个 webhook，否则 webhook 会等待 5 分钟后才超时触发。

`pixelle-video-streamlit` 是旧页面轻量入口镜像，不再安装 `moviepy`、`comfykit`、`playwright` 这类完整生产依赖。生产生成链路以 React Web + FastAPI API 镜像为准；旧页面主要用于回看、配置和临时调试。

如果构建日志里出现 `manylinux...aarch64`，说明该 ACR 仓库仍在按 ARM64 构建。服务器通常是 x86/amd64 时必须把 ACR 构建规则改为 `linux/amd64`，否则下载包会变慢，镜像也可能无法在服务器运行。

ACR 构建规则里按 geo-platform 的方式使用构建参数覆盖基础镜像：

```text
NODE_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/node:20-alpine
NGINX_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/nginx:alpine
PYTHON_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/python:3.11-slim
```

镜像 tag 必须按 ACR 实际已有版本填写；例如 nginx 仓库如果只有 `alpine`，就配置为 `.../nginx:alpine`。

如果 ACR 没有产生最新 tag，先检查构建规则是否绑定当前仓库和分支：

```text
代码源: rankai/Pixelle-Video
分支: dev
触发方式: 代码变更自动构建 / push
最新提交: 以 GitHub dev 当前 SHA 为准
```

## Webhook 行为

`scripts/webhook-server.js` 与 `geo-platform` 的 webhook 模式一致：

- 监听 `POST /deploy?token=...`
- 校验 `DEPLOY_WEBHOOK_SECRET`
- 接收 ACR payload 中的 `repository.name` 和 `push_data.tag`
- 只处理：
  - `pixelle-video-web`
  - `pixelle-video-api`
  - `pixelle-video-streamlit`（仅 `DEPLOY_STREAMLIT=true` 时）
- 同一 tag 收齐两个镜像后执行：

```bash
IMAGE_TAG=<tag> ./scripts/deploy.sh
```

如果 5 分钟未收齐，也会按 geo-platform 的策略强制触发部署，避免单个 webhook 丢失导致永远卡住。

## 服务器 .env

```env
IMAGE_TAG=latest
REGISTRY=acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech
PROJECT_DIR=/opt/pixelle-video
COMPOSE_PROJECT_NAME=pixelle-video

WEB_HOST=127.0.0.1
WEB_PORT=18080
API_PORT=8000
STREAMLIT_HOST=127.0.0.1
STREAMLIT_PORT=8501
TZ=Asia/Shanghai
USE_CN_MIRROR=true
VITE_API_BASE_URL=/api
NODE_BASE=node:20-alpine
NGINX_BASE=nginx:alpine
PYTHON_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/python:3.11-slim
DEPLOY_STREAMLIT=false

ACR_USERNAME=
ACR_PASSWORD=
FEISHU_WEBHOOK_URL=

DEPLOY_WEBHOOK_SECRET=
WEBHOOK_PORT=9877
```

## 宝塔反代

网页端：

```text
http://127.0.0.1:18080
```

旧 Streamlit 页面（可选）：

```text
http://127.0.0.1:8501
```

ACR webhook：

```text
/deploy -> http://127.0.0.1:9877/deploy
```

ACR webhook URL：

```text
https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

## 首次启动

```bash
cd /opt/pixelle-video
cp .env.example .env
cp config.example.yaml config.yaml
mkdir -p data output temp logs
docker compose -f docker-compose.prod.yml up -d webhook
```

验证 webhook：

```bash
curl http://127.0.0.1:9877/healthz
```

首次部署：

```bash
IMAGE_TAG=dev-xxxxxxx ./scripts/deploy.sh
```

验证网页：

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/api/tasks
```

手动启动旧 Streamlit 页面：

```bash
DEPLOY_STREAMLIT=true IMAGE_TAG=dev-xxxxxxx ./scripts/deploy.sh
curl http://127.0.0.1:8501/_stcore/health
```

## 日常发布

```bash
git push origin dev
```

后续由 GitHub Actions、ACR、webhook、deploy.sh 自动完成。
