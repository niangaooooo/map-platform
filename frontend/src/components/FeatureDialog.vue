<template>
  <el-dialog v-model="visible" :title="editing ? '编辑对象' : `新建${typeText}`" width="520px" destroy-on-close>
    <el-form label-width="80px" size="default">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="如：病例001" maxlength="128" />
      </el-form-item>

      <el-form-item label="分类">
        <el-select v-model="form.category_id" clearable placeholder="选择分类（可选）" style="width: 100%">
          <el-option v-for="c in projectStore.categories" :key="c.id" :label="c.name" :value="c.id">
            <span class="cat-opt"><i :style="{ background: c.color }" class="cat-dot" />{{ c.name }}</span>
          </el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="所属文件夹">
        <el-select v-model="form.folder_id" clearable placeholder="未分组" style="width: 100%">
          <el-option label="（未分组）" :value="null" />
          <el-option v-for="f in flatFolders" :key="f.id" :label="'　'.repeat(f.depth) + f.name" :value="f.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="颜色">
        <div class="color-row">
          <el-color-picker v-model="form.color" />
          <span v-if="form.color" class="color-hex">{{ form.color }}</span>
        </div>
      </el-form-item>

      <el-form-item v-if="createType === 'circle'" label="半径(米)">
        <el-input-number v-model="form.radius" :min="1" :max="100000" style="width: 100%" />
      </el-form-item>

      <el-form-item label="地址">
        <el-input v-model="form.address" placeholder="地址/描述（可选）" />
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="备注（可选）" />
      </el-form-item>

      <div v-if="geometryInfo" class="geo-info">📍 {{ geometryInfo }}</div>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { Feature } from '@/types'
import { featureApi } from '@/api'
import { useProjectStore } from '@/stores/project'
import { useFolderStore } from '@/stores/folder'
import { useFeatureStore } from '@/stores/feature'

const props = defineProps<{ projectId: string }>()

const projectStore = useProjectStore()
const folderStore = useFolderStore()
const featureStore = useFeatureStore()

const visible = ref(false)
const editing = ref(false)
const saving = ref(false)
const createType = ref('point')
const geometry = ref<Record<string, unknown> | null>(null)
const editingId = ref('')

const form = reactive({
  name: '',
  category_id: null as string | null,
  folder_id: null as string | null,
  color: '#FF5A5F',
  radius: 500,
  address: '',
  remark: '',
})

const flatFolders = computed(() => {
  const out: { id: string; name: string; depth: number }[] = []
  const walk = (nodes: any[], depth: number) => {
    for (const n of nodes) {
      out.push({ id: n.id, name: n.name, depth })
      walk(n.children || [], depth + 1)
    }
  }
  walk(folderStore.tree, 0)
  return out
})

const typeText = computed(() =>
  ({ point: '标点', circle: '画圆', polyline: '画线', polygon: '画多边形' } as const)[createType.value as 'point' | 'circle' | 'polyline' | 'polygon'] ?? '对象'
)

const geometryInfo = computed(() => {
  if (!geometry.value) return ''
  const g = geometry.value as any
  if (g.type === 'Point') {
    const c = g.coordinates
    return `点：${c[0].toFixed(6)}, ${c[1].toFixed(6)}`
  }
  if (g.type === 'Circle') return `圆：半径 ${g.radius} 米`
  if (g.type === 'LineString') return `线：${g.coordinates.length} 个点`
  if (g.type === 'Polygon') return `多边形：${g.coordinates?.[0]?.length ?? 0} 个顶点`
  return ''
})

function openForCreate(type: string, geo: Record<string, unknown>) {
  editing.value = false
  createType.value = type
  geometry.value = geo
  Object.assign(form, {
    name: '',
    category_id: null,
    folder_id: null,
    color: '#FF5A5F',
    radius: 500,
    address: '',
    remark: '',
  })
  if (type === 'circle' && (geo as any).radius) form.radius = Math.round((geo as any).radius)
  editingId.value = ''
  visible.value = true
}

function openForEdit(f: Feature) {
  editing.value = true
  createType.value = f.feature_type
  geometry.value = f.geometry_display as Record<string, unknown>
  editingId.value = f.id
  Object.assign(form, {
    name: f.name,
    category_id: f.category_id,
    folder_id: f.folder_id,
    color: (f.style?.color as string) || '#FF5A5F',
    radius: (f.geometry_display as any)?.radius ?? 500,
    address: (f.properties?.address as string) || '',
    remark: (f.properties?.remark as string) || '',
  })
  visible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    const style = { color: form.color }
    if (editing.value) {
      const cur = featureStore.byId.get(editingId.value)
      if (!cur) throw new Error('对象不存在')
      // 保留已有 properties 中的隐藏标记 / 绑定关系等，只更新地址与备注
      const mergedProps: Record<string, unknown> = { ...((cur.properties || {}) as Record<string, unknown>) }
      mergedProps.address = form.address
      mergedProps.remark = form.remark
      const payload: Record<string, unknown> = {
        version: cur.version,
        name: form.name,
        category_id: form.category_id,
        folder_id: form.folder_id,
        properties: mergedProps,
        style,
      }
      // 仅 Circle 允许在对话框改半径（其余几何交回地图编辑器，避免产生无谓的历史版本）
      if (createType.value === 'circle' && (geometry.value as any)?.type === 'Circle') {
        payload.geometry = { ...(geometry.value as any), radius: form.radius }
      }
      const updated = await featureApi.update(editingId.value, payload as any)
      featureStore.upsert(updated)
      emit('created', updated)
    } else {
      const properties: Record<string, unknown> = { address: form.address, remark: form.remark }
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        feature_type: createType.value,
        geometry: geometry.value,
        folder_id: form.folder_id,
        category_id: form.category_id,
        properties,
        style: { color: form.color },
      }
      // Circle 由 MouseTool 画出的带 radius；直接手填半径则覆盖
      if (createType.value === 'circle' && (geometry.value as any).type === 'Circle') {
        payload.geometry = { ...(geometry.value as any), radius: form.radius }
      }
      const created = await featureApi.create(props.projectId, payload as any)
      featureStore.upsert(created)
      emit('created', created)
    }
    visible.value = false
    ElMessage.success('已保存')
  } catch (e: any) {
    // 后端业务错误优先；网络/超时等错误给友好提示
    const detail = e?.response?.data?.detail
    if (detail) {
      ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    } else if (e?.code === 'ECONNABORTED' || e?.message?.includes('timeout')) {
      ElMessage.error('保存超时，请确认服务运行后重试')
    } else if (!e?.response) {
      ElMessage.error('无法连接服务器，请检查后端服务是否在运行')
    } else {
      ElMessage.error('保存失败：' + (e?.message || '未知错误'))
    }
  } finally {
    saving.value = false
  }
}

const emit = defineEmits<{ (e: 'created', f: any): void }>()

defineExpose({ openForCreate, openForEdit })
</script>

<style scoped>
.color-row { display: flex; align-items: center; gap: 8px; }
.color-hex { color: #999; font-size: 13px; }
.cat-option { display: inline-flex; align-items: center; gap: 6px; }
.cat-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.geo-info { background: #f7f9ff; border-radius: 6px; padding: 8px 10px; font-size: 13px; color: #1677ff; margin-bottom: 8px; }
</style>