<template>
  <div class="map-panel">
    <template v-if="props.feature">
      <div class="panel-head">
        <h3>{{ props.feature.name }}</h3>
        <el-button text :icon="Close" @click="emit('close')" />
      </div>

      <el-descriptions :column="1" size="small" border class="desc">
        <el-descriptions-item label="类型">{{ typeText(props.feature.feature_type) }}</el-descriptions-item>
        <el-descriptions-item label="坐标">{{ coordText }}</el-descriptions-item>
        <el-descriptions-item label="所属">{{ folderName }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ createdByName }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ dayjs(props.feature.created_at).format('YYYY-MM-DD HH:mm') }}</el-descriptions-item>
        <el-descriptions-item label="最后修改">
          {{ updatedByName }} · {{ dayjs(props.feature.updated_at).format('YYYY-MM-DD HH:mm') }}
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="props.feature.properties?.remark || props.feature.properties?.address" class="notes">
        <div v-if="props.feature.properties.address" class="note-line"><b>地址：</b>{{ props.feature.properties.address }}</div>
        <div v-if="props.feature.properties.remark" class="note-line"><b>备注：</b>{{ props.feature.properties.remark }}</div>
      </div>

      <!-- 与其他标点的距离（仅当选中标点时显示，按文件夹分组） -->
      <div v-if="isPoint && distGroups.length" class="distances">
        <div class="dist-title">📏 与其他标点的距离（点选查看 / 编辑）</div>
        <div v-for="grp in distGroups" :key="grp.key" class="dist-group">
          <div class="dist-group-title">
            {{ grp.folderName }} <span class="dist-group-count">{{ grp.items.length }}</span>
          </div>
          <div
            v-for="d in grp.items"
            :key="d.id"
            class="dist-item"
            :class="{ active: featureStore.selectedId === d.id }"
            @click="viewPoint(d)"
            @dblclick="editPoint(d)"
          >
            <span class="dist-name">{{ d.name }}</span>
            <span class="dist-val">{{ d.distText }}</span>
            <span class="dist-ops">
              <el-tooltip content="查看详情" placement="top"><span class="dist-op" @click.stop="viewPoint(d)">👁</span></el-tooltip>
              <el-tooltip content="编辑（名称/备注等）" placement="top"><span class="dist-op" @click.stop="editPoint(d)">✏️</span></el-tooltip>
            </span>
          </div>
        </div>
      </div>

      <div class="buttons">
        <el-button size="small" @click="openHistory">历史版本</el-button>
        <el-button size="small" @click="openProps">属性</el-button>
        <el-button size="small" @click="toggleHidden">
          {{ isHidden ? '👁 显示' : '🚫 隐藏' }}
        </el-button>
        <el-button size="small" type="primary" v-if="canWrite" @click="startEdit">编辑</el-button>
        <el-button size="small" type="danger" plain v-if="canWrite" @click="doDelete">删除</el-button>
      </div>

      <!-- 圆：绑定标点 -->
      <div v-if="isCircle" class="bind-box">
        <div class="bind-title">🎯 绑定标点</div>
        <div v-if="boundPoint" class="bind-info">
          已绑定：<b>{{ boundPoint.name }}</b>
          <el-button size="small" text type="danger" @click="unbindFromPoint">解除</el-button>
        </div>
        <div v-else class="bind-row">
          <el-select v-model="bindTargetId" placeholder="选择要跟随的标点" size="small" filterable style="flex: 1">
            <el-option v-for="pt in pointOptions" :key="pt.id" :label="pt.name" :value="pt.id" />
          </el-select>
          <el-button size="small" type="primary" :disabled="!bindTargetId" :loading="binding" @click="bindToPoint">绑定</el-button>
        </div>
        <div class="bind-tip">绑定后，移动 / 隐藏 / 删除该标点，圆都会同步跟随。</div>
      </div>

      <el-collapse v-if="versions.length" class="versions">
        <el-collapse-item title="历史版本">
          <div v-for="v in versions" :key="v.id" class="version-item">
            <span>v{{ v.version }} · {{ dayjs(v.created_at).format('MM-DD HH:mm') }}</span>
            <el-button size="small" text type="primary" @click="restoreVersion(v)">恢复</el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>

    <el-empty v-else description="选中一个地图对象查看详情" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { useProjectStore } from '@/stores/project'
import { useFeatureStore } from '@/stores/feature'
import { useFolderStore } from '@/stores/folder'
import { useCollaborationStore } from '@/stores/collaboration'
import { useAuthStore } from '@/stores/auth'
import { featureApi } from '@/api'
import { boundParentId, isFeatureHidden } from '@/services/AmapMapService'
import type { Feature, FeatureVersion } from '@/types'

const props = defineProps<{ feature: Feature | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'locate', lng: number, lat: number): void
  (e: 'edit', id: string): void
  (e: 'editprops', id: string): void
  (e: 'visibility', feature: Feature): void
  (e: 'bound', feature: Feature): void
  (e: 'childRemoved', id: string): void
  (e: 'view', id: string): void
}>()

const projectStore = useProjectStore()
const featureStore = useFeatureStore()
const folderStore = useFolderStore()
const collaboration = useCollaborationStore()
const auth = useAuthStore()
const versions = ref<FeatureVersion[]>([])

const canWrite = computed(() => projectStore.canWrite())

// ---- 隐藏 / 显示 ----
const isHidden = computed(() => isFeatureHidden(props.feature))

/** 切换要素在地图上的显示/隐藏（标记存 properties.hidden，随要素同步给其他协作者） */
async function toggleHidden() {
  const f = props.feature
  if (!f) return
  try {
    const { feature } = await featureStore.toggleHidden(f)
    emit('visibility', feature)
    ElMessage.success(isFeatureHidden(feature) ? '已隐藏，可在图层列表重新显示' : '已显示')
  } catch {
    ElMessage.error('操作失败，数据可能已被他人修改')
  }
}

// ---- 与其他标点的距离 ----
const isPoint = computed(() => props.feature?.feature_type === 'point')

// ---- 圆绑定标点 ----
const isCircle = computed(() => props.feature?.feature_type === 'circle')
const bindTargetId = ref('')
const binding = ref(false)

/** 可选的父标点：项目内所有未被删除的标点 */
const pointOptions = computed(() => {
  const fid = props.feature?.id
  return featureStore.features.filter(f => f.feature_type === 'point' && !f.deleted_at && f.id !== fid)
})

const boundPoint = computed(() => {
  const pid = props.feature ? boundParentId(props.feature) : undefined
  if (!pid) return null
  return featureStore.byId.get(pid) ?? null
})

/** 绑定：把圆心对齐到标点位置，并写入 parent_point_id */
async function bindToPoint() {
  const f = props.feature
  const pt = bindTargetId.value ? featureStore.byId.get(bindTargetId.value) : null
  if (!f || !pt) return
  const ptCoord = (pt.geometry_display as any)?.coordinates
  if (!ptCoord || ptCoord.length < 2) {
    ElMessage.warning('该标点坐标无效')
    return
  }
  const cur = featureStore.byId.get(f.id) ?? f
  const cg = (cur.geometry_display as any) || {}
  binding.value = true
  try {
    const props2: Record<string, unknown> = { ...((cur.properties || {}) as Record<string, unknown>), parent_point_id: pt.id }
    const updated = await featureApi.update(cur.id, {
      version: cur.version,
      properties: props2,
      geometry: { type: 'Circle', center: [ptCoord[0], ptCoord[1]], radius: cg.radius ?? 500 },
    })
    featureStore.upsert(updated)
    emit('bound', updated)
    ElMessage.success(`已绑定到「${pt.name}」`)
  } catch {
    ElMessage.error('绑定失败，数据可能已被他人修改')
  } finally {
    binding.value = false
    bindTargetId.value = ''
  }
}

/** 解除绑定：圆心保持当前位置，仅移除 parent_point_id */
async function unbindFromPoint() {
  const f = props.feature
  if (!f) return
  const cur = featureStore.byId.get(f.id) ?? f
  const props2: Record<string, unknown> = { ...((cur.properties || {}) as Record<string, unknown>) }
  delete props2.parent_point_id
  try {
    const updated = await featureApi.update(cur.id, { version: cur.version, properties: props2 })
    featureStore.upsert(updated)
    emit('bound', updated)
    ElMessage.success('已解除绑定')
  } catch {
    ElMessage.error('解除绑定失败，数据可能已被他人修改')
  }
}

const pointDistances = computed(() => {
  const f = props.feature
  if (!f || f.feature_type !== 'point') return []
  const g = f.geometry_display as any
  const my = g?.coordinates
  if (!my || my.length < 2) return []

  const out: {
    id: string
    name: string
    lng: number
    lat: number
    distText: string
    meters: number
    folderId: string | null
    folderName: string
  }[] = []
  for (const other of featureStore.features) {
    if (other.id === f.id || other.deleted_at || other.feature_type !== 'point') continue
    const og = other.geometry_display as any
    const oc = og?.coordinates
    if (!oc || oc.length < 2) continue
    const meters = haversine(my[1], my[0], oc[1], oc[0])
    const folder = other.folder_id ? folderStore.folders.find(fd => fd.id === other.folder_id) : undefined
    out.push({
      id: other.id,
      name: other.name || '(未命名)',
      lng: oc[0],
      lat: oc[1],
      meters,
      distText: formatDist(meters),
      folderId: other.folder_id,
      folderName: folder?.name || '未分组',
    })
  }
  return out.sort((a, b) => a.meters - b.meters)
})

/** 按文件夹分组（未分组归为「未分组」，放在最后） */
const distGroups = computed(() => {
  const items = pointDistances.value
  const groups = new Map<string, { key: string; folderName: string; items: typeof items }>()
  const ungroupedKey = '__ungrouped__'
  for (const d of items) {
    const key = d.folderId || ungroupedKey
    const folderName = d.folderId ? d.folderName : '未分组'
    if (!groups.has(key)) groups.set(key, { key, folderName, items: [] })
    groups.get(key)!.items.push(d)
  }
  const list = [...groups.values()]
  // 已分组按文件夹树顺序、未分组排最后
  const order = new Map(folderStore.folders.map((f, i) => [f.id, i]))
  list.sort((a, b) => {
    if (a.key === ungroupedKey) return 1
    if (b.key === ungroupedKey) return -1
    return (order.get(a.key) ?? 999) - (order.get(b.key) ?? 999)
  })
  return list
})

/** 单击：把该标点设为当前查看对象（面板顶部随之切换为该标点详情） */
function viewPoint(d: { id: string; lng: number; lat: number }) {
  emit('view', d.id)
  emit('locate', d.lng, d.lat)
}

/** 双击或铅笔：直接打开该标点的属性编辑（名称/分组/颜色/备注等） */
function editPoint(d: { id: string }) {
  emit('editprops', d.id)
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatDist(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(2)} km`
  return `${Math.round(m)} m`
}

const coordText = computed(() => {
  const g = props.feature?.geometry_display as any
  if (!g) return '—'
  if (props.feature?.feature_type === 'point') {
    const c = g.coordinates
    return c ? `${c[0].toFixed(6)}, ${c[1].toFixed(6)}` : '—'
  }
  if (props.feature?.feature_type === 'circle') {
    return `圆心 ${g.center?.[0].toFixed(6)}, ${g.center?.[1].toFixed(6)} · 半径 ${g.radius}m`
  }
  const pts = g.coordinates?.[0]?.length ?? g.coordinates?.length ?? 0
  return `${pts} 个点`
})
const folderName = computed(() => {
  if (!props.feature?.folder_id) return '未分组'
  return folderStore.folders.find(x => x.id === props.feature?.folder_id)?.name || '未分组'
})
const createdByName = computed(() => {
  const u = projectStore.members.find(m => m.user_id === props.feature?.created_by)
  return u?.display_name || u?.username || '—'
})
const updatedByName = computed(() => {
  const u = projectStore.members.find(m => m.user_id === props.feature?.updated_by)
  return u?.display_name || u?.username || '—'
})

function typeText(t: string) {
  return ({ point: '点', circle: '圆', polyline: '线', polygon: '多边形' } as const)[t as 'point' | 'circle' | 'polyline' | 'polygon'] ?? t
}

/** 打开属性编辑（名称 / 分组 / 颜色等），由 MapView 承载对话框 */
function openProps() {
  const f = props.feature
  if (f) emit('editprops', f.id)
}

async function openHistory() {
  if (!props.feature) return
  versions.value = await featureApi.versions(props.feature.id)
}

async function restoreVersion(v: FeatureVersion) {
  if (!props.feature) return
  try {
    await ElMessageBox.confirm(`恢复到 v${v.version}？当前状态将另存为新版本。`, '提示', { type: 'warning' })
    const updated = await featureApi.restoreVersion(props.feature.id, v.version)
    featureStore.upsert(updated)
    emit('close')
    ElMessage.success('已恢复')
  } catch {
    /* 取消 */
  }
}

async function startEdit() {
  const f = props.feature
  if (!f) return
  // 只做占用检查，真正加锁由 MapView.startEditFromPanel 统一处理
  if (collaboration.locks[f.id] && collaboration.locks[f.id].user_id !== auth.user?.id) {
    ElMessage.warning(`${collaboration.locks[f.id].username} 正在编辑该对象`)
    return
  }
  // 触发地图上的编辑模式（MapView 中加锁并打开编辑器）
  emit('edit', f.id)
  emit('close')
}

async function doDelete() {
  const f = props.feature
  if (!f) return
  try {
    // 删除标点 → 绑定圆一并删除
    const children = f.feature_type === 'point'
      ? featureStore.features.filter(c => !c.deleted_at && c.feature_type === 'circle' && boundParentId(c) === f.id)
      : []
    const extra = children.length ? `\n另有 ${children.length} 个绑定该标点的圆将一并删除。` : ''
    await ElMessageBox.confirm(`删除「${f.name}」？将移入回收站。${extra}`, '确认删除', { type: 'warning' })
    await featureApi.remove(f.id)
    featureStore.removeLocal(f.id)
    emit('close')
    for (const child of children) {
      await featureApi.remove(child.id)
      featureStore.removeLocal(child.id)
      emit('childRemoved', child.id)
    }
  } catch {
    /* 取消 */
  }
}

watch(() => props.feature?.id, () => {
  versions.value = []
  bindTargetId.value = ''
})
</script>

<style scoped>
.map-panel { padding: 12px; height: 100%; }
.panel-head { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f0f0f0; padding-bottom: 8px; margin-bottom: 10px; }
.panel-head h3 { margin: 0; font-size: 16px; }
.desc { margin-bottom: 12px; }
.notes { background: #fafafa; border-radius: 6px; padding: 8px 10px; font-size: 13px; margin-bottom: 12px; }
.note-line { margin: 2px 0; }
.buttons { display: flex; gap: 8px; margin: 8px 0 16px; }
.distances { background: #f7f9ff; border-radius: 6px; padding: 8px 10px; margin-bottom: 12px; max-height: 260px; overflow: auto; }
.dist-title { font-size: 13px; font-weight: 600; color: #1677ff; margin-bottom: 6px; }
.dist-group-title { font-size: 12px; font-weight: 600; color: #888; margin: 8px 0 2px; display: flex; align-items: center; gap: 6px; }
.dist-group:first-child .dist-group-title { margin-top: 0; }
.dist-group-count { font-size: 11px; color: #bbb; font-weight: 400; }
.dist-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 6px; font-size: 13px; cursor: pointer; border-radius: 4px; gap: 8px; }
.dist-item:hover { background: #eef4ff; }
.dist-item.active { background: #e0ecff; }
.dist-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dist-val { color: #666; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.dist-ops { display: none; flex-shrink: 0; gap: 2px; }
.dist-item:hover .dist-ops, .dist-item.active .dist-ops { display: inline-flex; }
.dist-op { cursor: pointer; padding: 0 3px; border-radius: 3px; font-size: 13px; }
.dist-op:hover { background: #fff; }
.version-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 13px; }
.bind-box { background: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px; padding: 8px 10px; margin: 4px 0 12px; }
.bind-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.bind-info { display: flex; align-items: center; justify-content: space-between; font-size: 13px; gap: 6px; }
.bind-row { display: flex; gap: 6px; align-items: center; }
.bind-tip { font-size: 12px; color: #999; margin-top: 6px; line-height: 1.5; }
</style>