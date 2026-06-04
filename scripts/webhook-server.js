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
import { spawn } from 'child_process'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = process.env.PROJECT_ROOT || join(__dirname, '..')

const PORT = process.env.WEBHOOK_PORT || 9877
const SECRET = process.env.DEPLOY_WEBHOOK_SECRET

if (!SECRET) {
  console.error('[webhook] DEPLOY_WEBHOOK_SECRET 未设置，拒绝启动')
  process.exit(1)
}

const EXPECTED_REPOS = ['pixelle-video-web', 'pixelle-video-api']
if (process.env.DEPLOY_STREAMLIT === 'true') {
  EXPECTED_REPOS.push('pixelle-video-streamlit')
}
const pendingByTag = new Map()

function runDeploy(imageTag) {
  console.log(`[webhook] 触发部署 IMAGE_TAG=${imageTag}`)

  const child = spawn('bash', ['scripts/deploy.sh'], {
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
  const token = url.searchParams.get('token')
  if (token !== SECRET) {
    console.warn(`[webhook] 鉴权失败 token=${token}`)
    res.writeHead(401).end('Unauthorized')
    return
  }

  let body = ''
  req.on('data', chunk => {
    body += chunk
  })
  req.on('end', () => {
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
