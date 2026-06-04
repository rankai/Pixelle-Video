# Pixelle-Video 网页端自动部署执行手册

本手册按 `geo-platform` 已验证的方式配置：GitHub 推送通知、ACR 自动构建、Docker webhook 容器接收通知、服务器执行 `scripts/deploy.sh`、飞书通知结果、宝塔反代访问。

## 1. 部署链路

```text
git push dev
  -> GitHub Actions 发送“代码已推送，ACR 构建中”飞书通知
  -> ACR 自动构建 pixelle-video-web / pixelle-video-api
  -> 可选：ACR 自动构建 pixelle-video-streamlit
  -> ACR webhook 请求服务器 /deploy?token=...
  -> pixelle-webhook 等同一 tag 的 web/api 都完成
  -> 可选：DEPLOY_STREAMLIT=true 时也等待 streamlit
  -> pixelle-webhook 执行 scripts/deploy.sh
  -> docker compose pull api web
  -> 可选：DEPLOY_STREAMLIT=true 时同步 pull streamlit
  -> docker compose up -d
  -> 健康检查
  -> deploy.sh 发送部署成功/失败飞书通知
```

生产分支：`dev`。

## 2. GitHub Actions

文件：

```text
.github/workflows/deploy.yml
```

触发：

```text
push dev
push v* tag
```

行为：

- 构建 React Web，提前发现前端编译错误。
- 校验 `docker-compose.prod.yml`。
- 运行 webhook 单元测试。
- 通过 `FEISHU_WEBHOOK_URL` secret 发送“ACR 构建中”通知。

GitHub Secrets：

```text
FEISHU_WEBHOOK_URL=飞书机器人 Webhook
```

说明：GitHub Actions 不构建镜像，不部署服务器；镜像构建交给 ACR，真实部署通知由服务器 `deploy.sh` 发。

## 3. ACR 配置

创建两个必需镜像仓库：

```text
pixelle-video-web
pixelle-video-api
```

两个仓库都绑定 GitHub 仓库的 `dev` 分支。

`pixelle-video-web`：

```text
Dockerfile: Dockerfile.web
构建上下文: /
构建架构: linux/amd64
构建参数:
  NODE_BASE=node:20-alpine
  NGINX_BASE=nginx:alpine
  VITE_API_BASE_URL=/api
Tag 规则:
  ${Branch}-${CommitID}
Webhook:
  https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

建议显式配置 `Dockerfile.web`。为了兼容 ACR 默认读取根目录 `Dockerfile` 的情况，根 `Dockerfile` 也已经改为 React Web 镜像入口。旧的一体化 Python 镜像入口保留在 `Dockerfile.legacy`。

`pixelle-video-api`：

```text
Dockerfile: Dockerfile.api
构建上下文: /
构建架构: linux/amd64
构建参数:
  PYTHON_BASE=python:3.11-slim
  USE_CN_MIRROR=true
Tag 规则:
  ${Branch}-${CommitID}
Webhook:
  https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

可选旧页面仓库：

```text
pixelle-video-streamlit
```

`pixelle-video-streamlit`：

```text
Dockerfile: Dockerfile.streamlit
构建上下文: /
构建架构: linux/amd64
构建参数:
  PYTHON_BASE=python:3.11-slim
  USE_CN_MIRROR=true
Tag 规则:
  ${Branch}-${CommitID}
Webhook:
  仅 DEPLOY_STREAMLIT=true 时配置同一个 webhook
```

ACR 构建规则里按 geo-platform 的方式使用构建参数覆盖基础镜像：

```text
NODE_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/node:20-alpine
NGINX_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/nginx:alpine
PYTHON_BASE=acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com/xiaojuntech/python:3.11-slim
```

如果你的基础镜像仓库 tag 不是完整版本，例如 nginx 只有 `alpine`，就把 `NGINX_BASE` 改成实际存在的 tag。

web/api 两个仓库的 tag 规则必须一致。服务器会等同一个 tag 的 web/api 两个镜像都收到通知后才部署。

如果启用旧 Streamlit 页面，streamlit 仓库也必须使用同一 tag 规则，并配置同一个 webhook。否则 webhook 会等待 5 分钟后超时强制触发部署。

如果 ACR 没有出现最新 tag，先检查构建规则是否绑定：

```text
代码源: rankai/Pixelle-Video
分支: dev
触发方式: 代码变更自动构建 / push
最新提交: 以 GitHub dev 当前 SHA 为准
```

如果上述配置确认无误但 ACR 没有新构建记录，可再次向 `dev` 推送一个小提交来重新触发 GitHub push 事件。
重新触发后，构建日志里的基础镜像地址应显示为 `acr-xiaojuntech-registry-vpc.cn-beijing.cr.aliyuncs.com`。

## 4. 服务器目录

建议目录：

```bash
/opt/pixelle-video
```

首次准备：

```bash
git clone <你的 GitHub 仓库地址> /opt/pixelle-video
cd /opt/pixelle-video
cp .env.example .env
cp config.example.yaml config.yaml
mkdir -p data output temp logs
```

`.env` 关键配置：

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
PYTHON_BASE=python:3.11-slim
DEPLOY_STREAMLIT=false

ACR_USERNAME=你的 ACR 用户名
ACR_PASSWORD=你的 ACR 密码

FEISHU_WEBHOOK_URL=飞书机器人 Webhook
DEPLOY_WEBHOOK_SECRET=随机长密钥
WEBHOOK_PORT=9877
```

端口说明：

- `18080` 是 Pixelle Web 宿主机端口，避开 geo-platform 已使用的 `8080`。
- `8501` 是旧 Streamlit 页面宿主机端口，仅 `DEPLOY_STREAMLIT=true` 时部署。
- `9877` 是 Pixelle webhook 宿主机端口，避开 geo-platform 已使用的 `9876`。
- `WEB_HOST=127.0.0.1` 表示只允许宝塔在服务器本机反代访问，不直接暴露 Docker 端口到公网。

## 5. 启动服务

首次在服务器上启动：

```bash
cd /opt/pixelle-video
docker compose -f docker-compose.prod.yml up -d webhook
```

健康检查：

```bash
curl http://127.0.0.1:9877/healthz
```

首次部署某个 ACR tag：

```bash
IMAGE_TAG=dev-a1b2c3d ./scripts/deploy.sh
```

验证：

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/api/tasks
curl http://127.0.0.1:18080/api/desktop/config
```

如果需要旧 Streamlit 页面：

```bash
DEPLOY_STREAMLIT=true IMAGE_TAG=dev-a1b2c3d ./scripts/deploy.sh
curl http://127.0.0.1:8501/_stcore/health
```

## 6. 宝塔配置

宝塔站点反代网页端：

```text
目标 URL:
http://127.0.0.1:18080
```

宝塔反代 ACR webhook：

```text
路径:
/deploy

目标 URL:
http://127.0.0.1:9877/deploy
```

等价 Nginx 配置：

```nginx
location / {
  proxy_pass http://127.0.0.1:18080;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location /deploy {
  proxy_pass http://127.0.0.1:9877/deploy;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

可选旧 Streamlit 页面反代：

```nginx
location /streamlit/ {
  proxy_pass http://127.0.0.1:8501/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
}
```

ACR webhook URL 填：

```text
https://你的域名/deploy?token=DEPLOY_WEBHOOK_SECRET
```

## 7. 日常发布

```bash
git push origin dev
```

之后自动发生：

```text
GitHub Actions 飞书通知
ACR 构建 web/api
ACR webhook 通知服务器
服务器自动部署
飞书通知部署结果
```

查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f webhook
docker compose -f docker-compose.prod.yml logs -f web api
tail -f logs/deploy-webhook.log
```

## 8. 回滚

```bash
./scripts/rollback.sh
```

回滚使用 `.last_good_tag` 中记录的上一个健康版本。

## 验收标准

- GitHub push 到 `dev` 后，飞书收到“代码已推送，ACR 构建中”通知。
- ACR 两个仓库都能生成相同 tag。
- ACR webhook 请求 `https://你的域名/deploy?token=...` 返回成功。
- `pixelle-webhook` 日志显示同一 tag 收到 `2/2`。
- `scripts/deploy.sh` 自动执行。
- `http://127.0.0.1:18080/health` 返回 `ok`。
- 宝塔域名能打开 React 网页端。
- 飞书收到部署成功或失败通知。
