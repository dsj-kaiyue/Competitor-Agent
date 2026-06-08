<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const mode = ref<'login' | 'register'>('login')
const registrationPausedMessage = '感谢关注！由于当前 Token 额度有限，暂时关闭新用户注册。考核老师可使用管理员账号或测试账号登录体验，感谢理解。'
const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

function showRegistrationPausedMessage() {
  ElMessage({
    message: registrationPausedMessage,
    type: 'warning',
    customClass: 'registration-paused-message',
  })
}

async function submit() {
  if (mode.value === 'register') {
    showRegistrationPausedMessage()
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error) {
    console.error(error)
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}

function switchMode(nextMode: 'login' | 'register') {
  mode.value = nextMode
  if (nextMode === 'register') {
    showRegistrationPausedMessage()
  }
  form.username = ''
  form.password = ''
  form.confirmPassword = ''
}
</script>

<template>
  <main class="login-page">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Competitive Agent</p>
        <h1>登录后继续分析。</h1>
        <p>每个账户只显示自己的分析任务，管理员可进入用户管理。</p>
      </div>
      <el-form class="login-card" :model="form" @submit.prevent="submit">
        <div class="form-head">
          <h2>{{ mode === 'login' ? '账户登录' : '注册账户' }}</h2>
          <el-segmented
            :model-value="mode"
            :options="[
              { label: '登录', value: 'login' },
              { label: '注册', value: 'register' },
            ]"
            @update:model-value="switchMode"
          />
        </div>
        <el-form-item>
          <el-input v-model="form.username" autocomplete="username" placeholder="用户名" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            autocomplete="current-password"
            placeholder="密码"
            show-password
            size="large"
            type="password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item v-if="mode === 'register'">
          <el-input
            v-model="form.confirmPassword"
            autocomplete="new-password"
            placeholder="确认密码"
            show-password
            size="large"
            type="password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button class="login-button" type="primary" :loading="loading" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>

      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  background: var(--ca-parchment);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  align-items: center;
  gap: 64px;
  width: min(1120px, calc(100vw - 40px));
  min-height: 100vh;
  margin: 0 auto;
  padding: 80px 0;
}

.hero-copy {
  display: grid;
  gap: 18px;
}

.eyebrow {
  color: var(--ca-primary);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.24;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  max-width: 650px;
  color: var(--ca-ink);
  font-size: 56px;
  font-weight: 600;
  letter-spacing: -0.28px;
  line-height: 1.07;
}

.hero-copy p:last-child {
  max-width: 620px;
  color: var(--ca-muted);
  font-size: 24px;
  font-weight: 300;
  line-height: 1.5;
}

.login-card {
  display: grid;
  gap: 18px;
  padding: 28px;
  border: 1px solid var(--ca-hairline);
  border-radius: var(--ca-radius-lg);
  background: var(--ca-canvas);
}

h2 {
  color: var(--ca-ink);
  font-size: 28px;
  font-weight: 600;
  line-height: 1.15;
}

.form-head {
  display: grid;
  gap: 14px;
}

.login-button {
  width: 100%;
  min-height: 44px;
}

@media (max-width: 820px) {
  .hero {
    grid-template-columns: 1fr;
    align-content: center;
    gap: 36px;
  }

  h1 {
    font-size: 40px;
  }

  .hero-copy p:last-child {
    font-size: 19px;
  }
}
</style>

<style>
.registration-paused-message {
  --el-message-bg-color: #fff4d8;
  --el-message-border-color: #f1c36d;
  --el-message-text-color: #8a5a12;
  box-shadow: 0 10px 30px rgb(138 90 18 / 10%);
}

.registration-paused-message .el-message__icon {
  color: #b7791f;
}
</style>
