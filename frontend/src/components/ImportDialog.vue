<template>
  <el-dialog v-model="visible" title="导入数据" width="520px">
    <el-steps :active="0" align-center finish-status="success" class="steps">
      <el-step title="选择文件" />
      <el-step title="确认参数" />
      <el-step title="完成" />
    </el-steps>

    <el-radio-group v-model="fileType" class="type-radio">
      <el-radio-button value="csv">CSV</el-radio-button>
      <el-radio-button value="geojson">GeoJSON</el-radio-button>
    </el-radio-group>

    <el-upload
      drag
      :auto-upload="false"
      :limit="1"
      accept=".csv,.geojson,.json"
      :on-change="onChange"
      :on-remove="onRemove"
      class="uploader"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">拖拽文件到此处，或<em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">
          CSV 列：name, longitude, latitude, address, category, folder, remark
        </div>
      </template>
    </el-upload>

    <el-form label-width="100px" class="import-form">
      <el-form-item label="坐标系">
        <el-radio-group v-model="crs">
          <el-radio value="GCJ02">GCJ02（高德）</el-radio>
          <el-radio value="WGS84">WGS84（GPS，自动转换）</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" :disabled="!file" @click="doImport">开始导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { importApi } from '@/api'

const props = defineProps<{ projectId: string }>()
const visible = ref(false)
const file = ref<File | null>(null)
const fileType = ref('csv')
const crs = ref<'GCJ02' | 'WGS84'>('GCJ02')
const loading = ref(false)

function open() {
  visible.value = true
  file.value = null
}

function onChange(uploadFile: any) {
  file.value = uploadFile.raw || null
  if (file.value) {
    const name = file.value.name.toLowerCase()
    fileType.value = name.endsWith('.csv') ? 'csv' : 'geojson'
  }
}

function onRemove() {
  file.value = null
}

async function doImport() {
  if (!file.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  loading.value = true
  try {
    const result = await importApi.importFile(props.projectId, file.value, crs.value)
    ElMessage.success(`导入完成：新增 ${result.created} 条，跳过 ${result.skipped} 条`)
    if (result.errors.length) {
      console.warn('导入错误明细', result.errors)
    }
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.steps { margin-bottom: 16px; }
.import-radio { margin-bottom: 12px; }
.uploader { margin-bottom: 12px; }
.import-form { margin-top: 8px; }
</style>