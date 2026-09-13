import type { AxiosResponse } from 'axios'
import type {
  AuditLogEntry,
  Category,
  Feature,
  FeatureVersion,
  Folder,
  ImportResult,
  Member,
  NearbyResult,
  Project,
  ProjectDetail,
  Role,
  TokenResponse,
  User,
} from '@/types'

import { api } from '@/utils/http'

export const authApi = {
  login: (username: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { username, password }).then(r => r.data),
  register: (payload: { username: string; email: string; password: string; display_name?: string }) =>
    api.post<TokenResponse>('/auth/register', payload).then(r => r.data),
  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token }).then(r => r.data),
  logout: (refresh_token: string) => api.post('/auth/logout', { refresh_token }),
  me: () => api.get<User>('/auth/me').then(r => r.data),
}

export const projectApi = {
  list: () => api.get<Project[]>('/projects').then(r => r.data),
  get: (id: string) => api.get<ProjectDetail>(`/projects/${id}`).then(r => r.data),
  create: (payload: { name: string; description?: string }) =>
    api.post<Project>('/projects', payload).then(r => r.data),
  update: (id: string, payload: Partial<Project>) =>
    api.patch<Project>(`/projects/${id}`, payload).then(r => r.data),
  remove: (id: string) => api.delete(`/projects/${id}`),
  /** 测试板块专用：把本项目同步到正式板块（后端跨进程调用正式 API） */
  syncToProd: (id: string) => api.post<{ project_id: string; name: string; created: number; errors: unknown[] }>(`/projects/${id}/sync-to-prod`).then(r => r.data),
  members: (id: string) => api.get<Member[]>(`/projects/${id}/members`).then(r => r.data),
  addMember: (id: string, payload: { username?: string; email?: string; role: Role }) =>
    api.post<Member>(`/projects/${id}/members`, payload).then(r => r.data),
  updateMember: (id: string, userId: string, role: Role) =>
    api.patch<Member>(`/projects/${id}/members/${userId}`, { role }).then(r => r.data),
  removeMember: (id: string, userId: string) =>
    api.delete(`/projects/${id}/members/${userId}`),
  audit: (id: string, page = 1) =>
    api.get<{ items: AuditLogEntry[]; total: number }>(`/projects/${id}/audit`, {
      params: { page, page_size: 50 },
    }).then(r => r.data),
  online: (id: string) => api.get<{ id: string; username: string; display_name: string }[]>(`/projects/${id}/online`).then(r => r.data),
  categories: (id: string) => api.get<Category[]>(`/projects/${id}/categories`).then(r => r.data),
}

export const folderApi = {
  list: (projectId: string) => api.get<Folder[]>(`/projects/${projectId}/folders`).then(r => r.data),
  create: (projectId: string, payload: { name: string; parent_id?: string | null; sort_order?: number }) =>
    api.post<Folder>(`/projects/${projectId}/folders`, payload).then(r => r.data),
  update: (id: string, payload: Partial<Folder>) =>
    api.patch<Folder>(`/folders/${id}`, payload).then(r => r.data),
  remove: (id: string) => api.delete(`/folders/${id}`),
}

export const categoryApi = {
  list: (projectId: string) => api.get<Category[]>(`/projects/${projectId}/categories`).then(r => r.data),
  create: (projectId: string, payload: Partial<Category>) =>
    api.post<Category>(`/projects/${projectId}/categories`, payload).then(r => r.data),
  update: (id: string, payload: Partial<Category>) =>
    api.patch<Category>(`/categories/${id}`, payload).then(r => r.data),
  remove: (id: string) => api.delete(`/categories/${id}`),
}

export interface FeatureCreatePayload {
  name: string
  feature_type: string
  geometry: Record<string, unknown>
  coordinate_system?: 'GCJ02' | 'WGS84'
  folder_id?: string | null
  category_id?: string | null
  properties?: Record<string, unknown>
  style?: Record<string, unknown>
}

export const featureApi = {
  list: (projectId: string, params?: { folder_id?: string; include_deleted?: boolean }) =>
    api.get<Feature[]>(`/projects/${projectId}/features`, { params }).then(r => r.data),
  get: (id: string) => api.get<Feature>(`/features/${id}`).then(r => r.data),
  create: (projectId: string, payload: FeatureCreatePayload) =>
    api.post<Feature>(`/projects/${projectId}/features`, payload).then(r => r.data),
  update: (id: string, payload: Partial<{ name: string; version: number; geometry: unknown; folder_id: string | null; category_id: string | null; properties: unknown; style: unknown }>) => {
    return api.patch<Feature>(`/features/${id}`, { ...payload, version: payload.version ?? 0 }).then(r => r.data)
  },
  move: (id: string, folder_id: string | null, version: number) =>
    api.post<Feature>(`/features/${id}/move`, { folder_id, version }).then(r => r.data),
  remove: (id: string) => api.delete(`/features/${id}`),
  restore: (id: string) => api.post<Feature>(`/features/${id}/restore`).then(r => r.data),
  permanentDelete: (id: string) => api.delete(`/features/${id}/permanent`),
  versions: (id: string) => api.get<FeatureVersion[]>(`/features/${id}/versions`).then(r => r.data),
  restoreVersion: (id: string, version: number) =>
    api.post<Feature>(`/features/${id}/versions/${version}/restore`).then(r => r.data),
  nearby: (projectId: string, lng: number, lat: number, radius: number) =>
    api
      .get<{ items: NearbyResult[] }>(`/projects/${projectId}/features/nearby`, {
        params: { lng, lat, radius },
      })
      .then(r => r.data),
  lock: (id: string) => api.post(`/features/${id}/lock`),
  unlock: (id: string) => api.post(`/features/${id}/unlock`),
  trash: (projectId: string) =>
    api.get<Feature[]>(`/projects/${projectId}/trash`).then(r => r.data),
}

export const importApi = {
  importFile: (projectId: string, file: File, crs: 'GCJ02' | 'WGS84') => {
    const form = new FormData()
    form.append('file', file)
    form.append('crs', crs)
    return api.post<ImportResult>(`/projects/${projectId}/import`, form).then(r => r.data)
  },
  exportUrl: (projectId: string, params: { scope?: string; folder_id?: string; feature_ids?: string; crs?: string; format?: string }) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v && q.set(k, v))
    return `${import.meta.env.BASE_URL}api/v1/projects/${projectId}/export?${q.toString()}`
  },
  /** 带鉴权下载导出文件（axios 自动带 Authorization），触发浏览器保存 */
  async downloadExport(projectId: string, params: { format: string; crs?: string; scope?: string; folder_id?: string; feature_ids?: string }) {
    const resp = await api.get(`/projects/${projectId}/export`, {
      params,
      responseType: 'blob',
      timeout: 60000,
    })
    const blob = resp.data as Blob
    // 从 Content-Disposition 里解析文件名（优先 filename* 的中文名）
    let filename = ''
    const cd = (resp.headers['content-disposition'] as string) || ''
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    if (star) {
      try { filename = decodeURIComponent(star[1]) } catch { /* ignore */ }
    }
    if (!filename) {
      const plain = /filename="?([^";]+)"?/i.exec(cd)
      filename = plain ? plain[1] : `export.${params.format === 'csv' ? 'csv' : params.format === 'backup' ? 'json' : 'geojson'}`
    }
    // 用 <a download> 触发下载；部分浏览器对 blob 下载有沙盒限制，
    // 检测不到则用隐式锚点方案兜底（见下方 else 分支前仍走 blob）
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
    return filename
  },
}

export const amapApi = {
  search: (keywords: string, city?: string, location?: [number, number], radius?: number) =>
    api
      .post<
        { status: string; pois?: { name: string; address: string; location: string }[] }
      >('/amap-proxy', {
        path: '/v3/place/text',
        params: {
          keywords,
          city: city ?? '',
          offset: 20, // 拉多一点，便于前端按视野排序
          page: 1,
          extensions: 'base',
          // 附近搜索：location=经度,纬度 + radius 以米为单位，让结果优先在当前视野
          ...(location ? { location: `${location[0]},${location[1]}`, radius: radius ?? 5000 } : {}),
        },
      })
      .then(r => r.data),
}