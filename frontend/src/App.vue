<template>
  <RouterView v-if="$route.meta.public" />
  <el-container v-else class="app-shell">
    <el-header class="app-header">
      <RouterLink to="/" class="brand">AI 竞品分析工作台</RouterLink>
      <nav class="nav">
        <RouterLink to="/">新建分析</RouterLink>
        <RouterLink to="/history">历史记录</RouterLink>
      </nav>
      <el-dropdown class="session">
        <span class="el-dropdown-link" style="cursor: pointer; outline: none; display: flex; align-items: center; gap: 4px;">
          {{ auth.user?.username }}
          <el-icon><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-if="auth.isAdmin" @click="router.push('/users')">用户管理</el-dropdown-item>
            <el-dropdown-item @click="passwordDialogVisible = true" :divided="auth.isAdmin">修改密码</el-dropdown-item>
            <el-dropdown-item @click="logout" divided>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-header>
    <el-main class="app-main">
      <RouterView />
    </el-main>
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="420px">
      <el-form class="password-form" :model="passwordForm" @submit.prevent="submitPassword">
        <el-form-item>
          <el-input
            v-model="passwordForm.currentPassword"
            autocomplete="current-password"
            placeholder="当前密码"
            show-password
            type="password"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="passwordForm.newPassword"
            autocomplete="new-password"
            placeholder="新密码"
            show-password
            type="password"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="passwordForm.confirmPassword"
            autocomplete="new-password"
            placeholder="确认新密码"
            show-password
            type="password"
            @keyup.enter="submitPassword"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="passwordLoading" @click="submitPassword">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()
const passwordDialogVisible = ref(false)
const passwordLoading = ref(false)
const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

function logout() {
  auth.logout()
  router.push('/login')
}

async function submitPassword() {
  if (!passwordForm.currentPassword || !passwordForm.newPassword) {
    ElMessage.warning('请填写当前密码和新密码')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  passwordLoading.value = true
  try {
    await auth.changePassword(passwordForm.currentPassword, passwordForm.newPassword)
    passwordForm.currentPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
    passwordDialogVisible.value = false
    ElMessage.success('密码已修改')
  } catch (error) {
    console.error(error)
    ElMessage.error('密码修改失败')
  } finally {
    passwordLoading.value = false
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--ca-parchment);
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 24px;
  height: 64px;
  padding: 0 max(24px, calc((100vw - 1440px) / 2 + 24px));
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(245, 245, 247, 0.86);
  color: var(--ca-ink);
  backdrop-filter: saturate(180%) blur(20px);
}

.brand {
  color: var(--ca-ink);
  font-size: 21px;
  font-weight: 600;
  line-height: 1.19;
}

.nav {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-left: auto;
  font-size: 13px;
  line-height: 1;
}

.session {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ca-muted);
  font-size: 13px;
  line-height: 1;
}

.password-form {
  display: grid;
  gap: 4px;
}

.nav a {
  color: var(--el-text-color-secondary);
}

.nav a.router-link-active {
  color: var(--ca-ink);
  font-weight: 600;
}

.app-main {
  width: min(1180px, calc(100vw - 40px));
  margin: 0 auto;
  padding: 32px 0 64px;
}

@media (max-width: 760px) {
  .app-header {
    padding-inline: 16px;
  }

  .nav {
    gap: 14px;
  }

  .brand {
    font-size: 18px;
  }

  .app-main {
    width: min(100% - 24px, 1180px);
    padding-top: 20px;
  }
}
</style>
