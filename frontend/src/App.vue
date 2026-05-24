<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <RouterLink to="/" class="brand">Competitive Agent</RouterLink>
      <span>AI 驱动的通用竞品分析 Agent 协作系统</span>
    </el-header>
    <el-main class="app-main">
      <RouterView />
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
  color: #1f2937;
  background: #f6f8fb;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

a {
  color: var(--el-color-primary);
  text-decoration: none;
}
</style>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 58px;
  border-bottom: 1px solid var(--el-border-color);
  background: #ffffff;
}

.brand {
  color: #111827;
  font-weight: 700;
}

.app-header span {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.app-main {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 24px 0 48px;
}
</style>
