<template>
  <div class="register-page">
    <el-card class="register-card">
      <h2 class="title">创建账号</h2>
      <el-form @submit.prevent="onSubmit">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名（至少4位）" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="email" placeholder="邮箱" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码（至少8位）" size="large" show-password />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" native-type="submit">注 册</el-button>
      </el-form>
      <div class="privacy-note">
        <div class="privacy-title">隐私说明 · 本站不收集隐私信息</div>
        <p>注册仅需用户名、邮箱和密码。<strong>邮箱仅作为账号标识，不会对外共享、不会用于营销，也不发送任何推广邮件。</strong>本站未接入第三方统计或广告追踪，你绘制的地图数据仅项目成员可见。</p>
        <a class="privacy-link" href="privacy.html" target="_blank" rel="noopener">查看完整隐私说明</a>
      </div>
      <div class="tip">
        已有账号？<router-link to="/login">去登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)

async function onSubmit() {
  if (!username.value || !email.value || !password.value) {
    ElMessage.warning('请填写完整信息')
    return
  }
  // 前端前置校验，与后端 Pydantic 规则一致，减少 422
  if (username.value.length < 4) {
    ElMessage.warning('用户名至少 4 个字符')
    return
  }
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username.value)) {
    ElMessage.warning('用户名只能包含字母、数字、下划线或中文')
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
    ElMessage.warning('请输入合法的邮箱地址')
    return
  }
  if (password.value.length < 8) {
    ElMessage.warning('密码至少 8 位')
    return
  }
  loading.value = true
  try {
    await auth.register({ username: username.value, email: email.value, password: password.value })
    ElMessage.success('注册成功')
    router.replace('/')
  } catch (e: any) {
    const detail = e.response?.data?.detail
    if (Array.isArray(detail)) {
      // 422 校验错误：后端已汉化，逐条显示（带字段名）
      const msgs = detail.map((d: any) => {
        const fieldLabel: Record<string, string> = { username: '用户名', email: '邮箱', password: '密码', display_name: '昵称' }
        const label = fieldLabel[d?.field] || d?.field || ''
        return (label ? label + '：' : '') + (d?.msg || '格式有误')
      })
      ElMessage.error(msgs.join('\n') || '注册信息格式有误')
    } else {
      ElMessage.error(detail || '注册失败，可能未开放注册')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef4ff 0%, #f7f9ff 100%);
}
.register-card {
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