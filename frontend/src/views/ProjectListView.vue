<template>
  <div class="projects-page">
    <header class="topbar">
      <div class="brand"><span class="logo">🗺️</span> 协作地图标绘</div>
      <div class="actions">
        <el-dropdown @command="onCommand">
          <span class="user-chip">{{ auth.user?.display_name || auth.user?.username }}</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <main class="content">
      <div class="head">
        <h2>全部项目</h2>
        <el-button type="primary" @click="dialogVisible = true">+ 新建项目</el-button>
      </div>

      <el-alert
        v-if="!projectStore.loadingProjects && projectStore.projects.length > 1"
        type="info"
        :closable="false"
        class="collab-tip"
        title="协作模式：所有登录用户都能看到全部项目并标注，仅创建者可删除自己的项目"
      />

      <div v-loading="projectStore.loadingProjects" class="grid">
        <el-card
          v-for="p in projectStore.projects"
          :key="p.id"
          class="project-card"
          shadow="hover"
          @click="open(p)"
        >
          <div class="card-head">
            <h3>{{ p.name }}</h3>
            <el-tag v-if="p.role === 'owner'" size="small" type="danger" effect="light">我创建的</el-tag>
            <el-tag v-else-if="p.role === 'admin'" size="small" type="warning" effect="light">管理员</el-tag>
          </div>
          <p class="desc">{{ p.description || '暂无描述' }}</p>
          <div class="meta">
            <span v-if="p.owner_name">👤 {{ p.owner_name }} · </span>最近修改：{{ dayjs(p.updated_at).fromNow() }}
          </div>
          <div class="card-actions">
            <el-button
              v-if="isTestEnv && p.role === 'owner'"
              type="success"
              size="small"
              plain
              :loading="syncingId === p.id"
              @click.stop="confirmSync(p)"
            >⬆ 同步到正式</el-button>
            <el-button type="primary" size="small" class="enter">进入</el-button>
            <el-button
              v-if="p.role === 'owner'"
              type="danger"
              size="small"
              plain
              :loading="deletingId === p.id"
              @click.stop="confirmDelete(p)"
            >删除</el-button>
          </div>
        </el-card>
        <el-empty
          v-if="!projectStore.projects.length && !projectStore.loadingProjects"
          description="还没有项目，点击右上角新建"
        />
      </div>
    </main>

    <el-dialog v-model="dialogVisible" title="新建项目" width="460px">
      <el-form label-width="70px">
        <el-form-item label="项目名">
          <el-input v-model="newName" placeholder="如：2026登革热疫情" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="newDesc" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import type { Project } from '@/types'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const auth = useAuthStore()
const projectStore = useProjectStore()
const router = useRouter()
const dialogVisible = ref(false)
const newName = ref('')
const newDesc = ref('')
const creating = ref(false)
const deletingId = ref('')
const syncingId = ref('')

/** 当前是否为测试板块（base=/map-test/）；正式板块(/map/)不显示同步入口 */
const isTestEnv = import.meta.env.BASE_URL.startsWith('/map-test')

onMounted(() => {
  projectStore.fetchProjects()
})

function open(p: Project) {
  router.push(`/projects/${p.id}`)
}

/** 一键同步：把测试板块项目推送到正式板块 */
async function confirmSync(p: Project) {
  try {
    await ElMessageBox.confirm(
      `将测试项目「${p.name}」同步到正式板块？\n正式板块会新建同名项目并复制其全部文件夹与标绘数据，不覆盖正式端已有内容。\n注意：你需要在正式板块也有同名账号（已注册即可）。`,
      '同步到正式板块',
      {
        confirmButtonText: '开始同步',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
  } catch {
    return // 用户取消
  }
  syncingId.value = p.id
  try {
    const r = await projectStore.syncToProd(p.id)
    ElMessage.success(`已同步到正式板块：「${r.name}」（复制要素 ${r.created} 条）`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步失败，请确认正式板块服务正常且你有同名账号')
  } finally {
    syncingId.value = ''
  }
}

async function confirmDelete(p: Project) {
  try {
    await ElMessageBox.confirm(
      `确定要彻底删除项目「${p.name}」吗？项目本身及其全部标绘、文件夹、分类和成员都会被永久删除，此操作不可恢复。`,
      '删除项目',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      }
    )
  } catch {
    return // 用户取消
  }
  deletingId.value = p.id
  try {
    await projectStore.deleteProject(p.id)
    ElMessage.success('项目已删除')
  } catch {
    ElMessage.error('删除失败，请确认你有项目所有者权限')
  } finally {
    deletingId.value = ''
  }
}

async function create() {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  creating.value = true
  try {
    const p = await projectStore.createProject(newName.value.trim(), newDesc.value.trim())
    dialogVisible.value = false
    router.push(`/projects/${p.id}`)
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.projects-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.brand {
  font-weight: 600;
  font-size: 16px;
}
.logo {
  margin-right: 4px;
}
.user-chip {
  cursor: pointer;
  color: #333;
}
.content {
  padding: 24px;
  flex: 1;
  overflow: auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.head h2 {
  margin: 0;
}
.collab-tip {
  margin-bottom: 16px;
}
.grid {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.project-card {
  width: 320px;
  cursor: pointer;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.card-head h3 {
  margin: 0;
  font-size: 16px;
}
.desc {
  color: #999;
  font-size: 13px;
  min-height: 40px;
  margin: 0;
}
.meta {
  color: #bbb;
  font-size: 12px;
  margin: 8px 0;
}
.enter {
  margin-top: 4px;
}
.card-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
}
.card-actions .enter {
  margin-top: 0;
}
</style>