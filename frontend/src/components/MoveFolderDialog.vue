<template>
  <el-dialog v-model="visible" title="移动到文件夹" width="400px">
    <el-tree
      :data="folderStore.tree"
      node-key="id"
      :props="{ label: 'name', children: 'children' }"
      highlight-current
      :expand-on-click-node="false"
      @node-click="onPick"
      class="move-tree"
    >
      <template #default="{ data }">
        <span>{{ data.name }}</span>
      </template>
    </el-tree>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="moveTo(null)">移动到未分组</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useFolderStore } from '@/stores/folder'
import { useFeatureStore } from '@/stores/feature'
import type { Feature } from '@/types'

const folderStore = useFolderStore()
const featureStore = useFeatureStore()
const visible = ref(false)
let target: Feature | null = null
let pickedId: string | null = null

function open(f: Feature) {
  target = f
  pickedId = null
  visible.value = true
}

function onPick(data: any) {
  pickedId = data.id as string
}

async function moveTo(folderId: string | null) {
  if (!target) return
  const dest = folderId ?? pickedId
  try {
    const cur = featureStore.byId.get(target.id)
    const updated = await featureStore.move(`${target.id}`, dest, cur?.version ?? target.version)
    ElMessage.success('已移动')
    visible.value = false
  } catch {
    ElMessage.error('移动失败')
  }
}

defineExpose({ open })
</script>

<style scoped>
.move-tree { max-height: 320px; overflow: auto; }
</style>