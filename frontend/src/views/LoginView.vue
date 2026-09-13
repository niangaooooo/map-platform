<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="title">协作地图标绘平台</h2>
      <el-form @submit.prevent="onSubmit">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" size="large" autocomplete="username" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" size="large" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" native-type="submit">登 录</el-button>
      </el-form>
      <div class="foot">
        <router-link to="/register">注册账号</router-link>
      </div>
      <div class="privacy-note">
        <div class="privacy-title">隐私说明 · 本站不收集隐私信息</div>
        <p>本站为个人自用协作工具，不收集、不上传任何个人隐私信息，未接入第三方统计或广告追踪。账号仅用于区分协作者身份，地图数据仅项目成员可见。</p>
        <a class="privacy-link" href="privacy.html" target="_blank" rel="noopener">查看完整隐私说明</a>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function onSubmit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.replace((route.query.redirect as string) || '/')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef4ff 0%, #f7f9ff 100%);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
}
.title {
  text-align: center;
}
.submit {
  width: 100%;
}
.tip {
  margin-top: 12px;
  text-align: center;
  font-size: 13px;
}
.privacy-note {
  margin-top: 16px;
  padding: 10px 12px;
  border: 1px solid #e2e8f5;
  border-radius: 8px;
  background: #f6f9ff;
}
.privacy-title {
  font-size: 13px;
  font-weight: 600;
  color: #2f5aa8;
  margin-bottom: 6px;
}
.privacy-note p {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #5b6b85;
}
.privacy-note strong {
  color: #3d6bb5;
  font-weight: 600;
}
.privacy-link {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: #4a7fd4;
  text-decoration: none;
}
.privacy-link:hover {
  text-decoration: underline;
}
</style>