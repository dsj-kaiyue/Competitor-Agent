import { http } from './http'
import type { User } from '@/types/user'

export async function getUsers() {
  const { data } = await http.get<{ items: User[] }>('/users')
  return data.items
}

export async function setUserActive(userId: number, is_active: boolean) {
  const { data } = await http.patch<User>(`/users/${userId}/active`, { is_active })
  return data
}
