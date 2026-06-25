<template>
  <div class="superadmin-accounts-page">
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
      <h1>{{ $t('accounts.title') }}</h1>

      <p v-if="loadError" class="err">{{ loadError }}</p>

      <table v-if="accounts.length">
        <thead>
          <tr>
            <th>{{ $t('accounts.name') }}</th>
            <th>{{ $t('accounts.active') }}</th>
            <th>{{ $t('accounts.userCount') }}</th>
            <th>{{ $t('accounts.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="acc in accounts" :key="acc.id">
            <td>{{ acc.name }}</td>
            <td>
              <input
                type="checkbox"
                :checked="acc.is_active"
                @change="toggleActive(acc)"
                :disabled="busy"
              />
            </td>
            <td>{{ acc.user_count }}</td>
            <td>
              <button @click="openCreateAdmin(acc)" :disabled="busy">
                {{ $t('accounts.createAdmin') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loadError" class="empty">{{ $t('accounts.noAccounts') }}</p>

      <p v-if="actionError" class="err">{{ actionError }}</p>

      <!-- Create Admin inline form -->
      <section v-if="adminForm.accountId" class="create-form">
        <h2>{{ $t('accounts.createAdmin') }}: {{ adminForm.accountName }}</h2>
        <form @submit.prevent="createAdmin">
          <input v-model="adminForm.email" type="email" :placeholder="$t('accounts.adminEmail')" required />
          <input v-model="adminForm.name" type="text" :placeholder="$t('accounts.adminName')" />
          <input v-model="adminForm.password" type="password" :placeholder="$t('accounts.adminPassword')" required />
          <p v-if="adminForm.error" class="err">{{ adminForm.error }}</p>
          <div class="form-actions">
            <button type="submit" :disabled="busy">{{ $t('accounts.createAdmin') }}</button>
            <button type="button" @click="closeCreateAdmin" :disabled="busy">{{ $t('accounts.cancel') }}</button>
          </div>
        </form>
      </section>

      <!-- Create Account form -->
      <section class="create-form">
        <h2>{{ $t('accounts.createAccount') }}</h2>
        <form @submit.prevent="createAccount">
          <input v-model="newAccountName" type="text" :placeholder="$t('accounts.accountName')" required />
          <p v-if="createError" class="err">{{ createError }}</p>
          <button type="submit" :disabled="busy">{{ $t('accounts.createAccount') }}</button>
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

const accounts = ref([])
const busy = ref(false)
const loadError = ref('')
const actionError = ref('')
const createError = ref('')
const newAccountName = ref('')

const adminForm = ref({
  accountId: null,
  accountName: '',
  email: '',
  name: '',
  password: '',
  error: ''
})

async function loadAccounts() {
  loadError.value = ''
  try {
    const res = await api.get('/api/superadmin/accounts')
    accounts.value = res.accounts
  } catch (e) {
    loadError.value = e.message || 'Failed to load accounts'
  }
}

async function createAccount() {
  createError.value = ''
  busy.value = true
  try {
    await api.post('/api/superadmin/accounts', { name: newAccountName.value })
    newAccountName.value = ''
    await loadAccounts()
  } catch (e) {
    createError.value = e.message || 'Failed to create account'
  } finally {
    busy.value = false
  }
}

async function toggleActive(acc) {
  actionError.value = ''
  busy.value = true
  try {
    await api.post(`/api/superadmin/accounts/${acc.id}/active`, { active: !acc.is_active })
    await loadAccounts()
  } catch (e) {
    actionError.value = e.message || 'Failed to update active status'
  } finally {
    busy.value = false
  }
}

function openCreateAdmin(acc) {
  adminForm.value = {
    accountId: acc.id,
    accountName: acc.name,
    email: '',
    name: '',
    password: '',
    error: ''
  }
}

function closeCreateAdmin() {
  adminForm.value = {
    accountId: null,
    accountName: '',
    email: '',
    name: '',
    password: '',
    error: ''
  }
}

async function createAdmin() {
  adminForm.value.error = ''
  busy.value = true
  try {
    await api.post(`/api/superadmin/accounts/${adminForm.value.accountId}/admin`, {
      email: adminForm.value.email,
      name: adminForm.value.name,
      password: adminForm.value.password
    })
    closeCreateAdmin()
    await loadAccounts()
  } catch (e) {
    adminForm.value.error = e.message || 'Failed to create admin'
  } finally {
    busy.value = false
  }
}

onMounted(loadAccounts)
</script>

<style scoped>
.superadmin-accounts-page {
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

.form-actions {
  display: flex;
  gap: 0.5rem;
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
