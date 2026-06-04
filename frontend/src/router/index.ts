import { createRouter, createWebHistory } from 'vue-router'
import EvidenceView from '@/views/EvidenceView.vue'
import HistoryView from '@/views/HistoryView.vue'
import ReportView from '@/views/ReportView.vue'
import TaskCreateView from '@/views/TaskCreateView.vue'
import TaskDetailView from '@/views/TaskDetailView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'task-create', component: TaskCreateView },
    { path: '/history', name: 'task-history', component: HistoryView },
    { path: '/tasks/:id', name: 'task-detail', component: TaskDetailView },
    { path: '/tasks/:id/report', name: 'task-report', component: ReportView },
    { path: '/tasks/:id/evidence', name: 'task-evidence', component: EvidenceView },
    { path: '/tasks/:id/timing', redirect: (to) => `/tasks/${to.params.id}` },
  ],
})

export default router
