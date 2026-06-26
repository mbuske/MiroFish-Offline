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
            <th>{{ $t('accounts.slug') }}</th>
            <th>{{ $t('accounts.active') }}</th>
            <th>{{ $t('accounts.userCount') }}</th>
            <th>{{ $t('accounts.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="acc in accounts" :key="acc.id">
            <tr>
              <td>{{ acc.name }}</td>
              <td>
                <div class="slug-cell">
                  <div v-if="renameId !== acc.id">
                    <span>{{ acc.slug }}</span>
                    <button @click="startRename(acc)" :disabled="busy" style="margin-left:0.4rem;">
                      {{ $t('accounts.rename') }}
                    </button>
                  </div>
                  <div v-else class="slug-rename-row">
                    <input v-model="renameSlug" type="text" />
                    <button @click="saveSlug(acc)" :disabled="busy">{{ $t('accounts.save') }}</button>
                    <button @click="cancelRename" :disabled="busy">{{ $t('accounts.cancel') }}</button>
                  </div>
                  <p v-if="slugErrors[acc.id]" class="err">{{ slugErrors[acc.id] }}</p>
                </div>
              </td>
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
                <button @click="toggleUsers(acc)" :disabled="busy" style="margin-left:0.4rem;">
                  {{ expanded[acc.id] ? '▾' : '▸' }} {{ $t('accounts.users') }} ({{ acc.user_count }})
                </button>
                <button @click="openBranding(acc)" :disabled="busy" style="margin-left:0.4rem;">
                  {{ $t('accounts.editBranding') }}
                </button>
              </td>
            </tr>
            <tr v-if="expanded[acc.id]">
              <td colspan="5">
                <p v-if="usersLoading[acc.id]">{{ $t('common.loading') }}</p>
                <p v-else-if="usersErrors[acc.id]" class="err">{{ usersErrors[acc.id] }}</p>
                <template v-else>
                  <p style="font-weight:600;margin-bottom:0.4rem;">
                    {{ $t('accounts.usersOf', { name: acc.name }) }}
                  </p>
                  <p v-if="!usersByAccount[acc.id] || usersByAccount[acc.id].length === 0" class="empty">
                    {{ $t('accounts.noUsers') }}
                  </p>
                  <table v-else class="users-table">
                    <thead>
                      <tr>
                        <th>{{ $t('auth.admin.email') }}</th>
                        <th>{{ $t('auth.admin.name') }}</th>
                        <th>{{ $t('auth.admin.role') }}</th>
                        <th>{{ $t('auth.admin.active') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="u in usersByAccount[acc.id]" :key="u.id">
                        <td>{{ u.email }}</td>
                        <td>{{ u.name }}</td>
                        <td>{{ u.role }}</td>
                        <td>
                          <span v-if="u.is_active" class="active-yes">✓</span>
                          <span v-else class="active-no">✗</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </template>
              </td>
            </tr>
          </template>
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

      <!-- Branding panel -->
      <section v-if="brandingForm.accountId" class="create-form">
        <h2>{{ $t('accounts.brandingOf', { name: brandingForm.accountName }) }}</h2>
        <p v-if="brandingForm.loading">{{ $t('common.loading') }}</p>
        <div v-else class="branding-row">
          <!-- Colors -->
          <div class="color-row">
            <label>{{ $t('branding.primaryColor') }}</label>
            <input type="color" v-model="brandingForm.primaryColor" />
          </div>
          <div class="color-row">
            <label>{{ $t('branding.accentColor') }}</label>
            <input type="color" v-model="brandingForm.accentColor" />
          </div>
          <div>
            <button @click="saveBrandingColors" :disabled="busy">{{ $t('branding.save') }}</button>
            <p v-if="brandingForm.colorMsg" class="ok-msg">{{ brandingForm.colorMsg }}</p>
            <p v-if="brandingForm.colorErr" class="err">{{ brandingForm.colorErr }}</p>
          </div>

          <!-- Logo -->
          <div class="upload-row">
            <label>{{ $t('branding.logo') }}</label>
            <input type="file" accept="image/*" @change="brandingForm.logoFile = $event.target.files[0]" />
            <button @click="uploadLogo" :disabled="busy || !brandingForm.logoFile">{{ $t('branding.upload') }}</button>
          </div>
          <p v-if="brandingForm.logoMsg" class="ok-msg">{{ brandingForm.logoMsg }}</p>
          <p v-if="brandingForm.logoErr" class="err">{{ brandingForm.logoErr }}</p>

          <!-- Favicon -->
          <div class="upload-row">
            <label>{{ $t('branding.favicon') }}</label>
            <input type="file" accept="image/*" @change="brandingForm.faviconFile = $event.target.files[0]" />
            <button @click="uploadFavicon" :disabled="busy || !brandingForm.faviconFile">{{ $t('branding.upload') }}</button>
          </div>
          <p v-if="brandingForm.faviconMsg" class="ok-msg">{{ brandingForm.faviconMsg }}</p>
          <p v-if="brandingForm.faviconErr" class="err">{{ brandingForm.faviconErr }}</p>

          <!-- Close -->
          <div>
            <button type="button" @click="closeBranding" :disabled="busy">{{ $t('common.close') }}</button>
          </div>
        </div>
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
import { useI18n } from 'vue-i18n'
import api from '@/api'
import UserMenu from '@/components/UserMenu.vue'
import { useBranding } from '@/stores/branding'

const { t: $t } = useI18n()
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
    loadError.value = e.response?.data?.error || $t('accounts.loadError')
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
    createError.value = e.response?.data?.error || $t('accounts.createAccountError')
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
    actionError.value = e.response?.data?.error || $t('accounts.toggleActiveError')
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
    adminForm.value.error = e.response?.data?.error || $t('accounts.createAdminError')
  } finally {
    busy.value = false
  }
}

// Rename slug state
const renameId = ref(null)
const renameSlug = ref('')
const slugErrors = ref({})

function startRename(acc) {
  renameId.value = acc.id
  renameSlug.value = acc.slug
  slugErrors.value[acc.id] = ''
  // close branding panel if open
  if (brandingForm.value.accountId) closeBranding()
}

function cancelRename() {
  renameId.value = null
  renameSlug.value = ''
}

async function saveSlug(acc) {
  slugErrors.value[acc.id] = ''
  busy.value = true
  try {
    await api.post(`/api/superadmin/accounts/${acc.id}/slug`, { slug: renameSlug.value })
    cancelRename()
    await loadAccounts()
  } catch (e) {
    slugErrors.value[acc.id] = e.response?.data?.error || $t('accounts.slugError')
  } finally {
    busy.value = false
  }
}

// Users drill-down state
const expanded = ref({})
const usersByAccount = ref({})
const usersLoading = ref({})
const usersErrors = ref({})

async function toggleUsers(acc) {
  if (expanded.value[acc.id]) {
    expanded.value[acc.id] = false
    return
  }
  expanded.value[acc.id] = true
  if (usersByAccount.value[acc.id]) return // cached
  usersLoading.value[acc.id] = true
  usersErrors.value[acc.id] = ''
  try {
    const res = await api.get(`/api/superadmin/accounts/${acc.id}/users`)
    usersByAccount.value[acc.id] = res.users
  } catch (e) {
    usersErrors.value[acc.id] = e.response?.data?.error || $t('accounts.usersLoadError')
    expanded.value[acc.id] = false
  } finally {
    usersLoading.value[acc.id] = false
  }
}

// Branding panel state
const brandingForm = ref({
  accountId: null,
  accountName: '',
  accountSlug: '',
  primaryColor: '#000000',
  accentColor: '#FF4500',
  logoFile: null,
  faviconFile: null,
  colorMsg: '',
  colorErr: '',
  logoMsg: '',
  logoErr: '',
  faviconMsg: '',
  faviconErr: '',
  loading: false
})

async function openBranding(acc) {
  brandingForm.value = {
    accountId: acc.id,
    accountName: acc.name,
    accountSlug: acc.slug,
    primaryColor: '#000000',
    accentColor: '#FF4500',
    logoFile: null,
    faviconFile: null,
    colorMsg: '',
    colorErr: '',
    logoMsg: '',
    logoErr: '',
    faviconMsg: '',
    faviconErr: '',
    loading: true
  }
  // close rename if open
  if (renameId.value) cancelRename()
  try {
    const cfg = await api.get(`/api/branding/config?account=${encodeURIComponent(acc.slug)}`)
    if (cfg.primary_color) brandingForm.value.primaryColor = cfg.primary_color
    if (cfg.accent_color) brandingForm.value.accentColor = cfg.accent_color
  } catch (e) {
    brandingForm.value.colorErr = e.response?.data?.error || $t('accounts.brandingLoadError')
  } finally {
    brandingForm.value.loading = false
  }
}

function closeBranding() {
  brandingForm.value = {
    accountId: null,
    accountName: '',
    accountSlug: '',
    primaryColor: '#000000',
    accentColor: '#FF4500',
    logoFile: null,
    faviconFile: null,
    colorMsg: '',
    colorErr: '',
    logoMsg: '',
    logoErr: '',
    faviconMsg: '',
    faviconErr: '',
    loading: false
  }
}

async function saveBrandingColors() {
  brandingForm.value.colorMsg = ''
  brandingForm.value.colorErr = ''
  busy.value = true
  try {
    await api.post(`/api/superadmin/accounts/${brandingForm.value.accountId}/branding`, {
      primary_color: brandingForm.value.primaryColor,
      accent_color: brandingForm.value.accentColor
    })
    brandingForm.value.colorMsg = $t('accounts.brandingSaved')
  } catch (e) {
    brandingForm.value.colorErr = e.response?.data?.error || $t('accounts.brandingError')
  } finally {
    busy.value = false
  }
}

async function uploadLogo() {
  if (!brandingForm.value.logoFile) return
  brandingForm.value.logoMsg = ''
  brandingForm.value.logoErr = ''
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('file', brandingForm.value.logoFile)
    await api.post(`/api/superadmin/accounts/${brandingForm.value.accountId}/branding/logo`, fd)
    brandingForm.value.logoMsg = $t('accounts.logoUploaded')
    brandingForm.value.logoFile = null
  } catch (e) {
    brandingForm.value.logoErr = e.response?.data?.error || $t('accounts.logoError')
  } finally {
    busy.value = false
  }
}

async function uploadFavicon() {
  if (!brandingForm.value.faviconFile) return
  brandingForm.value.faviconMsg = ''
  brandingForm.value.faviconErr = ''
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('file', brandingForm.value.faviconFile)
    await api.post(`/api/superadmin/accounts/${brandingForm.value.accountId}/branding/favicon`, fd)
    brandingForm.value.faviconMsg = $t('accounts.faviconUploaded')
    brandingForm.value.faviconFile = null
  } catch (e) {
    brandingForm.value.faviconErr = e.response?.data?.error || $t('accounts.faviconError')
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

.slug-cell {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.slug-rename-row {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.slug-rename-row input {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  padding: 0.2rem 0.4rem;
  border: 1px solid #ccc;
  border-radius: 2px;
  width: 160px;
}

.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.users-table th,
.users-table td {
  padding: 0.3rem 0.6rem;
  border-bottom: 1px solid #eee;
  text-align: left;
}

.users-table th {
  font-weight: 600;
  background: #f8f8f8;
}

.active-yes { color: #22c55e; font-weight: 600; }
.active-no  { color: #aaa; }

.branding-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 400px;
}

.color-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.upload-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.ok-msg { color: #22c55e; margin: 0; font-size: 0.85rem; }
</style>
