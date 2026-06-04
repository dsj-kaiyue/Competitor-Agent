<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <RouterLink to="/" class="brand">Competitive Agent</RouterLink>
      <nav class="nav">
        <RouterLink to="/">新建分析</RouterLink>
        <RouterLink to="/history">历史记录</RouterLink>
      </nav>
    </el-header>
    <div class="sub-nav">
      <span>AI 竞品分析工作台</span>
    </div>
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
  height: 44px;
  padding: 0 max(24px, calc((100vw - 1440px) / 2 + 24px));
  border-bottom: 0;
  background: #000000;
  color: #ffffff;
}

.brand {
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.nav {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-left: auto;
  font-size: 12px;
  line-height: 1;
}

.nav a {
  color: rgba(255, 255, 255, 0.78);
}

.nav a.router-link-active {
  color: #ffffff;
  font-weight: 600;
}

.sub-nav {
  position: sticky;
  top: 44px;
  z-index: 19;
  display: flex;
  align-items: center;
  min-height: 52px;
  padding: 0 max(24px, calc((100vw - 1440px) / 2 + 24px));
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(245, 245, 247, 0.82);
  backdrop-filter: saturate(180%) blur(20px);
}

.sub-nav span {
  color: var(--ca-ink);
  font-size: 21px;
  font-weight: 600;
  line-height: 1.19;
}

.app-main {
  width: min(1180px, calc(100vw - 40px));
  margin: 0 auto;
  padding: 32px 0 64px;
}

@media (max-width: 760px) {
  .app-header,
  .sub-nav {
    padding-inline: 16px;
  }

  .nav {
    gap: 14px;
  }

  .sub-nav span {
    font-size: 18px;
  }

  .app-main {
    width: min(100% - 24px, 1180px);
    padding-top: 20px;
  }
}
</style>
