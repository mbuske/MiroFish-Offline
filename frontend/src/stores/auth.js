import { reactive, computed } from 'vue'
import api from '@/api'

const state = reactive({ user: null, ready: false })

export function useAuth() {
  return {
    user: computed(() => state.user),
    ready: computed(() => state.ready),
    isAuthenticated: computed(() => !!state.user),
    isAdmin: computed(() => state.user?.role === 'admin'),
    async fetchMe() {
      try {
        const { data } = await api.get('/api/auth/me')
        state.user = data.user
      } catch { state.user = null }
      finally { state.ready = true }
    },
    async login(email, password) {
      const { data } = await api.post('/api/auth/login', { email, password })
      state.user = data.user
      return data.user
    },
    async logout() {
      try { await api.post('/api/auth/logout') } finally { state.user = null }
    },
  }
}
