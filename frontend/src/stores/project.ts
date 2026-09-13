import { ref } from 'vue'
import { defineStore } from 'pinia'
import { projectApi } from '@/api'
import type { Category, Member, Project, ProjectDetail } from '@/types'
import { ElMessage } from 'element-plus'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const current = ref<ProjectDetail | null>(null)
  const members = ref<Member[]>([])
  const categories = ref<Category[]>([])
  const loadingProjects = ref(false)

  async function fetchProjects() {
    loadingProjects.value = true
    try {
      projects.value = await projectApi.list()
    } finally {
      loadingProjects.value = false
    }
  }

  async function openProject(id: string) {
    const detail = await projectApi.get(id)
    current.value = detail
    const [m, c] = await Promise.all([projectApi.members(id), projectApi.categories(id)])
    members.value = m
    categories.value = c
    return detail
  }

  async function fetchCategories(id = current.value?.id) {
    if (!id) return
    categories.value = await projectApi.categories(id)
  }

  async function closeProject() {
    current.value = null
    members.value = []
    categories.value = []
  }

  async function createProject(name: string, description = '') {
    const p = await projectApi.create({ name, description })
    await fetchProjects()
    return p
  }

  async function deleteProject(id: string) {
    await projectApi.remove(id)
    await fetchProjects()
  }

  /** 测试板块：把项目同步到正式板块（仅测试环境使用） */
  async function syncToProd(id: string) {
    return await projectApi.syncToProd(id)
  }

  async function fetchAll() {
    await fetchProjects()
  }

  async function updateCurrent(payload: Partial<Project>) {
    if (!current.value) return
    current.value = { ...current.value, ...(await projectApi.update(current.value.id, payload)) }
  }

  async function addMember(payload: { username?: string; email?: string; role: Member['role'] }) {
    if (!current.value) return
    const m = await projectApi.addMember(current.value.id, payload)
    members.value.push(m)
    ElMessage.success(`已添加 ${m.display_name || m.username}`)
  }

  function roleOf(userId: string): Member['role'] | undefined {
    return members.value.find(m => m.user_id === userId)?.role
  }

  function canWrite(): boolean {
    const role = current.value?.role
    return role === 'owner' || role === 'admin' || role === 'editor'
  }

  function canManage(): boolean {
    const role = current.value?.role
    return role === 'owner' || role === 'admin'
  }

  return {
    projects, current, members, categories, loadingProjects,
    fetchProjects, fetchAll, openProject, closeProject, createProject, deleteProject, syncToProd, updateCurrent,
    fetchCategories, addMember, roleOf, canWrite, canManage,
  }
})