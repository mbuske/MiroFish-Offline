import { reactive, computed } from 'vue'
import api from '@/api'

const state = reactive({ user: null, ready: false })

export function useAuth() {
  return {
    user: computed(() => state.user),
    ready: computed(() => state.ready),
    isAuthenticated: computed(() => !!state.user),
    accountName: computed(() => state.user?.account_name ?? null),
    isSuperadmin: computed(() => state.user?.role === 'superadmin'),
    isAccountAdmin: computed(() => state.user?.role === 'account_admin'),
    async fetchMe() {
      try {
        // The axios response interceptor already unwraps to response.data,
        // so api.* resolves to the payload object ({success, user}) directly.
        const res = await api.get('/api/auth/me')
        state.user = res.user
      } catch { state.user = null }
      finally { state.ready = true }
    },
    async login(email, password) {
      const res = await api.post('/api/auth/login', { email, password })
      state.user = res.user
      return res.user
    },
    async logout() {
      try { await api.post('/api/auth/logout') } finally { state.user = null }
    },
  }
}
