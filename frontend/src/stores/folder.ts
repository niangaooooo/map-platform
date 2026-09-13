import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { folderApi } from '@/api'
import type { Folder } from '@/types'

interface TreeFolder extends Folder {
  children: TreeFolder[]
}

export const useFolderStore = defineStore('folder', () => {
  const folders = ref<Folder[]>([])
  const loading = ref(false)
  const expanded = ref<Set<string>>(new Set())

  const tree = computed<TreeFolder[]>(() => {
    const map = new Map<string, TreeFolder>()
    const roots: TreeFolder[] = []
    for (const f of folders.value) {
      map.set(f.id, { ...f, children: [] })
    }
    for (const f of folders.value) {
      const node = map.get(f.id)!
      if (f.parent_id && map.has(f.parent_id)) {
        map.get(f.parent_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    }
    const sortRec = (nodes: TreeFolder[]) => {
      nodes.sort((a, b) => a.sort_order - b.sort_order)
      nodes.forEach(n => sortRec(n.children))
    }
    sortRec(roots)
    return roots
  })

  async function fetchAll(projectId: string) {
    loading.value = true
    try {
      folders.value = await folderApi.list(projectId)
      // 展开第一层
      folders.value.forEach(f => {
        if (!f.parent_id) expanded.value.add(f.id)
      })
    } finally {
      loading.value = false
    }
  }

  async function create(projectId: string, name: string, parent_id: string | null = null) {
    const f = await folderApi.create(projectId, { name, parent_id })
    folders.value.push(f)
    if (parent_id) expanded.value.add(parent_id)
    return f
  }

  async function rename(id: string, name: string) {
    const updated = await folderApi.update(id, { name })
    replace(updated)
  }

  async function toggleVisible(id: string, visible?: boolean) {
    const f = folders.value.find(x => x.id === id)
    if (!f) return
    const updated = await folderApi.update(id, { visible: visible ?? !f.visible })
    replace(updated)
  }

  async function moveTo(id: string, parent_id: string | null) {
    const updated = await folderApi.update(id, { parent_id })
    replace(updated)
  }

  async function remove(id: string) {
    await folderApi.remove(id)
    folders.value = folders.value.filter(f => f.id !== id)
  }

  function replace(updated: Folder) {
    const i = folders.value.findIndex(f => f.id === updated.id)
    if (i >= 0) folders.value[i] = updated
  }

  /** 某文件夹自身或其祖先是否隐藏（用于左侧树的可见性推导） */
  function isHidden(id: string): boolean {
    const f = folders.value.find(x => x.id === id)
    if (!f) return false
    if (!f.visible) return true
    if (f.parent_id) return isHidden(f.parent_id)
    return false
  }

  function collectDescendants(id: string): string[] {
    const ids: string[] = []
    const stack = [...folders.value.filter(f => f.parent_id === id)]
    while (stack.length) {
      const cur = stack.pop()!
      ids.push(cur.id)
      stack.push(...folders.value.filter(f => f.parent_id === cur.id))
    }
    return ids
  }

  return {
    folders, loading, expanded, tree,
    fetchAll, create, rename, toggleVisible, moveTo, remove, isHidden,
    collectDescendants,
  }
})