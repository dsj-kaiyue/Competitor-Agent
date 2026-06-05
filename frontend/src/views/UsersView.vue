<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { getUsers, setUserActive } from '@/api/userApi'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types/user'

const users = ref<User[]>([])
const loading = ref(false)
const actionLoading = ref<number | null>(null)
const errorMessage = ref('')
const searchQuery = ref('')
const auth = useAuthStore()
const router = useRouter()

const filteredUsers = computed(() => {
  if (!searchQuery.value) return users.value
  const lowerQuery = searchQuery.value.toLowerCase()
  return users.value.filter((user) => user.username.toLowerCase().includes(lowerQuery))
})

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

async function loadUsers() {
  loading.value = true
  errorMessage.value = ''
  try {
    users.value = await getUsers()
  } catch (error) {
    console.error(error)
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

async function toggleActive(user: User) {
  const nextActive = !user.is_active
  await ElMessageBox.confirm(
    nextActive ? `确认启用账户 ${user.username}？` : `停用后 ${user.username} 将无法登录，确认停用？`,
    nextActive ? '启用账户' : '停用账户',
    {
      type: nextActive ? 'info' : 'warning',
      confirmButtonText: nextActive ? '确认启用' : '确认停用',
      cancelButtonText: '取消',
    },
  )
  actionLoading.value = user.id
  try {
    const nextUser = await setUserActive(user.id, nextActive)
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) {
      users.value[index] = nextUser
    }
    ElMessage.success(nextActive ? '账户已启用' : '账户已停用')
  } catch (error) {
    console.error(error)
    ElMessage.error('账户状态更新失败')
  } finally {
    actionLoading.value = null
  }
}

onMounted(loadUsers)
</script>

<template>
  <main v-loading="loading" class="page">
    <section class="toolbar">
      <div>
        <h1>用户管理</h1>
        <p>查看当前系统账户和管理员权限。</p>
      </div>
      <div class="actions">
        <el-input
          v-model="searchQuery"
          placeholder="搜索用户..."
          :prefix-icon="Search"
          clearable
          style="width: 200px"
        />
        <el-button type="primary" @click="loadUsers">刷新</el-button>
      </div>
    </section>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />

    <el-table :data="filteredUsers" class="user-table">
      <el-table-column label="用户名" min-width="180">
        <template #default="{ row }">
          <div class="user-cell">
            <div class="avatar-small">{{ row.username.slice(0, 1).toUpperCase() }}</div>
            <strong>{{ row.username }}</strong>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="角色" min-width="120">
        <template #default="{ row }">
          <el-tag v-if="row.is_admin" type="primary" effect="plain">管理员</el-tag>
          <el-tag v-else effect="plain">普通用户</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" effect="plain">
            {{ row.is_active ? '已启用' : '已停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="180">
        <template #default="{ row }">
          <span class="time-text">{{ formatDateTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="任务" width="120" align="center">
        <template #default="{ row }">
          <el-button
            size="small"
            @click="router.push(`/history?userId=${row.id}`)"
          >
            查看任务
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button
            v-if="!row.is_admin && row.id !== auth.user?.id"
            :loading="actionLoading === row.id"
            :type="row.is_active ? 'danger' : 'primary'"
            plain
            size="small"
            @click="toggleActive(row)"
          >
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  gap: 22px;
}

.toolbar,
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar {
  justify-content: space-between;
  padding: 28px 0 12px;
}

.actions {
  flex-wrap: wrap;
}

.user-table {
  border-radius: var(--ca-radius-lg);
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-cell strong {
  color: var(--ca-ink);
  font-size: 15px;
  font-weight: 600;
}

.avatar-small {
  display: grid;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: var(--ca-ink);
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
}

.time-text {
  color: var(--ca-muted);
  font-size: 14px;
}

h1,
p {
  margin: 0;
}

h1 {
  color: var(--ca-ink);
  font-size: 40px;
  font-weight: 600;
  line-height: 1.1;
}

.toolbar p {
  color: var(--ca-muted);
  margin-top: 10px;
  font-size: 21px;
  line-height: 1.35;
}

@media (max-width: 760px) {
    .toolbar {
      align-items: flex-start;
      flex-direction: column;
    }
  
    h1 {
      font-size: 30px;
    }
  
    .toolbar p {
      font-size: 17px;
    }
  }
</style>
