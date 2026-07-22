#!/usr/bin/env node
/**
 * ACR Deploy Webhook Server
 *
 * Mirrors geo-platform's deployment model:
 * - ACR pushes web/api build notifications to POST /deploy?token=...
 * - The server waits until both pixelle-video-web and pixelle-video-api are ready for the same tag
 * - Then it runs scripts/deploy.sh with IMAGE_TAG=<tag>
 */

import http from 'http'
import crypto from 'crypto'
import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = process.env.PROJECT_ROOT || process.cwd() || join(__dirname, '..')
const DEPLOY_SCRIPT = join(ROOT, 'scripts/deploy.sh')

const PORT = process.env.WEBHOOK_PORT || 9877
const SECRET = process.env.DEPLOY_WEBHOOK_SECRET
const HMAC_SECRET = process.env.DEPLOY_WEBHOOK_HMAC_SECRET || ''
const REQUIRE_HMAC = process.env.DEPLOY_WEBHOOK_REQUIRE_HMAC === 'true'
const configuredHmacWindow = Number(process.env.DEPLOY_WEBHOOK_HMAC_WINDOW_SECONDS || 300)
const HMAC_WINDOW_SECONDS = Number.isFinite(configuredHmacWindow) && configuredHmacWindow > 0 ? configuredHmacWindow : 300

if (!SECRET && !HMAC_SECRET) {
  console.error('[webhook] DEPLOY_WEBHOOK_SECRET 或 DEPLOY_WEBHOOK_HMAC_SECRET 未设置，拒绝启动')
  process.exit(1)
}

const EXPECTED_REPOS = ['pixelle-video-web', 'pixelle-video-api']
if (process.env.DEPLOY_STREAMLIT === 'true') {
  EXPECTED_REPOS.push('pixelle-video-streamlit')
}
const pendingByTag = new Map()

function runDeploy(imageTag) {
  console.log(`[webhook] 触发部署 IMAGE_TAG=${imageTag}`)
  if (!existsSync(DEPLOY_SCRIPT)) {
    console.error(`[webhook] 找不到部署脚本: ${DEPLOY_SCRIPT}`)
    console.error('[webhook] 请检查 docker-compose.prod.yml 中 PROJECT_ROOT/PROJECT_DIR 是否指向宿主机项目目录')
    return
  }

  const child = spawn('bash', [DEPLOY_SCRIPT], {
    cwd: ROOT,
    env: { ...process.env, IMAGE_TAG: imageTag },
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  child.stdout.on('data', d => process.stdout.write(`[deploy] ${d}`))
  child.stderr.on('data', d => process.stderr.write(`[deploy] ${d}`))
  child.on('exit', code => console.log(`[webhook] deploy.sh 退出 code=${code}`))
  child.unref()
}

function handlePush(repoName, tag) {
  if (!EXPECTED_REPOS.includes(repoName)) {
    console.log(`[webhook] 非预期镜像 repo=${repoName}，跳过`)
    return
  }

  if (!pendingByTag.has(tag)) {
    const timer = setTimeout(() => {
      const state = pendingByTag.get(tag)
      if (!state) return
      const missing = EXPECTED_REPOS.filter(repo => !state.repos.has(repo))
      console.log(`[webhook] 等待超时，缺少镜像: ${missing.join(',')}，强制触发部署`)
      pendingByTag.delete(tag)
      runDeploy(tag)
    }, 5 * 60 * 1000)

    pendingByTag.set(tag, { repos: new Set(), timer })
  }

  const state = pendingByTag.get(tag)
  state.repos.add(repoName)

  const missing = EXPECTED_REPOS.filter(repo => !state.repos.has(repo))
  console.log(`[webhook] tag=${tag} 已收到 ${state.repos.size}/${EXPECTED_REPOS.length}，等待: ${missing.join(',') || '全部到齐'}`)

  if (state.repos.size >= EXPECTED_REPOS.length) {
    clearTimeout(state.timer)
    pendingByTag.delete(tag)
    runDeploy(tag)
  }
}

function verifyHmac(req, body) {
  if (!HMAC_SECRET) return false
  const timestamp = req.headers['x-pixelle-timestamp']
  const signature = req.headers['x-pixelle-signature']
  if (typeof timestamp !== 'string' || typeof signature !== 'string') return false

  const timestampSeconds = Number(timestamp)
  if (!Number.isFinite(timestampSeconds)) return false
  const nowSeconds = Math.floor(Date.now() / 1000)
  if (Math.abs(nowSeconds - timestampSeconds) > HMAC_WINDOW_SECONDS) return false

  const expected = crypto
    .createHmac('sha256', HMAC_SECRET)
    .update(`${timestamp}.${body}`)
    .digest('hex')
  const provided = signature.replace(/^sha256=/, '')
  return timingSafeEqualHex(provided, expected)
}

function timingSafeEqualHex(left, right) {
  if (!/^[0-9a-f]+$/i.test(left) || !/^[0-9a-f]+$/i.test(right)) return false
  const leftBuffer = Buffer.from(left, 'hex')
  const rightBuffer = Buffer.from(right, 'hex')
  return leftBuffer.length === rightBuffer.length && crypto.timingSafeEqual(leftBuffer, rightBuffer)
}

function isAuthorized(req, url, body) {
  const hmacOk = verifyHmac(req, body)
  if (hmacOk) return true
  if (REQUIRE_HMAC) return false
  return url.searchParams.get('token') === SECRET
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/healthz') {
    res.writeHead(200).end('ok')
    return
  }

  if (req.method !== 'POST' || !req.url.startsWith('/deploy')) {
    res.writeHead(404).end()
    return
  }

  const url = new URL(req.url, 'http://localhost')
  let body = ''
  req.on('data', chunk => {
    body += chunk
  })
  req.on('end', () => {
    if (!isAuthorized(req, url, body)) {
      console.warn(`[webhook] 鉴权失败 remote=${req.socket.remoteAddress || 'unknown'}`)
      res.writeHead(401).end('Unauthorized')
      return
    }

    res.writeHead(200, { 'Content-Type': 'application/json' }).end('{"ok":true}')

    let payload
    try {
      payload = JSON.parse(body)
    } catch {
      console.warn('[webhook] 无法解析 payload')
      return
    }

    const repoName = payload?.repository?.name || ''
    const tag = payload?.push_data?.tag || 'dev'

    console.log(`[webhook] 收到推送 repo=${repoName} tag=${tag}`)
    handlePush(repoName, tag)
  })
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[webhook] 监听 0.0.0.0:${PORT}/deploy`)
})
