import { createRouter, createWebHistory } from 'vue-router'
import EvidenceView from '@/views/EvidenceView.vue'
import HistoryView from '@/views/HistoryView.vue'
import ReportView from '@/views/ReportView.vue'
import TaskCreateView from '@/views/TaskCreateView.vue'
import TaskDetailView from '@/views/TaskDetailView.vue'
import LoginView from '@/views/LoginView.vue'
import UsersView from '@/views/UsersView.vue'
import { useAuthStore } from '@/stores/authStore'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'task-create', component: TaskCreateView },
    { path: '/history', name: 'task-history', component: HistoryView },
    { path: '/users', name: 'users', component: UsersView, meta: { admin: true } },
    { path: '/tasks/:id', name: 'task-detail', component: TaskDetailView },
    { path: '/tasks/:id/report', name: 'task-report', component: ReportView },
    { path: '/tasks/:id/evidence', name: 'task-evidence', component: EvidenceView },
    { path: '/tasks/:id/timing', redirect: (to) => `/tasks/${to.params.id}` },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.admin && !auth.isAdmin) {
    return { path: '/' }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

export default router
