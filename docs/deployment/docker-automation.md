# Pixelle-Video Docker 自动化部署方案

## 目标

参考 `geo-platform` 已验证的部署模式，为 Pixelle-Video 建立一套可自动发布、可健康检查、可回滚的 Docker 部署链路。

生产环境目标：

- 前后端一起由 `docker compose` 启动。
- 对外只暴露 React Web 一个入口。
- 后端 FastAPI 由 Nginx 通过 `/api/*` 反代访问。
- 镜像通过阿里云 ACR 发布和拉取。
- ACR 直接从 GitHub 自动构建镜像，本地不构建镜像。
- ACR 构建完成后通过 webhook 通知服务器自动部署。
- 部署脚本具备加锁、拉镜像、启动、健康检查、失败回滚能力。
- 本次只覆盖 Web 生产部署，不覆盖 Windows/Tauri 桌面安装包。

## 生产架构

```text
浏览器
  ↓
pixelle-web:8080
  ├─ React 静态页面
  └─ /api/* 反代到 pixelle-api:8000
        ↓
        FastAPI 后端
        ↓
        config.yaml / data / output / temp
```

用户访问：

```text
http://服务器IP:8080
```

本地开发仍可保留：

```text
React dev server: http://127.0.0.1:5173
FastAPI API:      http://127.0.0.1:8000
```

## 服务拆分

### pixelle-api

职责：

- FastAPI 后端。
- IP 口播生产链路。
- 任务中心。
- 素材资产。
- 配置读写。
- 文件下载。

容器内端口：

```text
8000
```

挂载：

```text
./config.yaml:/app/config.yaml
./data:/app/data
./output:/app/output
./temp:/app/temp
```

健康检查：

```text
GET /health
```

说明：

- `data/desktop_tasks.sqlite` 存储任务中心记录。
- `config.yaml` 继续存储系统配置和密钥。
- `output/` 存储生成结果。
- `temp/` 存储中间文件。
- API 镜像必须包含 FFmpeg、Playwright Chromium、CJK 字体。

### pixelle-web

职责：

- 构建 React 生产包。
- Nginx 托管静态文件。
- Nginx 将 `/api/*` 反代到 `pixelle-api:8000`。

对外端口：

```text
127.0.0.1:${WEB_PORT:-8080}:8080
```

健康检查：

```text
GET /health
```

## ACR 镜像规划

使用阿里云 ACR，沿用 `geo-platform` 的发布方式，但构建动作由 ACR 完成，不在本地构建镜像。

环境变量：

```env
REGISTRY=acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech
IMAGE_TAG=dev-xxxx
```

镜像：

```text
${REGISTRY}/pixelle-video-api:${IMAGE_TAG}
${REGISTRY}/pixelle-video-web:${IMAGE_TAG}
```

ACR 中创建两个镜像仓库：

```text
pixelle-video-api
pixelle-video-web
```

两个仓库都绑定同一个 GitHub 仓库和同一个生产分支，区别是 Dockerfile：

| 镜像仓库 | Dockerfile | 构建上下文 | 关键构建参数 |
| --- | --- | --- | --- |
| `pixelle-video-api` | `Dockerfile.api` | `/` | `USE_CN_MIRROR=true` |
| `pixelle-video-web` | `Dockerfile.web` | `/` | `VITE_API_BASE_URL=/api` |

两个自动构建规则必须使用一致的 tag 规则，推荐：

```text
${Branch}-${CommitID}
```

原因：服务器 webhook 会等待同一个 tag 的 `api` 和 `web` 两个镜像都构建完成后才部署，避免前后端版本不一致。

服务器部署前需要具备 ACR 拉取权限：

```bash
docker login acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com
```

`.env` 可配置：

```env
ACR_USERNAME=xxx
ACR_PASSWORD=xxx
```

部署脚本中如果发现 `ACR_USERNAME` 和 `ACR_PASSWORD`，应在 `docker compose pull` 前自动登录。

## 文件规划

新增文件：

```text
Dockerfile.api
Dockerfile.web
nginx.conf
docker-compose.prod.yml
.env.example
scripts/deploy.sh
scripts/rollback.sh
docs/deployment/docker-automation.md
```

新增自动部署入口：

```text
scripts/acr-webhook-server.py
systemd/pixelle-acr-webhook.service
```

## Dockerfile.api 要求

基于当前 `Dockerfile` 拆出 API 生产版。

必须包含：

- Python 3.11 slim。
- `curl`，用于 healthcheck。
- `ffmpeg`，用于音视频合成。
- `fonts-noto-cjk`，用于中文字幕和封面。
- Playwright Chromium 及依赖，用于 HTML 模板渲染。
- `uv`。

需要复制：

```text
api/
pixelle_video/
templates/
workflows/
bgm/
resources/
docs/images/
docs/FAQ*.md
```

启动命令：

```bash
.venv/bin/python api/app.py --host 0.0.0.0 --port 8000
```

## Dockerfile.web 要求

多阶段构建。

Node 构建阶段：

```text
node:20-alpine
cd desktop
npm ci
npm run build
```

Nginx 运行阶段：

```text
nginx:1.27-alpine
复制 desktop/dist 到 /usr/share/nginx/html
复制 nginx.conf 到 /etc/nginx/conf.d/default.conf
暴露 8080
```

## Nginx 配置要求

核心规则：

```nginx
server {
  listen 8080;

  location /health {
    return 200 "ok";
  }

  location /api/ {
    proxy_pass http://pixelle-api:8000/api/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    client_max_body_size 2048m;
  }

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

注意：

- `proxy_read_timeout` 需要较长，因为数字人和成片任务可能耗时较久。
- `client_max_body_size` 需要支持上传视频素材。
- 前端必须请求相对路径 `/api`，不能在生产环境请求浏览器本机的 `127.0.0.1:8000`。

## 前端 API Base URL 要求

当前 React fallback 有 `http://127.0.0.1:8000`，生产 Docker 下必须支持相对路径。

推荐规则：

- Tauri / 本地开发：`http://127.0.0.1:8000`
- Docker Web 生产：`/api`

可通过 `VITE_API_BASE_URL` 控制：

```env
VITE_API_BASE_URL=/api
```

如果 `VITE_API_BASE_URL` 未设置：

- Tauri 调用 `desktop_runtime` 成功时使用其返回的 API 地址。
- 浏览器 Web 生产环境默认使用空字符串，相对请求 `/api/...`。
- 本地开发可通过 `.env.local` 设置 `VITE_API_BASE_URL=http://127.0.0.1:8000`。

## docker-compose.prod.yml 设计

核心服务：

```yaml
services:
  init:
    image: alpine:latest
    volumes:
      - ./:/workspace
    command: >
      sh -c '
        mkdir -p /workspace/data /workspace/output /workspace/temp;
        if [ -d /workspace/config.yaml ]; then
          rm -rf /workspace/config.yaml;
        fi;
        if [ ! -f /workspace/config.yaml ] && [ -f /workspace/config.example.yaml ]; then
          cp /workspace/config.example.yaml /workspace/config.yaml;
        fi
      '
    restart: "no"

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
      args:
        USE_CN_MIRROR: ${USE_CN_MIRROR:-false}
        IMAGE_TAG: ${IMAGE_TAG:-latest}
        GIT_COMMIT: ${GIT_COMMIT:-unknown}
        BUILD_TIME: ${BUILD_TIME:-unknown}
    image: ${REGISTRY}/pixelle-video-api:${IMAGE_TAG:-latest}
    container_name: pixelle-api
    command: .venv/bin/python api/app.py --host 0.0.0.0 --port 8000
    depends_on:
      init:
        condition: service_completed_successfully
    expose:
      - "8000"
    ports:
      - "127.0.0.1:${API_PORT:-8000}:8000"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./data:/app/data
      - ./output:/app/output
      - ./temp:/app/temp
    environment:
      - TZ=${TZ:-Asia/Shanghai}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped
    networks:
      - pixelle-network

  web:
    build:
      context: .
      dockerfile: Dockerfile.web
      args:
        IMAGE_TAG: ${IMAGE_TAG:-latest}
        GIT_COMMIT: ${GIT_COMMIT:-unknown}
        BUILD_TIME: ${BUILD_TIME:-unknown}
    image: ${REGISTRY}/pixelle-video-web:${IMAGE_TAG:-latest}
    container_name: pixelle-web
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "127.0.0.1:${WEB_PORT:-8080}:8080"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - pixelle-network

networks:
  pixelle-network:
    driver: bridge
```

说明：

- 生产推荐只让用户访问 `WEB_PORT`。
- `API_PORT` 绑定 `127.0.0.1`，仅用于服务器本机排查。
- 如果外层还有宝塔、Caddy 或 Nginx，可再反代到 `127.0.0.1:${WEB_PORT}`。

## .env.example

```env
IMAGE_TAG=latest
REGISTRY=acr-xiaojuntech-registry.cn-beijing.cr.aliyuncs.com/xiaojuntech
WEB_PORT=8080
API_PORT=8000
TZ=Asia/Shanghai
USE_CN_MIRROR=false

ACR_USERNAME=
ACR_PASSWORD=
FEISHU_WEBHOOK_URL=
ACR_WEBHOOK_SECRET=
ACR_WEBHOOK_HOST=127.0.0.1
ACR_WEBHOOK_PORT=9001
ACR_WEBHOOK_PATH=/pixelle-acr-webhook
ACR_WEBHOOK_EXPECTED_SERVICES=api,web
ACR_WEBHOOK_STATE_PATH=data/deploy_webhook_state.json
ACR_WEBHOOK_DEPLOY_LOG=logs/deploy-webhook.log
```

业务配置仍写入 `config.yaml`：

```yaml
llm:
  api_key: ...
  base_url: ...
  model: ...

comfyui:
  runninghub_api_key: ...
  runninghub_instance_type: default
```

## deploy.sh 流程

参考 `geo-platform/scripts/deploy.sh`。

流程：

1. 使用 `/tmp/pixelle-video-deploy.lock` 加部署锁。
2. 进入项目根目录。
3. 加载 `.env`。
4. 设置：
   - `IMAGE_TAG`
   - `GIT_COMMIT`
   - `BUILD_TIME`
5. 如果存在 `ACR_USERNAME` 和 `ACR_PASSWORD`，执行 `docker login`。
6. 拉取镜像：

```bash
IMAGE_TAG="$TAG" docker compose -f docker-compose.prod.yml pull api web
```

7. 启动服务：

```bash
IMAGE_TAG="$TAG" docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

8. 健康检查：

```bash
curl -sf http://127.0.0.1:${WEB_PORT:-8080}/health
curl -sf http://127.0.0.1:${API_PORT:-8000}/health
```

9. 成功后写入：

```text
.last_good_tag
```

10. 失败时自动回滚到 `.last_good_tag`。
11. 可选飞书通知部署成功/失败。

## rollback.sh 流程

1. 读取 `.last_good_tag`。
2. 如果不存在，退出并提示无法回滚。
3. 使用历史 tag 拉取镜像：

```bash
IMAGE_TAG="$LAST_GOOD_TAG" docker compose -f docker-compose.prod.yml pull api web
```

4. 启动历史版本：

```bash
IMAGE_TAG="$LAST_GOOD_TAG" docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

5. 再跑 Web/API 健康检查。

## ACR webhook 自动部署流程

目标流程：

```text
GitHub push
  ↓
ACR 自动构建 pixelle-video-api / pixelle-video-web
  ↓
两个镜像仓库的 webhook 都请求服务器
  ↓
服务器记录同一 tag 下 api/web 的构建完成状态
  ↓
api/web 都完成后执行 IMAGE_TAG=<tag> ./scripts/deploy.sh
```

为什么不能每个镜像构建完成就直接部署：

- 本项目生产环境包含 `api` 和 `web` 两个镜像。
- ACR 两个镜像的构建完成时间不一定一致。
- 如果 api 先完成就部署，web 可能还没有相同 tag，导致 `docker compose pull` 失败或版本不一致。

因此 webhook 接收器采用“双镜像就绪再部署”的策略。

### webhook 服务

新增：

```text
scripts/acr-webhook-server.py
```

行为：

1. 监听 `ACR_WEBHOOK_HOST` / `ACR_WEBHOOK_PORT`。
2. 仅接收 `ACR_WEBHOOK_PATH` 的 POST 请求。
3. 通过 header 或 query 校验 `ACR_WEBHOOK_SECRET`。
4. 从 ACR payload 中解析镜像仓库名和 tag。
5. 将状态写入 `ACR_WEBHOOK_STATE_PATH`。
6. 当同一 tag 下 `api`、`web` 都就绪时，后台执行：

```bash
IMAGE_TAG=<tag> ./scripts/deploy.sh
```

服务健康检查：

```bash
curl http://127.0.0.1:${ACR_WEBHOOK_PORT:-9001}/health
```

### systemd 服务

新增：

```text
systemd/pixelle-acr-webhook.service
```

服务器安装：

```bash
sudo cp systemd/pixelle-acr-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pixelle-acr-webhook
sudo systemctl status pixelle-acr-webhook
```

查看日志：

```bash
journalctl -u pixelle-acr-webhook -f
tail -f logs/deploy-webhook.log
```

### Nginx / 宝塔反代

webhook 服务默认只监听 `127.0.0.1:9001`，不要直接暴露到公网端口。

外层 Nginx 或宝塔配置一个 HTTPS 路径反代：

```nginx
location /pixelle-acr-webhook {
  proxy_pass http://127.0.0.1:9001/pixelle-acr-webhook;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

ACR webhook URL 使用：

```text
https://你的域名/pixelle-acr-webhook?secret=你的ACR_WEBHOOK_SECRET
```

如果 ACR 支持自定义 header，也可以传：

```text
X-Pixelle-Webhook-Secret: 你的ACR_WEBHOOK_SECRET
```

### ACR 自动构建配置

`pixelle-video-api`：

```text
代码源：GitHub
分支：main 或生产分支
Dockerfile：Dockerfile.api
构建上下文：/
镜像 Tag：${Branch}-${CommitID}
构建参数：USE_CN_MIRROR=true
Webhook：https://你的域名/pixelle-acr-webhook?secret=...
```

`pixelle-video-web`：

```text
代码源：GitHub
分支：main 或生产分支
Dockerfile：Dockerfile.web
构建上下文：/
镜像 Tag：${Branch}-${CommitID}
构建参数：VITE_API_BASE_URL=/api
Webhook：https://你的域名/pixelle-acr-webhook?secret=...
```

### 日常发布方式

日常发布只需要：

```bash
git push
```

ACR 会自动构建镜像。两个镜像都完成后，服务器自动部署。

## 发布流程

正式发布不在本地构建镜像，也不通过 GitHub Actions 构建镜像。

流程：

1. 开发者提交代码到 GitHub。
2. ACR 自动拉取 GitHub 代码构建 `pixelle-video-api`。
3. ACR 自动拉取 GitHub 代码构建 `pixelle-video-web`。
4. ACR webhook 通知服务器。
5. 服务器等同一 tag 的 api/web 都完成后执行 `deploy.sh`。
6. `deploy.sh` 拉取镜像、启动服务、执行健康检查，失败自动回滚。

人工部署仍可作为兜底：

```bash
IMAGE_TAG=main-xxxxxxx ./scripts/deploy.sh
```

## 健康检查边界

健康检查只判断：

- Web 容器可访问。
- API 容器可访问。

不把以下内容放入 healthcheck：

- LLM 是否可用。
- 云端算力是否可用。
- RunningHub 是否可用。
- 数字人/成片完整生成。

原因：

- 第三方服务波动不应该导致容器被误判为部署失败。
- 真实生成链路成本高、耗时长，不适合作为容器健康检查。

需要单独保留人工 smoke test：

```bash
curl http://127.0.0.1:${WEB_PORT:-8080}/health
curl http://127.0.0.1:${WEB_PORT:-8080}/api/tasks
curl http://127.0.0.1:${WEB_PORT:-8080}/api/desktop/config
```

## 验收标准

本地生产模式：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

应满足：

- `http://127.0.0.1:8080/health` 返回 `ok`。
- `http://127.0.0.1:8000/health` 返回正常。
- `http://127.0.0.1:8080` 可以打开 React 页面。
- `http://127.0.0.1:8080/api/tasks` 可以返回任务列表。
- `config.yaml` 自动初始化。
- `data/desktop_tasks.sqlite` 可持久化任务中心。
- `output/`、`temp/` 正常挂载。

部署脚本模式：

```bash
IMAGE_TAG=dev-xxxx ./scripts/deploy.sh
```

应满足：

- 自动登录 ACR。
- 自动 pull 镜像。
- 自动启动 api/web。
- Web/API 健康检查通过。
- 成功写入 `.last_good_tag`。
- 部署坏 tag 时可回滚。

## 实施顺序

1. 修改 React API base URL，支持 Docker 生产相对 `/api`。
2. 新增 `Dockerfile.api`。
3. 新增 `Dockerfile.web`。
4. 新增 `nginx.conf`。
5. 新增 `docker-compose.prod.yml`。
6. 新增 `.env.example`。
7. 新增 `scripts/deploy.sh`。
8. 新增 `scripts/rollback.sh`。
9. 新增 `scripts/acr-webhook-server.py`。
10. 新增 `systemd/pixelle-acr-webhook.service`。
11. 本地生产 compose 配置验证。
12. ACR 自动构建验证。
13. 服务器 webhook 触发部署验证。
14. 服务器 `deploy.sh` 和 `rollback.sh` 验证。

## 风险和注意事项

- API 镜像会比较大，因为必须包含 FFmpeg、Playwright、字体。
- 前端生产环境不能请求 `http://127.0.0.1:8000`，必须走 `/api`。
- Nginx `/api/` 的 `proxy_pass` 路径必须测试，避免路径被截错。
- `config.yaml` 中含密钥，不应提交到 Git。
- `data/`、`output/`、`temp/` 必须挂载宿主机目录，否则容器重建会丢数据。
- Streamlit 是旧入口，本次生产部署以 React Web 为主；如需保留 Streamlit，应放入单独的 legacy compose 文件。
