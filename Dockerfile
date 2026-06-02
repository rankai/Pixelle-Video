# Pixelle-Video React web production image.
# The root Dockerfile intentionally builds the web image because ACR defaults
# to `Dockerfile` when the Dockerfile path is not set. The legacy all-in-one
# Python image is kept at Dockerfile.legacy.

ARG NODE_BASE=registry.cn-hangzhou.aliyuncs.com/library/node:20-alpine
ARG NGINX_BASE=registry.cn-hangzhou.aliyuncs.com/library/nginx:alpine

FROM ${NODE_BASE} AS builder

ARG VITE_API_BASE_URL=/api
ARG IMAGE_TAG=latest
ARG GIT_COMMIT=unknown
ARG BUILD_TIME=unknown

WORKDIR /app/desktop

COPY desktop/package.json desktop/package-lock.json ./
RUN npm ci

COPY desktop ./
RUN VITE_API_BASE_URL="${VITE_API_BASE_URL}" npm run build

FROM ${NGINX_BASE}

ARG IMAGE_TAG=latest
ARG GIT_COMMIT=unknown
ARG BUILD_TIME=unknown

LABEL org.opencontainers.image.title="pixelle-video-web" \
      org.opencontainers.image.version="${IMAGE_TAG}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.created="${BUILD_TIME}"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/desktop/dist /usr/share/nginx/html

EXPOSE 8080
