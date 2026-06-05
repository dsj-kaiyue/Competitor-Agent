import { http } from './http'
import type { User } from '@/types/user'

export async function login(username: string, password: string) {
  const { data } = await http.post<{ access_token: string; token_type: string; user: User }>('/auth/login', {
    username,
    password,
  })
  return data
}

export async function register(username: string, password: string) {
  const { data } = await http.post<{ access_token: string; token_type: string; user: User }>('/auth/register', {
    username,
    password,
  })
  return data
}

export async function getCurrentUser() {
  const { data } = await http.get<User>('/auth/me')
  return data
}

export async function changePassword(current_password: string, new_password: string) {
  const { data } = await http.post<User>('/auth/password', {
    current_password,
    new_password,
  })
  return data
}
