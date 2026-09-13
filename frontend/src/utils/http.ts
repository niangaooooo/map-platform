import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

export const api = axios.create({
  baseURL: `${import.meta.env.BASE_URL}api/v1`,
  timeout: 20000,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const status = error.response?.status
    if (status === 401) {
      const auth = useAuthStore()
      // 尝试刷新一次
      const ok = await auth.tryRefresh()
      if (ok && error.config) {
        error.config.headers.Authorization = `Bearer ${auth.accessToken}`
        return api.request(error.config)
      }
      auth.logout()
      const loginPath = `${import.meta.env.BASE_URL}login`
      if (!location.pathname.startsWith(loginPath)) {
        location.href = loginPath
      }
      return Promise.reject(error)
    }
    if (status === 409) {
      ElMessage.warning('该对象刚刚被其他用户修改，请重新加载最新版本。')
    } else if (status === 403) {
      ElMessage.error('没有权限执行该操作')
    } else if (status === 423) {
      const detail = error.response?.data?.detail
      ElMessage.error(typeof detail === 'string' ? detail : '对象正被他人编辑')
    } else if (status === 429) {
      ElMessage.warning('操作过于频繁，请稍后再试')
    }
    return Promise.reject(error)
  }
)