import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '@/api'
import type { User } from '@/types'

// 正式(/map/)与测试(/map-test/)板块的登录态必须隔离：
// 两套后端使用不同 SECRET_KEY 签发 token，若共用同一 localStorage key，
// 会把正式 token 发到测试后端 → 401 → refresh 死循环 → 页面空白。
// 以构建时的 BASE_URL 区分存储 key。
const _testEnv = import.meta.env.BASE_URL.startsWith('/map-test')
const _keyPrefix = _testEnv ? 'map_platform_test' : 'map_platform'
const ACCESS_KEY = `${_keyPrefix}_access`
const REFRESH_KEY = `${_keyPrefix}_refresh`

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem(ACCESS_KEY) || '')
  const refreshToken = ref(localStorage.getItem(REFRESH_KEY) || '')
  const user = ref<User | null>(null)
  const initialized = ref(false)

  const isLoggedIn = computed(() => !!accessToken.value)

  function persist() {
    localStorage.setItem(ACCESS_KEY, accessToken.value)
    localStorage.setItem(REFRESH_KEY, refreshToken.value)
  }

  async function login(username: string, password: string) {
    const resp = await authApi.login(username, password)
    accessToken.value = resp.access_token
    refreshToken.value = resp.refresh_token
    persist()
    user.value = await authApi.me()
  }

  async function register(payload: { username: string; email: string; password: string; display_name?: string }) {
    const resp = await authApi.register(payload)
    accessToken.value = resp.access_token
    refreshToken.value = resp.refresh_token
    persist()
    user.value = await authApi.me()
  }

  async function fetchMe() {
    if (!accessToken.value) return null
    user.value = await authApi.me().catch(() => null)
    initialized.value = true
    return user.value
  }

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const resp = await authApi.refresh(refreshToken.value)
      accessToken.value = resp.access_token
      refreshToken.value = resp.refresh_token
      persist()
      return true
    } catch {
      return false
    }
  }

  function logout() {
    if (refreshToken.value) authApi.logout(refreshToken.value).catch(() => undefined)
    accessToken.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  return { accessToken, refreshToken, user, initialized, isLoggedIn, login, register, fetchMe, tryRefresh, logout }
})