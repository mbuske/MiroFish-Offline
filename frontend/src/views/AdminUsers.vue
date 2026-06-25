<template>
  <div class="admin-users-page">
    <header class="app-header">
      <div class="header-left">
        <router-link to="/" class="brand">
          <img v-if="logoUrl" :src="logoUrl" alt="Logo" class="brand-logo" />
          <span v-else>{{ $t('common.brand') }}</span>
        </router-link>
      </div>
      <div class="header-right">
        <UserMenu />
      </div>
    </header>

    <div class="admin-content">
      <h1>{{ $t('auth.admin.usersTitle') }}</h1>

      <p v-if="loadError" class="err">{{ loadError }}</p>

      <table v-if="users.length">
        <thead>
          <tr>
            <th>{{ $t('auth.admin.email') }}</th>
            <th>{{ $t('auth.admin.name') }}</th>
            <th>{{ $t('auth.admin.role') }}</th>
            <th>{{ $t('auth.admin.active') }}</th>
            <th>{{ $t('auth.admin.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.email }}</td>
            <td>{{ u.name }}</td>
            <td>
              <select :value="u.role" @change="changeRole(u, $event.target.value)" :disabled="busy">
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </td>
            <td>
              <input type="checkbox" :checked="u.is_active" @change="toggleActive(u)" :disabled="busy" />
            </td>
            <td>
              <button @click="resetPassword(u)" :disabled="busy">{{ $t('auth.admin.resetPassword') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty">{{ $t('auth.admin.noUsers') }}</p>

      <p v-if="actionError" class="err">{{ actionError }}</p>

      <section class="create-form">
        <h2>{{ $t('auth.admin.createUser') }}</h2>
        <form @submit.prevent="createUser">
          <input v-model="form.email" type="email" :placeholder="$t('auth.admin.email')" required />
          <input v-model="form.name" type="text" :placeholder="$t('auth.admin.name')" />
          <select v-model="form.role">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <input v-model="form.password" type="password" :placeholder="$t('auth.admin.password')" required />
          <p v-if="createError" class="err">{{ createError }}</p>
          <button type="submit" :disabled="busy">{{ $t('auth.admin.createUser') }}</button>
        </form>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import UserMenu from '@/components/UserMenu.vue'
import { useBranding } from '@/stores/branding'

const { logoUrl } = useBranding()

const users = ref([])
const busy = ref(false)
const loadError = ref('')
const actionError = ref('')
const createError = ref('')

const form = ref({ email: '', name: '', role: 'user', password: '' })

async function loadUsers() {
  loadError.value = ''
  try {
    const res = await api.get('/api/admin/users')
    users.value = res.users
  } catch (e) {
    loadError.value = e.message || 'Failed to load users'
  }
}

async function createUser() {
  createError.value = ''
  busy.value = true
  try {
    await api.post('/api/admin/users', {
      email: form.value.email,
      name: form.value.name,
      role: form.value.role,
      password: form.value.password
    })
    form.value = { email: '', name: '', role: 'user', password: '' }
    await loadUsers()
  } catch (e) {
    createError.value = e.message || 'Failed to create user'
  } finally {
    busy.value = false
  }
}

async function toggleActive(u) {
  actionError.value = ''
  busy.value = true
  try {
    await api.post(`/api/admin/users/${u.id}/active`, { active: !u.is_active })
    await loadUsers()
  } catch (e) {
    actionError.value = e.message || 'Failed to update active status'
  } finally {
    busy.value = false
  }
}

async function changeRole(u, role) {
  actionError.value = ''
  busy.value = true
  try {
    await api.post(`/api/admin/users/${u.id}/role`, { role })
    await loadUsers()
  } catch (e) {
    actionError.value = e.message || 'Failed to change role'
  } finally {
    busy.value = false
  }
}

async function resetPassword(u) {
  const password = window.prompt(`New password for ${u.email}:`)
  if (!password) return
  actionError.value = ''
  busy.value = true
  try {
    await api.post(`/api/admin/users/${u.id}/reset-password`, { password })
    await loadUsers()
  } catch (e) {
    actionError.value = e.message || 'Failed to reset password'
  } finally {
    busy.value = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.admin-users-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  text-decoration: none;
  color: #000;
}

.brand-logo {
  max-height: 36px;
  width: auto;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.admin-content {
  max-width: 900px;
  margin: 2rem auto;
  padding: 0 1rem;
  width: 100%;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.5rem;
}

th, td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #ddd;
}

th {
  font-weight: 600;
}

.create-form {
  margin-top: 2rem;
}

.create-form form {
  display: flex;
  flex-direction: column;
  max-width: 400px;
  gap: 0.6rem;
}

.err {
  color: red;
  margin: 0.25rem 0;
}

.empty {
  color: #999;
  margin: 1rem 0;
}
</style>
