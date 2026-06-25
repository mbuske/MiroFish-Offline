<template>
  <div v-if="isAuthenticated" class="user-menu" ref="menuRef">
    <button class="menu-trigger" @click="toggleOpen">
      <span class="user-label">{{ user?.name || user?.email }}</span>
      <span class="caret">{{ open ? '▲' : '▼' }}</span>
    </button>

    <div v-if="open" class="menu-dropdown">
      <!-- User identity header -->
      <div class="menu-identity">
        <span class="identity-email">{{ user?.email }}</span>
      </div>

      <div class="menu-divider"></div>

      <!-- Language section -->
      <div class="menu-section-label">{{ $t('auth.menu.language') }}</div>
      <ul class="locale-list">
        <li
          v-for="loc in availableLocales"
          :key="loc.key"
          class="locale-item"
          :class="{ active: loc.key === locale }"
          @click="switchLocale(loc.key)"
        >
          {{ loc.label }}
        </li>
      </ul>

      <div class="menu-divider"></div>

      <!-- Admin section -->
      <template v-if="isAdmin">
        <div class="menu-section-label">{{ $t('auth.menu.admin') }}</div>
        <router-link class="menu-item" to="/admin/users" @click="open = false">
          {{ $t('auth.admin.usersTitle') }}
        </router-link>
        <router-link class="menu-item" to="/admin/branding" @click="open = false">
          {{ $t('branding.menuTitle') }}
        </router-link>
        <div class="menu-divider"></div>
      </template>

      <!-- Logout -->
      <button class="menu-item menu-item--logout" @click="handleLogout">
        {{ $t('auth.logout') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuth } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { availableLocales } from '@/i18n/index.js'

const auth = useAuth()
const router = useRouter()
const { locale } = useI18n()

const { user, isAuthenticated, isAdmin } = auth

const open = ref(false)
const menuRef = ref(null)

function toggleOpen() {
  open.value = !open.value
}

function switchLocale(key) {
  locale.value = key
  localStorage.setItem('locale', key)
  document.documentElement.lang = key
  open.value = false
}

async function handleLogout() {
  open.value = false
  await auth.logout()
  router.replace('/login')
}

function onClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.user-menu {
  position: relative;
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
}

.menu-trigger {
  background: transparent;
  color: #333;
  border: 1px solid #CCC;
  padding: 4px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: border-color 0.2s;
}

.menu-trigger:hover {
  border-color: #999;
}

.user-label {
  white-space: nowrap;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.caret {
  font-size: 0.6rem;
}

.menu-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: #FFFFFF;
  border: 1px solid #DDD;
  min-width: 180px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 4px 0;
}

.menu-identity {
  padding: 8px 12px 6px;
}

.identity-email {
  font-size: 0.75rem;
  color: #999;
  word-break: break-all;
}

.menu-divider {
  height: 1px;
  background: #EEEEEE;
  margin: 4px 0;
}

.menu-section-label {
  padding: 4px 12px 2px;
  font-size: 0.7rem;
  color: #AAA;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.locale-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.locale-item {
  padding: 6px 12px;
  font-size: 0.8rem;
  color: #333;
  cursor: pointer;
  transition: background 0.15s;
}

.locale-item:hover {
  background: #F0F0F0;
}

.locale-item.active {
  color: var(--brand-primary, #FF4500);
}

.menu-item {
  display: block;
  padding: 6px 12px;
  font-size: 0.8rem;
  color: #333;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s;
  font-family: 'JetBrains Mono', monospace;
  background: transparent;
  border: none;
  width: 100%;
  text-align: left;
}

.menu-item:hover {
  background: #F0F0F0;
}

.menu-item--logout {
  color: #555;
}
</style>
