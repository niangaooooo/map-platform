<template>
  <el-dialog v-model="visible" :title="renaming ? '重命名文件夹' : '新建文件夹'" width="380px" destroy-on-close>
    <el-form label-width="70px" @submit.prevent="save">
      <el-form-item label="名称" required>
        <el-input v-model="name" placeholder="如：石门街" maxlength="128" @keyup.enter="save" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useFolderStore } from '@/stores/folder'
import type { Folder } from '@/types'

const props = defineProps<{ projectId: string }>()

const folderStore = useFolderStore()
const visible = ref(false)
const renaming = ref(false)
const saving = ref(false)
const name = ref('')
const parentId = ref<string | null>(null)
const target = ref<Folder | null>(null)

function open(projectId: string, parentIdVal: string | null) {
  renaming.value = false
  name.value = ''
  parentId.value = parentIdVal
  visible.value = true
}

function rename(folder: Folder) {
  renaming.value = true
  target.value = folder
  name.value = folder.name
  visible.value = true
}

async function save() {
  if (!name.value.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    if (renaming.value && target.value) {
      await folderStore.rename(target.value.id, name.value.trim())
    } else {
      await folderStore.create(props.projectId, name.value.trim(), parentId.value)
    }
    visible.value = false
    ElMessage.success(renaming.value ? '已重命名' : '已创建')
  } catch {
    ElMessage.error('操作失败')
  } finally {
    saving.value = false
  }
}

defineExpose({ open, rename })
</script>