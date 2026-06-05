import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { changePassword as changePasswordApi, getCurrentUser, login as loginApi, register as registerApi } from '@/api/authApi'
import type { User } from '@/types/user'

const TOKEN_KEY = 'competitor-agent-token'
const USER_KEY = 'competitor-agent-user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const storedUser = localStorage.getItem(USER_KEY)
  const user = ref<User | null>(storedUser ? JSON.parse(storedUser) : null)

  const isAuthenticated = computed(() => Boolean(token.value))
  const isAdmin = computed(() => Boolean(user.value?.is_admin))

  function persist(nextToken: string, nextUser: User) {
    token.value = nextToken
    user.value = nextUser
    localStorage.setItem(TOKEN_KEY, nextToken)
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  async function login(username: string, password: string) {
    const data = await loginApi(username, password)
    persist(data.access_token, data.user)
  }

  async function register(username: string, password: string) {
    const data = await registerApi(username, password)
    persist(data.access_token, data.user)
  }

  async function changePassword(currentPassword: string, newPassword: string) {
    const nextUser = await changePasswordApi(currentPassword, newPassword)
    user.value = nextUser
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  async function refreshMe() {
    if (!token.value) return
    const nextUser = await getCurrentUser()
    user.value = nextUser
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, isAuthenticated, isAdmin, login, register, changePassword, refreshMe, logout }
})
