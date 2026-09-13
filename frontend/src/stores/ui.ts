import { ref } from 'vue'
import { defineStore } from 'pinia'

export type MapTool = 'select' | 'point' | 'circle' | 'polyline' | 'polygon' | 'measure' | 'area'

export const useUiStore = defineStore('ui', () => {
  const sidebarWidth = ref(300)
  const rightPanelOpen = ref(false)
  const detailPanel = ref(false)
  const activeTab = ref<'folders' | 'members' | 'audit' | 'trash'>('folders')
  const searchKeyword = ref('')
  const searchResults = ref<{ name: string; address: string; location: [number, number] }[]>([])
  const tool = ref<MapTool>('select')

  function setTool(t: MapTool) {
    tool.value = t
  }

  function openDetail() {
    detailPanel.value = true
    rightPanelOpen.value = true
  }

  function closeDetail() {
    detailPanel.value = false
    rightPanelOpen.value = false
  }

  return {
    sidebarWidth, rightPanelOpen, detailPanel, activeTab,
    searchKeyword, searchResults, tool, setTool, openDetail, closeDetail,
  }
})