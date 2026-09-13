import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { featureApi } from '@/api'
import type { Feature } from '@/types'

export const useFeatureStore = defineStore('feature', () => {
  const features = ref<Feature[]>([])
  const loading = ref(false)
  const selectedId = ref<string | null>(null)
  const trash = ref<Feature[]>([])

  const byId = computed(() => new Map(features.value.map(f => [f.id, f])))
  const selected = computed(() => (selectedId.value ? byId.value.get(selectedId.value) ?? null : null))

  async function fetchAll(projectId: string, includeDeleted = false) {
    loading.value = true
    try {
      features.value = await featureApi.list(projectId, { include_deleted: includeDeleted })
    } finally {
      loading.value = false
    }
  }

  function upsert(feature: Feature) {
    const i = features.value.findIndex(f => f.id === feature.id)
    if (i >= 0) features.value[i] = feature
    else features.value.unshift(feature)
  }

  function removeLocal(id: string) {
    features.value = features.value.filter(f => f.id !== id)
    if (selectedId.value === id) selectedId.value = null
  }

  function select(id: string | null) {
    selectedId.value = id
  }

  /** 只更新 properties（用于"隐藏/显示"这类视图标记，不影响几何与其他字段） */
  async function updateProperties(id: string, properties: Record<string, unknown>, version: number) {
    const updated = await featureApi.update(id, { version, properties })
    upsert(updated)
    return updated
  }

  /** 切换要素的隐藏标记（写入 properties.hidden，随 WS 同步到其他协作者） */
  async function toggleHidden(f: Feature) {
    const current = (f.properties || {}) as Record<string, unknown>
    const next: Record<string, unknown> = { ...current }
    if (next.hidden === true) delete next.hidden
    else next.hidden = true
    const updated = await updateProperties(f.id, next, f.version)
    return { feature: updated, hidden: next.hidden === true }
  }

  async function save(f: Feature): Promise<Feature> {
    const updated = await featureApi.update(f.id, {
      version: f.version,
      name: f.name,
      geometry: f.geometry_display as Record<string, unknown>,
      folder_id: f.folder_id,
      category_id: f.category_id,
      properties: f.properties as Record<string, unknown>,
      style: f.style as Record<string, unknown>,
    })
    upsert(updated)
    return updated
  }

  async function move(featureId: string, folderId: string | null, version: number) {
    const updated = await featureApi.move(featureId, folderId, version)
    upsert(updated)
    return updated
  }

  async function trashAll(projectId: string) {
    trash.value = await featureApi.trash(projectId)
  }

  async function restore(featureId: string) {
    const updated = await featureApi.restore(featureId)
    upsert(updated)
    trash.value = trash.value.filter(t => t.id !== featureId)
    return updated
  }

  function countByFolder(folderId: string | null): number {
    return features.value.filter(f => f.folder_id === folderId && !f.deleted_at).length
  }

  return {
    features, loading, selectedId, selected, trash, byId,
    fetchAll, upsert, removeLocal, select, save, move,
    trashAll, restore, countByFolder, updateProperties, toggleHidden,
  }
})