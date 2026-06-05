<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <RouterLink to="/" class="brand">AI 竞品分析工作台</RouterLink>
      <nav class="nav">
        <RouterLink to="/">新建分析</RouterLink>
        <RouterLink to="/history">历史记录</RouterLink>
      </nav>
    </el-header>
    <el-main class="app-main">
      <RouterView />
    </el-main>
  </el-container>
</template>

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
