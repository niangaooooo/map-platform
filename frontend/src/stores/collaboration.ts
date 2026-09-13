import { ref } from 'vue'
import { defineStore } from 'pinia'
import { projectApi } from '@/api'
import type { OnlineMember } from '@/types'

export interface LockInfo {
  user_id: string
  username: string
  display_name: string
}

/** 地图（WebSocket）协作 store：连接、在线成员、编辑锁、活动提示 */
export const useCollaborationStore = defineStore('collaboration', () => {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const online = ref<OnlineMember[]>([])
  const locks = ref<Record<string, LockInfo>>({})
  const lastActivity = ref<{ text: string; ts: number } | null>(null)

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectAttempts = 0
  let currentProjectId = ''
  let eventHandler: ((event: string, data: Record<string, unknown>) => void) | undefined

  function wsUrl(projectId: string): string {
    const token = localStorage.getItem('map_platform_access') || ''
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const base = import.meta.env.BASE_URL || '/'
    const path = `${base}ws/projects/${projectId}`.replace(/\/{2,}/g, '/')
    return `${proto}://${location.host}${path}?token=${encodeURIComponent(token)}`
  }

  function connect(projectId: string, onEvent?: (event: string, data: Record<string, unknown>) => void) {
    disconnect()
    currentProjectId = projectId
    eventHandler = onEvent
    const sock = new WebSocket(wsUrl(projectId))
    ws.value = sock

    sock.onopen = () => {
      connected.value = true
      reconnectAttempts = 0
      startHeartbeat(sock)
    }
    sock.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'pong') return
        handleMessage(msg)
      } catch {
        /* ignore */
      }
    }
    sock.onclose = () => {
      connected.value = false
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
      if (currentProjectId) scheduleReconnect()
    }
  }

  function handleMessage(msg: { event?: string; user_id?: string | null; data?: Record<string, unknown> }) {
    if (!msg.event || !msg.data) return
    const data = msg.data
    switch (msg.event) {
      case 'member.joined': {
        const u = (data.user as OnlineMember) ?? null
        if (u && !online.value.find(m => m.id === u.id)) online.value.push(u)
        break
      }
      case 'member.left': {
        const uid = data.user_id as string
        online.value = online.value.filter(m => m.id !== uid)
        break
      }
      case 'feature.locked': {
        const id = data.id as string
        locks.value = {
          ...locks.value,
          [id]: {
            user_id: (data.user_id as string) || msg.user_id || '',
            username: (data.username as string) || '其他用户',
            display_name: (data.display_name as string) || '',
          },
        }
        break
      }
      case 'feature.unlocked': {
        const id = data.id as string
        const next = { ...locks.value }
        delete next[id]
        locks.value = next
        break
      }
      case 'presence': {
        lastActivity.value = {
          text: `${(data.username as string) || '同事'} ${(data.activity as string) || '正在操作'}`,
          ts: Date.now(),
        }
        break
      }
      default:
        break
    }
    eventHandler?.(msg.event, data)
  }

  function startHeartbeat(sock: WebSocket) {
    heartbeatTimer = setInterval(() => {
      if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify({ type: 'ping' }))
    }, 20000)
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 15000)
    reconnectAttempts += 1
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (currentProjectId) connect(currentProjectId, eventHandler)
    }, delay)
  }

  function sendPresence(activity: string) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type: 'presence', activity, ts: Date.now() }))
    }
  }

  async function refreshOnline(projectId: string) {
    try {
      const list = await projectApi.online(projectId)
      online.value = list.map(m => ({ id: m.id, username: m.username, display_name: m.display_name, ts: '' }))
    } catch {
      /* ignore */
    }
  }

  function disconnect() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws.value?.close()
    ws.value = null
    connected.value = false
    online.value = []
    locks.value = {}
    lastActivity.value = null
    currentProjectId = ''
  }

  return {
    ws, connected, online, locks, lastActivity,
    connect, disconnect, sendPresence, refreshOnline,
  }
})