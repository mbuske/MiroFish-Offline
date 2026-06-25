<template>
  <div class="branding-settings-page">
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

    <div class="settings-content">
      <h1>{{ $t('branding.title') }}</h1>

      <p v-if="loadError" class="err">{{ loadError }}</p>

      <section class="settings-section">
        <h2>{{ $t('branding.primaryColor') }}</h2>
        <div class="color-row">
          <input type="color" v-model="primaryColor" />
          <span>{{ primaryColor }}</span>
        </div>

        <h2>{{ $t('branding.accentColor') }}</h2>
        <div class="color-row">
          <input type="color" v-model="accentColor" />
          <span>{{ accentColor }}</span>
        </div>

        <p v-if="saveError" class="err">{{ saveError }}</p>
        <p v-if="saveSuccess" class="success">{{ $t('common.success') }}</p>

        <button class="btn-primary" @click="saveColors" :disabled="saving">
          {{ saving ? $t('common.loading') : $t('branding.save') }}
        </button>
      </section>

      <section class="settings-section">
        <h2>{{ $t('branding.logo') }}</h2>
        <div v-if="currentLogoUrl" class="preview-row">
          <p>{{ $t('branding.currentLogo') }}</p>
          <img :src="currentLogoUrl" alt="Current logo" class="preview-img" />
        </div>
        <div class="upload-row">
          <input type="file" accept="image/*" @change="onLogoChange" ref="logoInput" />
          <button class="btn-secondary" @click="uploadLogo" :disabled="!logoFile || uploadingLogo">
            {{ uploadingLogo ? $t('common.loading') : $t('branding.upload') }}
          </button>
        </div>
        <p v-if="logoError" class="err">{{ logoError }}</p>
        <p v-if="logoSuccess" class="success">{{ $t('common.success') }}</p>
      </section>

      <section class="settings-section">
        <h2>{{ $t('branding.favicon') }}</h2>
        <div class="upload-row">
          <input type="file" accept="image/*" @change="onFaviconChange" ref="faviconInput" />
          <button class="btn-secondary" @click="uploadFavicon" :disabled="!faviconFile || uploadingFavicon">
            {{ uploadingFavicon ? $t('common.loading') : $t('branding.upload') }}
          </button>
        </div>
        <p v-if="faviconError" class="err">{{ faviconError }}</p>
        <p v-if="faviconSuccess" class="success">{{ $t('common.success') }}</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import UserMenu from '@/components/UserMenu.vue'
import { useBranding } from '@/stores/branding'

const branding = useBranding()
const { logoUrl } = branding

const primaryColor = ref('#000000')
const accentColor = ref('#FF4500')
const currentLogoUrl = ref(null)
const loadError = ref('')
const saveError = ref('')
const saveSuccess = ref(false)
const saving = ref(false)

const logoFile = ref(null)
const logoInput = ref(null)
const uploadingLogo = ref(false)
const logoError = ref('')
const logoSuccess = ref(false)

const faviconFile = ref(null)
const faviconInput = ref(null)
const uploadingFavicon = ref(false)
const faviconError = ref('')
const faviconSuccess = ref(false)

async function loadConfig() {
  loadError.value = ''
  try {
    const cfg = await api.get('/api/branding/config')
    if (cfg.primary_color) primaryColor.value = cfg.primary_color
    if (cfg.accent_color) accentColor.value = cfg.accent_color
    if (cfg.logo_url) currentLogoUrl.value = cfg.logo_url
  } catch (e) {
    loadError.value = e.message || 'Failed to load branding config'
  }
}

async function saveColors() {
  saveError.value = ''
  saveSuccess.value = false
  saving.value = true
  try {
    await api.post('/api/admin/branding', {
      primary_color: primaryColor.value,
      accent_color: accentColor.value
    })
    saveSuccess.value = true
    await branding.applyBranding()
  } catch (e) {
    saveError.value = e.message || 'Failed to save colors'
  } finally {
    saving.value = false
  }
}

function onLogoChange(e) {
  logoFile.value = e.target.files[0] || null
}

async function uploadLogo() {
  if (!logoFile.value) return
  logoError.value = ''
  logoSuccess.value = false
  uploadingLogo.value = true
  try {
    const formData = new FormData()
    formData.append('file', logoFile.value)
    await api.post('/api/admin/branding/logo', formData)
    logoSuccess.value = true
    logoFile.value = null
    if (logoInput.value) logoInput.value.value = ''
    await branding.applyBranding()
    await loadConfig()
  } catch (e) {
    logoError.value = e.message || 'Failed to upload logo'
  } finally {
    uploadingLogo.value = false
  }
}

function onFaviconChange(e) {
  faviconFile.value = e.target.files[0] || null
}

async function uploadFavicon() {
  if (!faviconFile.value) return
  faviconError.value = ''
  faviconSuccess.value = false
  uploadingFavicon.value = true
  try {
    const formData = new FormData()
    formData.append('file', faviconFile.value)
    await api.post('/api/admin/branding/favicon', formData)
    faviconSuccess.value = true
    faviconFile.value = null
    if (faviconInput.value) faviconInput.value.value = ''
    await branding.applyBranding()
  } catch (e) {
    faviconError.value = e.message || 'Failed to upload favicon'
  } finally {
    uploadingFavicon.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.branding-settings-page {
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

.settings-content {
  max-width: 700px;
  margin: 2rem auto;
  padding: 0 1rem;
  width: 100%;
}

.settings-section {
  margin-bottom: 2.5rem;
  padding: 1.5rem;
  border: 1px solid #EAEAEA;
}

.color-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.upload-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.75rem;
}

.preview-row {
  margin-bottom: 0.75rem;
}

.preview-img {
  max-width: 200px;
  max-height: 80px;
  border: 1px solid #EEE;
  margin-top: 0.5rem;
}

.btn-primary {
  background: #000;
  color: #fff;
  border: none;
  padding: 10px 24px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  letter-spacing: 1px;
  margin-top: 0.5rem;
}

.btn-primary:hover:not(:disabled) {
  background: #333;
}

.btn-secondary {
  background: transparent;
  color: #333;
  border: 1px solid #CCC;
  padding: 6px 16px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  cursor: pointer;
}

.btn-secondary:hover:not(:disabled) {
  border-color: #999;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.err {
  color: red;
  margin: 0.25rem 0;
}

.success {
  color: green;
  margin: 0.25rem 0;
}
</style>
