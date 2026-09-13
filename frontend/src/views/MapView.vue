<template>
  <div class="map-page" v-if="loaded">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="left">
        <span class="back" @click="goBack">←</span>
        <span class="proj-name">{{ projectStore.current?.name }}</span>
        <span class="role-tag" :class="'r-' + (projectStore.current?.role || 'viewer')">{{ roleTextOf(projectStore.current?.role || 'viewer') }}</span>
      </div>
      <div class="center">
        <el-input
          v-model="uiStore.searchKeyword"
          placeholder="搜索地址 / POI，回车定位"
          clearable
          size="small"
          class="search-input"
          @keyup.enter="doSearch"
        >
          <template #append>
            <el-button :icon="Search" @click="doSearch" />
          </template>
        </el-input>
      </div>
      <div class="right">
        <span v-if="collaboration.connected" class="conn-badge"><i class="dot" />在线 {{ collaboration.online.length }}</span>
        <span v-else class="conn-badge offline">连接中…</span>
        <el-dropdown @command="onTopCommand">
          <span class="user-chip">{{ auth.user?.display_name || auth.user?.username }}</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="refresh">刷新数据</el-dropdown-item>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="body">
      <!-- 左侧面板 -->
      <aside class="sidebar">
        <el-tabs v-model="uiStore.activeTab" class="side-tabs">
          <el-tab-pane label="图层" name="folders" class="tab-pane-folders">
            <div class="tree-toolbar">
              <el-button size="small" type="primary" text :icon="Plus" @click="addFolder(null)">新建文件夹</el-button>
              <el-button size="small" text :icon="Refresh" @click="reloadData" />
            </div>
            <el-tree
              ref="folderTreeRef"
              :data="layerTree"
              node-key="id"
              :props="{ label: 'name', children: 'children' }"
              :expand-on-click-node="false"
              :default-expanded-keys="treeExpandedKeys"
              draggable
              :allow-drag="allowTreeDrag"
              :allow-drop="allowDrop"
              @node-drop="onFolderDrop"
              @node-click="onTreeClick"
              @node-collapse="onNodeCollapse"
              @node-expand="onNodeExpand"
              class="folder-tree"
            >
              <template #default="{ data }">
                <!-- 文件夹节点 -->
                <div v-if="data.kind !== 'feature'" class="folder-node">
                  <el-icon class="f-ico"><Folder /></el-icon>
                  <span class="f-name">{{ data.name }}</span>
                  <span class="count">{{ data.featureCount }}</span>
                  <el-dropdown trigger="click" @command="(cmd: string) => onFolderCmd(cmd, data)">
                    <el-icon class="more"><MoreFilled /></el-icon>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="rename">重命名</el-dropdown-item>
                        <el-dropdown-item command="new-sub">新建子文件夹</el-dropdown-item>
                        <el-dropdown-item command="toggle">{{ data.visible ? '隐藏' : '显示' }}</el-dropdown-item>
                        <el-dropdown-item divided command="delete">删除</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
                <!-- 标点节点 -->
                <div v-else class="feature-node" @contextmenu.prevent.stop="onFeatureNodeMenu($event, data)">
                  <span class="f-type">{{ featureTypeIcon(data.feature_type) }}</span>
                  <span
                    class="f-name"
                    :class="{ 'is-selected': featureStore.selectedId === data.feature_id, 'is-hidden': data.hidden }"
                  >{{ data.name }}</span>
                  <!-- 显隐开关：隐藏后地图上不显示，图层列表仍可见且可随时恢复 -->
                  <el-tooltip :content="data.hidden ? '显示' : '隐藏'" placement="top">
                    <span class="f-eye" :class="{ 'always': data.hidden }" @click.stop="toggleFeatureHidden(data)">
                      {{ data.hidden ? '🚫' : '👁' }}
                    </span>
                  </el-tooltip>
                </div>
              </template>
            </el-tree>
            <div class="tree-footer">
              <el-button size="small" text @click="openTrash">🗑 回收站</el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="成员" name="members">
            <div class="members-panel">
              <div v-for="m in projectStore.members" :key="m.user_id" class="member-item">
                <span class="m-name">{{ m.display_name || m.username }}</span>
                <el-tag size="small" :type="tagType(m.role)">{{ roleTextOf(m.role) }}</el-tag>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="日志" name="audit">
            <div class="audit-panel">
              <div v-for="log in auditLogs" :key="log.id" class="audit-item">
                <div class="a-head">
                  <b>{{ log.user_display_name || log.username || '系统' }}</b>
                  <span class="a-action">{{ actionText(log.action) }}</span>
                </div>
                <div class="a-time">{{ dayjs(log.created_at).format('MM-DD HH:mm') }}</div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </aside>

      <!-- 地图 -->
      <main class="map-wrap">
        <div ref="mapEl" class="map-container"></div>

        <div v-if="searchResults.length" class="search-results">
          <div v-for="(r, i) in searchResults" :key="i" class="sr-item" @click="locateResult(r)">
            <div class="sr-name">{{ r.name }}
              <span v-if="r.distance != null" class="sr-dist" :class="{ 'in-view': r.distance <= 5000 }">{{ r.distance < 1000 ? Math.round(r.distance) + 'm' : (r.distance / 1000).toFixed(1) + 'km' }}</span>
            </div>
            <div class="sr-addr">{{ r.address }}</div>
          </div>
        </div>

        <div class="online-panel">
          <div class="op-title">当前在线 {{ collaboration.online.length }} 人</div>
          <div v-for="m in collaboration.online" :key="m.id" class="op-member">
            <i class="dot" /> {{ m.display_name || m.username }}
          </div>
        </div>

        <transition name="fade">
          <div v-if="collaboration.lastActivity" class="activity-toast">{{ collaboration.lastActivity.text }}</div>
        </transition>

        <!-- 右键菜单 -->
        <div
          v-if="contextMenu.visible"
          ref="contextMenuEl"
          class="context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        >
          <div class="cm-title">{{ contextMenu.feature?.name }}</div>
          <div class="cm-item" @click="viewFeature">查看详情</div>
          <div class="cm-item" v-if="canWrite" @click="startEditFeature">编辑形状</div>
          <div class="cm-item" v-if="canWrite" @click="editFeatureProps(contextMenu.feature?.id)">编辑属性…</div>
          <div class="cm-item" @click="toggleHiddenFromMenu">
            {{ contextMenu.feature && isHidden(contextMenu.feature) ? '👁 显示' : '🚫 隐藏' }}
          </div>
          <div class="cm-item" v-if="canWrite" @click="moveToFolder">移动到文件夹…</div>
          <div class="cm-item cm-sp" v-if="contextMenu.feature?.feature_type === 'point'" @click="genCircle(100)">生成 100m 圆</div>
          <div class="cm-item" v-if="contextMenu.feature?.feature_type === 'point'" @click="genCircle(300)">生成 300m 圆</div>
          <div class="cm-item" v-if="contextMenu.feature?.feature_type === 'point'" @click="genCircle(1000)">生成 1km 圆</div>
          <div class="cm-item" @click="nearbySearch">查找附近对象…</div>
          <div class="cm-item danger" v-if="canWrite" @click="deleteFeature">删除</div>
        </div>
      </main>

      <!-- 右侧属性面板 -->
      <transition name="slide">
        <aside v-if="uiStore.rightPanelOpen" class="right-panel">
          <MapPanel
            :feature="featureStore.selected"
            @close="uiStore.closeDetail()"
            @locate="onLocateFromPanel"
            @edit="startEditFromPanel"
            @editprops="editFeatureProps"
            @visibility="onFeatureVisibilityChanged"
            @bound="onFeatureChanged"
            @child-removed="onChildRemoved"
            @view="onViewFeatureFromPanel"
          />
        </aside>
      </transition>
    </div>

    <!-- 底部工具栏 -->
    <div class="toolbar">
      <el-tooltip content="选择 (V)"><el-button :type="toolBtn('select')" :icon="Pointer" @click="setTool('select')" /></el-tooltip>
      <el-tooltip content="标点 (M)"><el-button :type="toolBtn('point')" :icon="Location" @click="setTool('point')" /></el-tooltip>
      <el-tooltip content="画圆 (C)"><el-button :type="toolBtn('circle')" :icon="Aim" @click="setTool('circle')" /></el-tooltip>
      <el-tooltip content="画线 (L)"><el-button :type="toolBtn('polyline')" :icon="Operation" @click="setTool('polyline')" /></el-tooltip>
      <el-tooltip content="画多边形 (P)"><el-button :type="toolBtn('polygon')" :icon="Crop" @click="setTool('polygon')" /></el-tooltip>
      <el-divider direction="vertical" />
      <el-tooltip content="测距 (R)"><el-button :type="toolBtn('measure')" :icon="Odometer" @click="setTool('measure')" /></el-tooltip>
      <el-tooltip content="测面积"><el-button :type="toolBtn('area')" :icon="DataAnalysis" @click="setTool('area')" /></el-tooltip>
      <el-divider direction="vertical" />
      <el-tooltip content="撤销 (Ctrl+Z)"><el-button :icon="RefreshLeft" :disabled="undoStack.length === 0" @click="undo()" /></el-tooltip>
      <el-tooltip content="重做 (Ctrl+Shift+Z)"><el-button :icon="RefreshRight" :disabled="redoStack.length === 0" @click="redoAction()" /></el-tooltip>
      <el-divider direction="vertical" />
      <el-tooltip content="删除选中 (Delete)"><el-button :icon="Delete" @click="deleteSelected" /></el-tooltip>
      <el-tooltip content="删除选中 (Delete)"><el-button :icon="Delete" @click="deleteSelected" /></el-tooltip>
      <el-tooltip content="定位到我"><el-button :icon="Position" @click="locateMe" /></el-tooltip>
      <el-tooltip :content="baseLayer === 'satellite' ? '切换为平面地图' : '切换为卫星地图'">
        <el-button data-testid="toggle-base" :icon="Picture" @click="toggleBaseLayer" />
      </el-tooltip>
      <el-tooltip content="复位"><el-button :icon="Refresh" @click="resetView" /></el-tooltip>
      <el-tooltip content="导入"><el-button :icon="Upload" @click="importDialogRef?.open()" /></el-tooltip>
      <el-dropdown trigger="click" @command="onExportCommand">
        <el-tooltip content="导出备份">
          <el-button :icon="Download" :loading="exporting" />
        </el-tooltip>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="backup" icon="Document">完整备份（.json，可完整还原）</el-dropdown-item>
            <el-dropdown-item command="geojson" icon="Document">GeoJSON（通用地理数据）</el-dropdown-item>
            <el-dropdown-item command="csv" icon="Document">CSV（表格，仅点/圆中心）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 弹窗 -->
    <FeatureDialog ref="featureDialogRef" :project-id="projectId" @created="onFeatureCreated" />
    <FolderDialog ref="folderDialogRef" :project-id="projectId" />
    <MoveFolderDialog ref="moveDialogRef" />
    <NearbyDialog ref="nearbyDialogRef" :project-id="projectId" />
    <ImportDialog ref="importDialogRef" :project-id="projectId" />

    <el-dialog v-model="trashVisible" title="回收站" width="680px">
      <el-table :data="featureStore.trash" size="small">
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="feature_type" label="类型" width="90" />
        <el-table-column prop="deleted_at" label="删除时间" width="160" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="restoreTrash(row)">恢复</el-button>
            <el-button size="small" type="danger" text @click="purgeTrash(row)">永久删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Aim, Crop, DataAnalysis, Delete, Download, Folder, Location, MoreFilled,
  Odometer, Operation, Picture, Plus, Pointer, Position, Refresh, RefreshLeft, RefreshRight,
  Search, Upload,
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { useFolderStore } from '@/stores/folder'
import { useFeatureStore } from '@/stores/feature'
import { useUiStore } from '@/stores/ui'
import { useCollaborationStore } from '@/stores/collaboration'
import { createMapService } from '@/services'
import { boundParentId, isFeatureHidden } from '@/services/AmapMapService'
import type { MapService, MapToolType } from '@/services/MapService'
import type { Feature } from '@/types'
import { featureApi, projectApi, importApi } from '@/api'
import MapPanel from '@/components/MapPanel.vue'
import FeatureDialog from '@/components/FeatureDialog.vue'
import FolderDialog from '@/components/FolderDialog.vue'
import MoveFolderDialog from '@/components/MoveFolderDialog.vue'
import NearbyDialog from '@/components/NearbyDialog.vue'
import ImportDialog from '@/components/ImportDialog.vue'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectStore = useProjectStore()
const folderStore = useFolderStore()
const featureStore = useFeatureStore()
const uiStore = useUiStore()
const collaboration = useCollaborationStore()

const projectId = computed(() => String(route.params.id))
const mapEl = ref<HTMLElement | null>(null)
const loaded = ref(false)
const auditLogs = ref<Awaited<ReturnType<typeof projectApi.audit>>['items']>([])
const undoStack = ref<Feature[]>([])
const redoStack = ref<Feature[]>([])
const contextMenuEl = ref<HTMLElement | null>(null)
const contextMenu = ref<{ visible: boolean; x: number; y: number; feature: Feature | null }>({
  visible: false, x: 0, y: 0, feature: null,
})

/** 打开右键菜单：x/y 为视口坐标（clientX/Y），并确保菜单不超出屏幕右侧/底部 */
function openContextMenu(feature: Feature, clientX: number, clientY: number) {
  contextMenu.value = { visible: true, x: clientX, y: clientY, feature }
  // fixed 菜单渲染完成后，若越界则回移到可视范围内
  requestAnimationFrame(() => {
    const el = contextMenuEl.value
    if (!el) return
    const r = el.getBoundingClientRect()
    const m = 6
    let nx = contextMenu.value.x
    let ny = contextMenu.value.y
    if (r.right > window.innerWidth - m) nx = Math.max(m, window.innerWidth - r.width - m)
    if (r.bottom > window.innerHeight - m) ny = Math.max(m, window.innerHeight - r.height - m)
    if (nx !== contextMenu.value.x || ny !== contextMenu.value.y) {
      contextMenu.value = { ...contextMenu.value, x: nx, y: ny }
    }
  })
}
const trashVisible = ref(false)
const exporting = ref(false)

/** 树 ref：受控展开需要（default-expanded-keys 直接作用于 el-tree，ref 主要用于将来可能的程序化操作） */
const folderTreeRef = ref<any>(null)

const featureDialogRef = ref<InstanceType<typeof FeatureDialog> | null>(null)
const folderDialogRef = ref<InstanceType<typeof FolderDialog> | null>(null)
const moveDialogRef = ref<InstanceType<typeof MoveFolderDialog> | null>(null)
const nearbyDialogRef = ref<InstanceType<typeof NearbyDialog> | null>(null)
const importDialogRef = ref<InstanceType<typeof ImportDialog> | null>(null)

const canWrite = computed(() => projectStore.canWrite())
const searchResults = ref<{ name: string; address: string; location: [number, number]; distance?: number }[]>([])

// ---------- 图层混合树（文件夹 + 标点） ----------
interface LayerNode {
  id: string
  kind: 'folder' | 'feature'
  name: string
  feature_id?: string
  feature_type?: string
  featureCount?: number
  visible?: boolean
  hidden?: boolean
  parent_id?: string | null
  sort_order?: number
  children: LayerNode[]
}

const UNGROUPED_ID = '__ungrouped__'

const layerTree = computed<LayerNode[]>(() => {
  const folderMap = new Map<string, LayerNode>()
  const roots: LayerNode[] = []
  for (const f of folderStore.folders) {
    const node: LayerNode = {
      id: f.id, kind: 'folder', name: f.name, visible: f.visible,
      parent_id: f.parent_id, sort_order: f.sort_order, children: [],
    }
    folderMap.set(f.id, node)
    roots.push(node)
  }
  // 先建所有要素节点（按 id 索引），供父子归属
  const featureNodes = new Map<string, LayerNode>()
  const allFeatures = featureStore.features.filter(f => !f.deleted_at)
  for (const feat of allFeatures) {
    featureNodes.set(feat.id, {
      id: 'feat-' + feat.id, kind: 'feature', name: feat.name,
      feature_id: feat.id, feature_type: feat.feature_type,
      hidden: isHidden(feat), children: [],
    })
  }
  // 归类：绑定圆作为父标点的子节点；其余按 folder_id 挂文件夹 / 未分组
  // 病例名以「月.日」开头（如 9.5林思洋 / 8.21黄少芬），返回排序权重：
  // 月*100+日，日期越近越大；无日期前缀返回 -1（排最后）。同年场景足够。
  const dateRankOf = (name: string): number => {
    const m = /^(\d{1,2})[.．](\d{1,2})/.exec((name || '').trim())
    if (!m) return -1
    return Number(m[1]) * 100 + Number(m[2])
  }
  // 文件夹内标点按发病时间从近到远；无日期前缀的排在末尾
  const sortFeaturesByDate = (nodes: LayerNode[]) => {
    nodes.sort((a, b) => {
      const ra = dateRankOf(a.name)
      const rb = dateRankOf(b.name)
      return rb - ra // 降序：日期近（权重大）在前
    })
  }
  const attachToFolder = (fn: LayerNode, folderId: string | null | undefined) => {
    const holder = folderId ? folderMap.get(folderId) : null
    if (holder) {
      holder.children.push(fn)
      sortFeaturesByDate(holder.children)
    } else {
      let ungrouped = roots.find(r => r.id === '__ungrouped__')
      if (!ungrouped) {
        ungrouped = { id: '__ungrouped__', kind: 'folder', name: '未分组', children: [] }
        roots.unshift(ungrouped)
      }
      ungrouped.children.push(fn)
      sortFeaturesByDate(ungrouped.children)
    }
  }
  for (const feat of allFeatures) {
    const fn = featureNodes.get(feat.id)!
    // 圆绑定了标点 → 放到该标点节点的 children（点击标点展开才显示，不单独出现在文件夹下）
    const parentId = feat.feature_type === 'circle' ? boundParentId(feat) : undefined
    const parentNode = parentId ? featureNodes.get(parentId) : undefined
    if (parentNode && !feat.deleted_at) {
      parentNode.children.push(fn)
    } else {
      attachToFolder(fn, feat.folder_id)
    }
  }
  // 若标点节点没有任何子要素（普通要素或绑定圆的父点），保持原样；文件夹嵌套：parent_id 挂载
  const realRoots: LayerNode[] = []
  for (const r of roots) {
    if (r.id === '__ungrouped__') { realRoots.push(r); continue }
    if (r.parent_id && folderMap.has(r.parent_id)) folderMap.get(r.parent_id)!.children.push(r)
    else realRoots.push(r)
  }
  // 统计每个文件夹的直接要素数量（不含绑定圆的隐藏层级；它们计入其父标点）
  const count = (n: LayerNode): number => {
    let c = 0
    for (const ch of n.children) {
      // 有子要素的节点（父标点）本身算 1 个要素，子级是它的绑定圆不再重复统计
      if (ch.kind === 'feature') {
        c += 1
      } else {
        c += count(ch)
      }
    }
    n.featureCount = c
    return c
  }
  for (const r of realRoots) count(r)
  return realRoots
})

// ---------- 图层树展开控制 ----------
// Element Plus 树在 layerTree 整体重建（如编辑某要素保存后）会重置展开状态。
// 用受控 default-expanded-keys：凡是用户折叠过的文件夹会从 keys 里移除，重建后保持折叠；
// 新建的文件夹默认加进 keys（保持展开），直到用户折叠它。
const treeExpandedKeys = ref<string[]>([])
const collapsedFolderIds = ref<Set<string>>(new Set())

/** 收集当前树中所有文件夹节点 id */
function collectFolderKeys(): string[] {
  const keys: string[] = []
  const walk = (nodes: LayerNode[]) => {
    for (const n of nodes) {
      if (n.kind === 'folder') {
        keys.push(n.id)
        if (n.children.length) walk(n.children)
      }
    }
  }
  walk(layerTree.value)
  return keys
}

/** 同步受控展开 keys：移除已删除的文件夹、加入未折叠的新文件夹 */
watch(layerTree, (tree) => {
  const all = new Set(collectFolderKeys())
  const collapsed = collapsedFolderIds.value
  const next: string[] = []
  for (const k of treeExpandedKeys.value) if (all.has(k)) next.push(k) // 清理已删
  // 折叠中的不加入；未折叠且已存在的（含新出现）默认展开
  for (const id of all) {
    if (!collapsed.has(id) && !next.includes(id)) next.push(id)
  }
  const cur = treeExpandedKeys.value
  if (next.length !== cur.length || next.some((k, i) => k !== cur[i])) {
    treeExpandedKeys.value = next
  }
}, { immediate: true })

/** 用户折叠了文件夹 → 从展开 keys 移除并记录（数据重建后保持折叠） */
function onNodeCollapse(data: LayerNode) {
  if (data.kind !== 'folder') return
  const s = new Set(collapsedFolderIds.value)
  s.add(data.id)
  collapsedFolderIds.value = s
  treeExpandedKeys.value = treeExpandedKeys.value.filter(k => k !== data.id)
}

/** 用户展开了文件夹 → 移出折叠记录、加回展开 keys */
function onNodeExpand(data: LayerNode) {
  if (data.kind !== 'folder') return
  const s = new Set(collapsedFolderIds.value)
  s.delete(data.id)
  collapsedFolderIds.value = s
  if (!treeExpandedKeys.value.includes(data.id)) {
    treeExpandedKeys.value = [...treeExpandedKeys.value, data.id]
  }
}

function featureTypeIcon(t?: string): string {
  return ({ point: '📍', circle: '⭕', polyline: '〰️', polygon: '⬠' } as const)[t as 'point' | 'circle' | 'polyline' | 'polygon'] ?? '📍'
}

// ---------- 要素显示 / 隐藏 ----------
// 隐藏标记写在 feature.properties.hidden，随要素同步给其他协作者，刷新后依然保持
function isHidden(f: Feature | null | undefined): boolean {
  return isFeatureHidden(f)
}

/** 统一的显隐切换：先写后端（乐观锁），再同步地图显示 */
async function applyToggleHidden(f: Feature) {
  try {
    const { feature, hidden } = await featureStore.toggleHidden(f)
    mapService?.setFeatureVisibility(feature.id, !hidden)
    ElMessage.success(hidden ? `已隐藏「${f.name}」` : `已显示「${f.name}」`)
  } catch {
    ElMessage.warning('操作失败，数据可能已被他人修改')
  }
}

/** 图层列表里的眼睛按钮 */
function toggleFeatureHidden(node: LayerNode) {
  if (!node.feature_id) return
  const f = featureStore.byId.get(node.feature_id)
  if (f) applyToggleHidden(f)
}

/** 地图右键 / 图层树右键菜单里的隐藏项 */
function toggleHiddenFromMenu() {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (f) applyToggleHidden(f)
}

/** 右侧属性面板触发的显隐变更（面板已写库，这里只需同步地图） */
function onFeatureVisibilityChanged(f: Feature) {
  mapService?.setFeatureVisibility(f.id, !isFeatureHidden(f))
}

/**
 * 取几何体的代表坐标 [lng, lat]。
 * 各类型结构不同，之前统一用 coordinates[0] 导致标点取到的是经度数字
 * （Point.coordinates 本身就是 [lng,lat]，[0] 是 lng）→ 定位失败。
 * - Point:    coordinates = [lng, lat]
 * - Circle:   center = [lng, lat]
 * - Polyline: coordinates = [[lng,lat], ...]
 * - Polygon:  coordinates = [[[lng,lat], ...], ...]
 */
function geometryCenter(g: any): [number, number] | null {
  if (!g) return null
  if (g.type === 'Circle') return Array.isArray(g.center) ? g.center : null
  const c = g.coordinates
  if (!Array.isArray(c) || !c.length) return null
  if (g.type === 'Point') return Array.isArray(c[0]) ? (c[0] as [number, number]) : (c as [number, number])
  if (g.type === 'Polygon') {
    const ring = Array.isArray(c[0]) ? c[0] : null
    const first = ring && ring[0]
    return Array.isArray(first) ? (first as [number, number]) : null
  }
  // LineString / 兜底
  return Array.isArray(c[0]) ? (c[0] as [number, number]) : null
}

function onTreeClick(data: LayerNode) {
  if (data.kind === 'feature' && data.feature_id) {
    featureStore.select(data.feature_id)
    uiStore.openDetail()
    const f = featureStore.byId.get(data.feature_id)
    if (f) {
      const center = geometryCenter(f.geometry_display as any)
        ?? geometryCenter((f as any).geometry_original)
      if (center && Number.isFinite(center[0]) && Number.isFinite(center[1])) {
        mapService?.locate(center[0], center[1], 17)
      }
    }
  }
}

function allowTreeDrag(node: any): boolean {
  // 只允许拖动标点与真文件夹；"未分组"容器不可拖动
  const d = node?.data
  if (!d) return true
  if (d.id === UNGROUPED_ID) return false
  return true
}

/** 左侧树标点节点右键：查看 / 编辑 / 删除（复用地图右键菜单） */
function onFeatureNodeMenu(e: MouseEvent, data: LayerNode) {
  if (!data.feature_id) return
  const f = featureStore.byId.get(data.feature_id)
  if (!f) return
  openContextMenu(f, e.clientX, e.clientY)
}

let mapService: MapService | null = null
/** 重建地图中（防抖，避免 context lost 连续触发多次重建） */
let mapRebuilding = false

/** 创建地图实例并绑定事件（可重复调用；WebGL 崩溃后用它重建，无需刷新整页） */
async function initMap(): Promise<void> {
  if (!mapEl.value || mapRebuilding) return
  mapRebuilding = true
  mapService?.destroy()
  mapService = null
  try {
    const svc = createMapService({
      container: mapEl.value,
      amapKey: getAmapKey(),
      securityCode: getAmapSecurityCode(),
      // 高德 WebGL 上下文丢失（显存不足/GPU 崩溃）→ 自动重建地图，避免一直空白
      onContextLost: () => {
        if (!mapRebuilding) {
          ElMessage.warning('地图渲染异常，正在自动恢复…')
          setTimeout(() => initMap(), 600)
        }
      },
    })
    mapService = svc
    await svc.init()
    svc.setFeatures(featureStore.features)
    svc.onFeatureClick((id) => {
      featureStore.select(id)
      uiStore.openDetail()
    })
    svc.onFeatureContextMenu((id, xy) => {
      const f = featureStore.byId.get(id)
      if (f) openContextMenu(f, xy[0], xy[1])
    })
    svc.onFeatureDragEnd((id, geometry) => handleDragEnd(id, geometry))
  } catch {
    ElMessage.error('地图加载失败，请检查高德 Key 是否配置正确')
  } finally {
    mapRebuilding = false
  }
}

// ---------- 生命周期 ----------
onMounted(async () => {
  if (!route.params.id) return
  try {
    await projectStore.openProject(projectId.value)
  } catch (e: any) {
    ElMessage.error('打开项目失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
    goBack()
    return
  }
  // 先渲染页面结构（mapEl 就位），再初始化地图
  loaded.value = true
  await Promise.all([
    folderStore.fetchAll(projectId.value),
    featureStore.fetchAll(projectId.value),
    loadAudit(),
  ]).catch(() => undefined)

  await initMap()

  collaboration.connect(projectId.value, onWsEvent)
  collaboration.refreshOnline(projectId.value)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  collaboration.disconnect()
  mapService?.destroy()
  mapService = null
})

// ---------- 数据 ----------
async function reloadData() {
  await Promise.all([
    folderStore.fetchAll(projectId.value),
    featureStore.fetchAll(projectId.value),
    loadAudit(),
  ])
  mapService?.setFeatures(featureStore.features)
}

async function loadAudit() {
  const data = await projectApi.audit(projectId.value)
  auditLogs.value = data.items
}

// ---------- 工具 ----------
function toolBtn(t: string) {
  return uiStore.tool === t ? 'primary' : 'default'
}

function setTool(t: MapToolType) {
  uiStore.setTool(t)
  mapService?.setTool(t, onDrawDone)
}

function onDrawDone(geometry: unknown, tool: MapToolType) {
  const typeMap: Record<string, string> = { point: 'point', circle: 'circle', polyline: 'polyline', polygon: 'polygon' }
  const ftype = typeMap[tool]
  if (ftype && featureDialogRef.value) {
    featureDialogRef.value.openForCreate(ftype, geometry as Record<string, unknown>)
  }
  // 测距 / 测面积：弹出结果 toast
  const r = geometry as { distance?: number; area?: number } | null
  if (tool === 'measure' && r?.distance) {
    ElMessage.info(`测距结果：${formatDistance(r.distance)}`)
  }
  if (tool === 'area' && r?.area) {
    ElMessage.info(`面积：${formatArea(r.area)}`)
  }
}

function formatDistance(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(2)} km`
  return `${Math.round(m)} m`
}

function formatArea(sqm: number): string {
  if (sqm >= 1e6) return `${(sqm / 1e6).toFixed(2)} km²`
  if (sqm >= 1e4) return `${(sqm / 1e4).toFixed(2)} 万m²`
  return `${Math.round(sqm)} m²`
}

// ---------- 画对象回调（创建后同步地图与 store） ----------
async function onFeatureCreated(f: Feature) {
  featureStore.upsert(f)
  mapService?.upsertFeature(f)
}

// 右侧面板"与其他标点的距离"点击跳转
function onLocateFromPanel(lng: number, lat: number) {
  mapService?.locate(lng, lat, 15)
}

// ---------- 搜索 ----------
async function doSearch() {
  const kw = uiStore.searchKeyword.trim()
  if (!kw || !mapService) return
  searchResults.value = await mapService.searchAndLocate(kw)
}

function locateResult(r: { name: string; address: string; location: [number, number]; distance?: number }) {
  // 飞至目标点并在地图上显示一个临时标记（点击标记可关闭）
  mapService?.locateSearch(r.location[0], r.location[1], r.name)
  searchResults.value = []
  uiStore.searchKeyword = ''
}

// ---------- WebSocket 事件 ----------
function onWsEvent(event: string, data: Record<string, unknown>) {
  switch (event) {
    case 'feature.created': {
      const f = data.feature as Feature
      featureStore.upsert(f)
      mapService?.upsertFeature(f)
      break
    }
    case 'feature.updated': {
      const f = data.feature as Feature
      featureStore.upsert(f)
      mapService?.upsertFeature(f)
      break
    }
    case 'feature.deleted': {
      const id = data.id as string
      featureStore.removeLocal(id)
      mapService?.removeFeature(id)
      break
    }
    case 'folder.deleted': {
      reloadData()
      break
    }
    default:
      break
  }
}

// ---------- 右键操作 ----------
function viewFeature() {
  const f = contextMenu.value.feature
  if (f) {
    featureStore.select(f.id)
    uiStore.openDetail()
  }
  contextMenu.value.visible = false
}

async function startEditFeature() {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (!f || !mapService) return
  try {
    await featureApi.lock(f.id)
    mapService.startEdit(f.id)
    // 进入编辑后提示用户如何保存（标点：直接拖动；图形：拖控制点）
    ElMessage.info(
      f.feature_type === 'point'
        ? '现在可以拖动标点调整位置，完成后点击地图空白处保存'
        : '拖动控制点编辑，完成后点击地图空白处保存'
    )
  } catch {
    /* 锁被占用时由拦截器提示 */
  }
}

/** 打开属性编辑对话框（名称 / 分组 / 颜色 / 备注等） */
function editFeatureProps(id?: string) {
  const targetId = id || contextMenu.value.feature?.id
  contextMenu.value.visible = false
  if (!targetId) return
  const f = featureStore.byId.get(targetId)
  if (f) featureDialogRef.value?.openForEdit(f)
}

/** 要素属性/绑定关系变更后同步到地图（来自属性面板的 @bound） */
function onFeatureChanged(f: Feature) {
  mapService?.upsertFeature(f)
}

/** 属性面板级联删除的绑定圆：同步移除地图 overlay */
function onChildRemoved(id: string) {
  mapService?.removeFeature(id)
}

/** 属性面板「与其他标点的距离」点选某个标点 → 切换当前查看对象到该标点 */
function onViewFeatureFromPanel(id: string) {
  const target = featureStore.byId.get(id)
  if (!target) return
  featureStore.select(id)
  // 保持右侧面板打开，展示该标点详情
  uiStore.openDetail()
  // 确保地图不处于绘图/编辑状态，方便直接查看
  mapService?.stopDraw?.()
  mapService?.stopEdit?.()
  mapService?.setTool?.('select')
  const center = geometryCenter(target.geometry_display as any)
    ?? geometryCenter((target as any).geometry_original)
  if (center && Number.isFinite(center[0]) && Number.isFinite(center[1])) {
    mapService?.locate(center[0], center[1], 17)
  }
}

// 右侧面板"编辑"按钮 → 进入地图编辑模式
async function startEditFromPanel(id: string) {
  if (!mapService) return
  const f = featureStore.byId.get(id)
  if (!f) return
  if (collaboration.locks[id] && collaboration.locks[id].user_id !== auth.user?.id) {
    ElMessage.warning(`${collaboration.locks[id].username} 正在编辑该对象`)
    return
  }
  try {
    await featureApi.lock(f.id)
    mapService.startEdit(id)
    uiStore.closeDetail()
    ElMessage.info(
      f.feature_type === 'point'
        ? '现在可以拖动标点调整位置，完成后点击地图空白处保存'
        : '拖动控制点编辑，完成后点击地图空白处保存'
    )
  } catch {
    /* 锁冲突由拦截器提示 */
  }
}

async function deleteFeature() {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (!f) return
  // 删除标点 → 绑定圆一并删除
  const children = f.feature_type === 'point' ? boundCirclesOf(f.id) : []
  const extra = children.length ? `\n另有 ${children.length} 个绑定该标点的圆将一并删除。` : ''
  try {
    await ElMessageBox.confirm(`删除「${f.name}」？将移入回收站，可在回收站恢复。${extra}`, '确认删除', { type: 'warning' })
    pushUndo(f)
    await featureApi.remove(f.id)
    featureStore.removeLocal(f.id)
    mapService?.removeFeature(f.id)
    for (const child of children) {
      await featureApi.remove(child.id)
      featureStore.removeLocal(child.id)
      mapService?.removeFeature(child.id)
    }
  } catch {
    /* 取消 */
  }
}

async function genCircle(radius: number) {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (!f || f.feature_type !== 'point') return
  const coord = (f.geometry_display as { coordinates?: number[] })?.coordinates
  if (!coord) return
  const created = await featureApi.create(projectId.value, {
    name: `${f.name} · ${radius}m 范围`,
    feature_type: 'circle',
    geometry: { type: 'Circle', center: [coord[0], coord[1]], radius },
    folder_id: f.folder_id,
    // 由标点生成的圆：默认绑定该标点（随标点移动/隐藏/删除联动）
    properties: { parent_point_id: f.id },
  })
  onFeatureCreated(created)
  mapService?.locate(coord[0], coord[1], 15)
  ElMessage.success('已生成并绑定到该标点，可在右侧面板解除绑定')
}

function moveToFolder() {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (f) moveDialogRef.value?.open(f)
}

function nearbySearch() {
  const f = contextMenu.value.feature
  contextMenu.value.visible = false
  if (f) nearbyDialogRef.value?.open(f)
}

// ---------- 拖拽结束同步 ----------
async function handleDragEnd(id: string, geometry: unknown) {
  const f = featureStore.byId.get(id)
  if (!f) return
  pushUndo(f)
  try {
    const updated = await featureApi.update(id, { version: f.version, geometry: geometry as Record<string, unknown> })
    releaseEditLock(id)
    featureStore.upsert(updated)
    mapService?.upsertFeature(updated)
    // 移动标点 → 绑定的圆圆心跟着走
    if (updated.feature_type === 'point') {
      await syncBoundCircleCenters(updated, geometry as Record<string, unknown>)
    }
    // 手动把绑定圆的圆心拖走 → 自动解绑
    await detachBoundCircleIfMoved(updated, geometry as Record<string, unknown>)
  } catch (e: any) {
    // 409 = 服务端版本已推进（如并行编辑/WS 同步拉开了 version）。
    // 拉取最新版本后重试一次，避免"其他用户修改"误报 + 保存失败。
    if (e?.response?.status === 409) {
      try {
        const latest = await featureApi.get(id)
        if (latest) {
          featureStore.upsert(latest)
          const updated = await featureApi.update(id, {
            version: latest.version,
            geometry: geometry as Record<string, unknown>,
          })
          releaseEditLock(id)
          featureStore.upsert(updated)
          mapService?.upsertFeature(updated)
          // 重试成功同样触发绑定联动
          if (updated.feature_type === 'point') {
            await syncBoundCircleCenters(updated, geometry as Record<string, unknown>)
          }
          await detachBoundCircleIfMoved(updated, geometry as Record<string, unknown>)
          return
        }
      } catch {
        /* 重试也失败则回滚本地显示 */
      }
    }
    mapService?.upsertFeature(f)
  }
}

/** 编辑保存完成后释放编辑锁（锁不释放会导致他人无法编辑） */
async function releaseEditLock(id: string) {
  try {
    await featureApi.unlock(id)
  } catch {
    /* 锁已过期/不存在则忽略 */
  }
}

// ---------- 圆绑定标点：级联 ----------
// 绑定关系写在圆 properties.parent_point_id；UI 见右侧面板。
// 联动规则：
//  - 移动标点 → 已绑定圆的 DB 圆心一并更新（随父走）
//  - 隐藏/显示标点 → 绑定圆可见性跟随（见 AmapMapService.syncBoundChildren）
//  - 删除标点 → 绑定圆一并移入回收站；恢复 / 永久删除同理级联

/** 当前绑定到某标点的圆（未删除） */
function boundCirclesOf(parentId: string): Feature[] {
  return featureStore.features.filter(
    c => !c.deleted_at && c.feature_type === 'circle' && boundParentId(c) === parentId
  )
}

/** 把绑定圆的数据库圆心同步到标点新位置（半径、其余字段不动） */
async function syncBoundCircleCenters(point: Feature, geometry: Record<string, unknown>) {
  const g = geometry as { type?: string; coordinates?: number[] }
  if (g.type !== 'Point' || !Array.isArray(g.coordinates) || g.coordinates.length < 2) return
  const center = [g.coordinates[0], g.coordinates[1]]
  for (const child of boundCirclesOf(point.id)) {
    const cg = (child.geometry_display || {}) as any
    if (cg.type !== 'Circle' || !cg.radius) continue
    try {
      const updated = await featureApi.update(child.id, {
        version: child.version,
        geometry: { type: 'Circle', center, radius: cg.radius },
      })
      featureStore.upsert(updated)
      mapService?.upsertFeature(updated)
    } catch {
      /* 个别同步失败不影响主流程 */
    }
  }
}

/** 若用户把"绑定圆"的圆心拖离了父标点，自动解除绑定（圆心以手动位置为准） */
async function detachBoundCircleIfMoved(f: Feature, geometry: Record<string, unknown>) {
  if (f.feature_type !== 'circle') return
  const parentId = boundParentId(f)
  if (!parentId) return
  const parent = featureStore.byId.get(parentId)
  const g = geometry as any
  if (!parent || g.type !== 'Circle') return
  const pg = parent.geometry_display as any
  if (!pg || pg.type !== 'Point') return
  const [plng, plat] = pg.coordinates
  const moved = Math.abs(g.center[0] - plng) > 1e-9 || Math.abs(g.center[1] - plat) > 1e-9
  if (!moved) return
  // 圆心已不等于父标点 → 解绑并保持手动位置
  const props: Record<string, unknown> = { ...((f.properties || {}) as Record<string, unknown>) }
  delete props.parent_point_id
  try {
    const updated = await featureApi.update(f.id, {
      version: f.version,
      properties: props,
      geometry,
    })
    featureStore.upsert(updated)
    mapService?.upsertFeature(updated)
    ElMessage.info('圆已脱离标点绑定（圆心位置已手动调整）')
  } catch { /* ignore */ }
}

// ---------- 撤销 / 重做 ----------
// Pinia 状态是响应式 Proxy，structuredClone 会抛 DataCloneError；先 toRaw 再克隆
function cloneFeatureSafe(f: Feature): Feature {
  try {
    return structuredClone(toRaw(f))
  } catch {
    return JSON.parse(JSON.stringify(f)) as Feature
  }
}

function pushUndo(f: Feature) {
  if (undoStack.value.length > 50) undoStack.value.shift()
  undoStack.value.push(cloneFeatureSafe(f))
  redoStack.value = []
}

async function undo() {
  const snap = undoStack.value.pop()
  if (!snap) return
  const cur = featureStore.byId.get(snap.id)
  if (!cur) return
  try {
    const updated = await featureApi.update(snap.id, {
      version: cur.version,
      name: snap.name,
      geometry: snap.geometry_display as Record<string, unknown>,
      folder_id: snap.folder_id,
      category_id: snap.category_id,
      properties: snap.properties as Record<string, unknown>,
      style: snap.style as Record<string, unknown>,
    })
    featureStore.upsert(updated)
    mapService?.upsertFeature(updated)
    redoStack.value.push(cloneFeatureSafe(cur))
  } catch {
    ElMessage.warning('撤销失败，数据可能已被他人修改')
  }
}

async function redoAction() {
  const snap = redoStack.value.pop()
  if (!snap) return
  const cur = featureStore.byId.get(snap.id)
  if (!cur) return
  try {
    const updated = await featureApi.update(snap.id, {
      version: cur.version,
      name: snap.name,
      geometry: snap.geometry_display as Record<string, unknown>,
      folder_id: snap.folder_id,
      category_id: snap.category_id,
      properties: snap.properties as Record<string, unknown>,
      style: snap.style as Record<string, unknown>,
    })
    featureStore.upsert(updated)
    mapService?.upsertFeature(updated)
    undoStack.value.push(cloneFeatureSafe(cur))
  } catch {
    ElMessage.warning('重做失败')
  }
}

function deleteSelected() {
  const f = featureStore.selected
  if (!f) return
  contextMenu.value.feature = f
  deleteFeature()
}

// ---------- 其它 ----------
const baseLayer = ref<'normal' | 'satellite'>('normal')

function toggleBaseLayer() {
  const next = baseLayer.value === 'normal' ? 'satellite' : 'normal'
  try {
    mapService?.setBaseLayer(next)
    baseLayer.value = next
    ElMessage.success(next === 'satellite' ? '已切换为卫星地图' : '已切换为平面地图')
  } catch (e: any) {
    console.error('[toggleBaseLayer]', e)
    ElMessage.error('切换底图失败：' + (e?.message || e))
  }
}

function resetView() {
  const c = projectStore.current?.default_center
  if (c) mapService?.locate(c[0], c[1], projectStore.current?.default_zoom ?? 13)
  else mapService?.locate(113.264, 23.199, 13)
}

function locateMe() {
  if (!mapService || !navigator.geolocation) {
    ElMessage.warning('无法定位')
    return
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => mapService?.locate(pos.coords.longitude, pos.coords.latitude, 16),
    () => ElMessage.warning('定位失败'),
  )
}

async function onExportCommand(cmd: string) {
  if (!projectId.value) return
  const exportingFlag = { backup: '完整备份', geojson: 'GeoJSON', csv: 'CSV' }[cmd as 'backup' | 'geojson' | 'csv'] || ''
  exporting.value = true
  try {
    const filename = await importApi.downloadExport(projectId.value, {
      format: cmd,
      crs: 'original',
    })
    ElMessage.success(`已导出：${filename || exportingFlag}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

function goBack() {
  router.push('/')
}

function onTopCommand(cmd: string) {
  if (cmd === 'refresh') reloadData()
  else if (cmd === 'logout') {
    auth.logout()
    router.replace('/login')
  }
}

// ---------- 文件夹 ----------
function allowDrop() {
  return true
}

async function onFolderDrop(dragging: any, target: any, type: string) {
  // type: 'before' | 'after' | 'inner' —— 拖到目标上为子级
  if (!target) return
  // 标点拖入文件夹 → 移动 folder_id
  if (dragging?.data?.kind === 'feature') {
    const fid = dragging.data.feature_id
    const f = featureStore.byId.get(fid)
    if (!f) return
    // inner → 放入目标文件夹；before/after → 归入目标所在文件夹（若目标是标点）或目标文件夹
    let folderId: string | null = null
    if (target.data?.kind === 'feature') {
      const tf = featureStore.byId.get(target.data.feature_id)
      folderId = tf?.folder_id ?? null
    } else {
      folderId = target.data?.id === UNGROUPED_ID ? null : (target.data?.id ?? null)
    }
    if (folderId === f.folder_id) return
    try {
      await featureStore.move(fid, folderId, f.version)
      ElMessage.success(folderId ? '已移入文件夹' : '已移入未分组')
    } catch {
      ElMessage.warning('移动失败，可能已被他人修改')
    }
    return
  }
  // 文件夹拖到目标文件夹 → 移动为其子级
  if (type === 'inner' && target) {
    try {
      await folderStore.moveTo(dragging.id, target.id)
      ElMessage.success('已移动文件夹')
    } catch {
      /* noop */
    }
  }
}

function onFolderCmd(cmd: string, data: any) {
  if (cmd === 'rename') folderDialogRef.value?.rename(data)
  else if (cmd === 'new-sub') folderDialogRef.value?.open(projectId.value, data.id)
  else if (cmd === 'toggle') folderStore.toggleVisible(data.id)
  else if (cmd === 'delete') {
    ElMessageBox.confirm(`删除文件夹「${data.name}」？其下对象将变为未分组。`, '提示', { type: 'warning' })
      .then(() => folderStore.remove(data.id))
      .catch(() => undefined)
  }
}

function addFolder(parentId: string | null) {
  folderDialogRef.value?.open(projectId.value, parentId)
}

async function openTrash() {
  await featureStore.trashAll(projectId.value)
  trashVisible.value = true
}

async function restoreTrash(row: Feature) {
  const updated = await featureStore.restore(row.id)
  mapService?.upsertFeature(updated)
  // 恢复标点 → 一并恢复绑定它的圆（它们随删除一起进了回收站）
  if (row.feature_type === 'point') {
    for (const t of [...featureStore.trash]) {
      if (!t.deleted_at && t.feature_type === 'circle' && boundParentId(t) === row.id) {
        try {
          const restored = await featureStore.restore(t.id)
          mapService?.upsertFeature(restored)
        } catch { /* ignore */ }
      }
    }
  }
  ElMessage.success('已恢复')
}

async function purgeTrash(row: Feature) {
  // 永久删除标点 → 绑定圆也永久删除
  const children = row.feature_type === 'point'
    ? featureStore.trash.filter(t => t.feature_type === 'circle' && boundParentId(t) === row.id)
    : []
  const extra = children.length ? `\n另有 ${children.length} 个绑定该标点的圆将被一并永久删除。` : ''
  try {
    await ElMessageBox.confirm(`永久删除「${row.name}」？不可恢复。${extra}`, '警告', { type: 'error' })
    await featureApi.permanentDelete(row.id)
    featureStore.trash = featureStore.trash.filter(t => t.id !== row.id)
    for (const child of children) {
      await featureApi.permanentDelete(child.id)
      featureStore.trash = featureStore.trash.filter(t => t.id !== child.id)
    }
  } catch {
    /* 取消 */
  }
}

// ---------- 快捷键 ----------
function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (e.ctrlKey && k === 'z') {
    e.preventDefault()
    if (e.shiftKey) redoAction()
    else undo()
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    deleteSelected()
  } else if (k === 'v') setTool('select')
  else if (k === 'm') setTool('point')
  else if (k === 'c') setTool('circle')
  else if (k === 'l') setTool('polyline')
  else if (k === 'p') setTool('polygon')
  else if (k === 'r') setTool('measure')
  else if (k === 'escape') {
    setTool('select')
    contextMenu.value.visible = false
  }
}

// ---------- 小工具 ----------
function getAmapKey(): string {
  const meta = document.querySelector('meta[name="amap-key"]')
  return meta ? meta.getAttribute('content') || '' : ''
}

function getAmapSecurityCode(): string {
  const meta = document.querySelector('meta[name="amap-security-code"]')
  return meta ? meta.getAttribute('content') || '' : ''
}

function tagType(role: string) {
  return ({ owner: 'danger', admin: 'warning', editor: 'primary', viewer: 'info' } as const)[role as 'owner' | 'admin' | 'editor' | 'viewer'] ?? 'info'
}

function roleTextOf(role: string) {
  return ({ owner: '所有者', admin: '管理员', editor: '编辑者', viewer: '只读' } as const)[role as 'owner' | 'admin' | 'editor' | 'viewer'] ?? role
}

function actionText(action: string) {
  const map: Record<string, string> = {
    create: '创建', update: '修改', delete: '删除', restore: '恢复',
    move: '移动', 'delete.permanent': '永久删除', import: '导入', export: '导出',
    'member.add': '添加成员', 'member.remove': '移除成员', 'member.update': '修改成员',
  }
  return map[action] ?? action
}
</script>

<style scoped>
.map-page { height: 100%; display: flex; flex-direction: column; position: relative; overflow: hidden; }
.topbar { display: flex; justify-content: space-between; align-items: center; height: 48px; padding: 0 12px; background: #fff; border-bottom: 1px solid #e5e7eb; z-index: 20; flex-shrink: 0; }
.body { flex: 1; display: flex; overflow: hidden; position: relative; }
.sidebar { width: 260px; border-right: 1px solid #e5e7eb; background: #fff; display: flex; flex-direction: column; }
.map-wrap { flex: 1; position: relative; }
.map-container { position: absolute; inset: 0; }
.toolbar { height: 48px; display: flex; align-items: center; gap: 2px; padding: 0 8px; background: #fff; border-top: 1px solid #e5e7eb; z-index: 20; flex-shrink: 0; }

.folder-tree { flex: 1; padding: 4px; overflow: auto; }
.folder-node, .feature-node { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.folder-node .el-icon { margin-left: auto; }
.more { cursor: pointer; opacity: 0.5; }
.more:hover { opacity: 1; }
.count { font-size: 12px; color: #bbb; margin-left: auto; order: 2; }
.count + .el-dropdown { order: 3; }
.f-ico { color: #f7ba2a; font-size: 14px; }
.feature-node { padding: 1px 0; }
.f-type { font-size: 13px; }
.f-name { font-size: 13px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.f-name.is-selected { color: #1677ff; font-weight: 600; }
.f-name.is-hidden { color: #bbb; text-decoration: line-through; }
.f-eye { margin-left: auto; margin-right: 4px; font-size: 12px; cursor: pointer; opacity: 0; flex-shrink: 0; }
.f-eye.always { opacity: 1; }
.feature-node:hover .f-eye { opacity: 1; }
.feature-node { position: relative; }
.feature-node:hover { background: #f5f7fa; }
.folder-tree :deep(.el-tree-node__content:hover) { background: #f5f7fa; }
.free-tree-drag { cursor: grab; }
.tree-toolbar { display: flex; align-items: center; padding: 6px; border-bottom: 1px solid #f0f0f0; }
.tree-footer { padding: 4px 8px; border-top: 1px solid #f0f0f0; }
.side-tabs { height: 100%; display: flex; flex-direction: column; }
.side-tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; }
/* 图层 tab-pane 占满高度并 flex 布局，folder-tree 才能正确内部滚动（病例多时不截断） */
.side-tabs :deep(.el-tabs__content .tab-pane-folders) { height: 100%; overflow: hidden; display: flex; flex-direction: column; }

.search-input { width: 340px; }
.search-results { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); width: 440px; background: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.14); z-index: 30; max-height: 300px; overflow: auto; }
.sr-item { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0; }
.sr-item:hover { background: #f5f7fa; }
.sr-dist { float: right; font-size: 12px; color: #999; background: #f5f7fa; border-radius: 8px; padding: 0 6px; }
.sr-dist.in-view { color: #1677ff; background: #e8f4ff; }
.sr-name { font-weight: 500; }
.sr-addr { color: #999; font-size: 12px; }

.online-panel { position: absolute; right: 12px; top: 12px; background: #fff; border-radius: 8px; padding: 8px 12px; box-shadow: 0 2px 8px rgba(0,0,0,.12); min-width: 130px; z-index: 15; }
.op-title { font-size: 12px; color: #999; margin-bottom: 4px; }
.op-member { font-size: 13px; line-height: 1.9; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #67c23a; margin-right: 6px; }
.conn-badge { font-size: 12px; color: #67c23a; margin-right: 14px; }
.user-chip { cursor: pointer; font-size: 14px; }

.activity-toast { position: absolute; bottom: 64px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,.72); color: #fff; padding: 6px 16px; border-radius: 16px; font-size: 13px; z-index: 35; }

.context-menu { position: fixed; background: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16); padding: 4px 0; z-index: 3000; min-width: 160px; max-height: calc(100vh - 12px); overflow-y: auto; }
.cm-title { padding: 8px 14px; font-weight: 600; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.cm-item { padding: 8px 14px; font-size: 13px; cursor: pointer; color: #333; }
.cm-item:hover { background: #f5f7fa; }
.cm-item.danger { color: #f56c6c; }
.cm-sp { border-top: 1px solid #f0f0f0; margin-top: 4px; padding-top: 8px; }

.right-panel { width: 340px; border-left: 1px solid #e5e7eb; background: #fff; overflow: auto; box-shadow: -4px 0 12px rgba(0,0,0,.06); z-index: 18; flex-shrink: 0; }
.slide-enter-active, .slide-leave-active { transition: width .2s ease; }

.members-panel, .audit-panel { padding: 8px; overflow: auto; height: 100%; }
.member-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 4px; font-size: 13px; }
.audit-item { padding: 6px 4px; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
.a-head { display: flex; gap: 6px; }
.a-action { color: #1677ff; }
.a-time { color: #bbb; font-size: 12px; }

.back { cursor: pointer; margin-right: 8px; font-size: 18px; color: #666; }
.proj-name { font-weight: 600; margin-right: 8px; }
.role-tag { font-size: 12px; color: #fff; padding: 2px 8px; border-radius: 10px; }
.r-owner { background: #f56c6c; }
.r-admin { background: #e6a23c; }
.r-editor { background: #409eff; }
.r-viewer { background: #909399; }

.fade-enter-active, .fade-leave-active { transition: opacity .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>